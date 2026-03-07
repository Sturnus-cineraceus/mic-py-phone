import os
import uuid
import wave
import subprocess
import numpy as np
import threading
from . import audio_device
import logging


class RecorderSink:
    """Object-style sink that writes incoming float32 frames to a temporary WAV
    and converts to MP3 in a background thread when stopped.

    This class is intended to be registered with `SinkManager.register(RecorderSinkInstance)`
    so that the SinkManager worker will call `consume(frames, meta)`.
    """

    def __init__(self, target_path: str, samplerate: int = 44100, channels: int = 1):
        """録音シンクを初期化し、一時 WAV ファイルを開く。

        Args:
            target_path: 出力先ファイルパス（.mp3 以外の拡張子は .mp3 に変換される）。
            samplerate: サンプルレート（Hz）。デフォルトは 44100。
            channels: チャンネル数。デフォルトは 1。
        """
        self.target_path = str(target_path)
        if not self.target_path.lower().endswith(".mp3"):
            base = os.path.splitext(self.target_path)[0]
            self._out_path = base + ".mp3"
        else:
            self._out_path = self.target_path

        tmp_name = f".pymic_rec_{uuid.uuid4().hex}.wav"
        self._tmp_path = os.path.join(os.path.dirname(self._out_path) or ".", tmp_name)

        self._samplerate = int(samplerate or 44100)
        self._channels = int(channels or 1)

        # open wave file for writing; keep handle until stop()
        self._wf = wave.open(self._tmp_path, "wb")
        self._wf.setnchannels(self._channels)
        self._wf.setsampwidth(2)
        self._wf.setframerate(self._samplerate)

        self._closed = False

    def consume(self, frames, meta=None):
        """フレームを受け取り一時 WAV ファイルに書き込む。

        Args:
            frames: float32 の numpy 配列（値域 -1.0〜1.0）。
            meta: 未使用のメタデータ引数（互換性のために保持）。
        """
        try:
            if frames is None or self._closed:
                return
            arr = np.asarray(frames, dtype=np.float32)
            if arr.size == 0:
                return
            arr = np.clip(arr, -1.0, 1.0)
            int16 = (arr * 32767.0).astype(np.int16)
            try:
                self._wf.writeframes(int16.tobytes())
            except Exception:
                pass
        except Exception:
            pass

    def stop(self):
        """録音を停止し、ffmpeg で WAV を MP3 に変換するバックグラウンドスレッドを起動する。

        Returns:
            dict: 成功時は {"ok": True, "path": <出力パス>, "converting": True}、
                  失敗時は {"error": ...}。
        """
        try:
            if not self._closed:
                try:
                    self._wf.close()
                except Exception:
                    pass
                self._closed = True

            def _convert_and_cleanup(tmp_path, out_path):
                """一時 WAV ファイルを ffmpeg で MP3 に変換し、完了後に一時ファイルを削除する。"""
                try:
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        tmp_path,
                        "-codec:a",
                        "libmp3lame",
                        "-qscale:a",
                        "2",
                        out_path,
                    ]
                    proc = subprocess.run(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    if proc.returncode != 0:
                        logging.error(
                            "ffmpeg conversion failed: %s",
                            proc.stderr.decode(errors="replace"),
                        )
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                except FileNotFoundError:
                    logging.error(
                        "ffmpeg not found on PATH; cannot convert %s", tmp_path
                    )
                except Exception:
                    logging.exception("Error during ffmpeg conversion")

            th = threading.Thread(
                target=_convert_and_cleanup,
                args=(self._tmp_path, self._out_path),
                daemon=True,
            )
            th.start()
            return {"ok": True, "path": str(self._out_path), "converting": True}
        except Exception as e:
            return {"error": str(e)}


class Recorder:
    """Compatibility wrapper used by `Api`. Creates and registers a `RecorderSink` with
    the provided `SinkManager` and forwards `start`/`stop` calls.
    """

    def __init__(self, sink_mgr):
        """レコーダーを初期化する。

        Args:
            sink_mgr: フレームの配送管理に使用する SinkManager インスタンス。
        """
        self.sink_mgr = sink_mgr
        self._sid = None
        self._sink_obj = None
        self._stream = None
        self.last_input_rms = 0.0

    def is_recording(self):
        """現在録音中かどうかを返す。

        Returns:
            bool: 録音中の場合は True。
        """
        return self._sid is not None

    def start(self, target_path: str, samplerate: int, channels: int):
        """録音を開始する。

        RecorderSink を作成して SinkManager に登録し、入力ストリームを起動する。

        Args:
            target_path: 出力先ファイルパス。
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。

        Returns:
            dict: 成功時は {"ok": True}、失敗時は {"error": ...}。
        """
        if self.is_recording():
            return {"error": "already recording"}
        if not target_path:
            return {"error": "no target path"}
        try:
            rs = RecorderSink(target_path, samplerate=samplerate, channels=channels)
            resp = self.sink_mgr.register(rs)
            if resp.get("error") or not resp.get("id"):
                try:
                    rs.stop()
                except Exception:
                    pass
                return {"error": "failed to register recorder sink"}
            self._sid = resp.get("id")
            self._sink_obj = rs
            # create and start dedicated input stream that dispatches frames to sinks
            try:

                def _callback(indata, frames, time, status):
                    """入力フレームを RMS 計算後にシンクへ配送する sounddevice 入力コールバック。"""
                    try:
                        arr = indata.copy()
                        # use numpy here to compute RMS
                        a = np.asarray(arr, dtype=np.float32)
                        if a.ndim == 1:
                            a = a.reshape(-1, 1)
                        try:
                            self.last_input_rms = float(
                                np.sqrt(np.mean(np.square(a.astype(np.float64))))
                            )
                        except Exception:
                            pass
                        try:
                            self.sink_mgr.dispatch(arr)
                        except Exception:
                            pass
                    except Exception:
                        pass

                self._stream = audio_device.create_input_stream(
                    device=None,
                    samplerate=samplerate,
                    channels=channels,
                    dtype="float32",
                    callback=_callback,
                )
                self._stream.start()
            except Exception:
                # stream creation failure should not prevent recorder registration
                self._stream = None

            logging.getLogger(__name__).info(
                "Recorder started target=%s samplerate=%s channels=%s",
                target_path,
                samplerate,
                channels,
            )
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def stop(self):
        """録音を停止し、ストリームとシンクを後片付けする。

        Returns:
            dict: 成功時は RecorderSink.stop() の戻り値（MP3 変換情報を含む）、
                  録音していない場合は {"error": "not recording"}。
        """
        if not self.is_recording():
            return {"error": "not recording"}
        try:
            logging.getLogger(__name__).info("Recorder stopping")
            # stop dedicated input stream if present
            try:
                if self._stream is not None:
                    try:
                        self._stream.stop()
                    except Exception:
                        pass
                    try:
                        self._stream.close()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._stream = None

            sid = self._sid
            sink_obj = self._sink_obj
            try:
                self.sink_mgr.unregister(sid)
            except Exception:
                pass
            # after unregister, worker will have stopped; ensure sink closed and conversion started
            try:
                if sink_obj is not None:
                    return sink_obj.stop()
            except Exception:
                pass
            self._sid = None
            self._sink_obj = None
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
