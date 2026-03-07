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
        """RecorderSink を初期化し、一時 WAV ファイルを開く。

        Args:
            target_path: 最終的な MP3 出力先パス。
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
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
        """受信した float32 フレームを WAV ファイルに書き込む。

        Args:
            frames: 音声フレームの numpy 配列（float32）。
            meta: 未使用のメタデータ（将来の拡張用）。
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
        """録音を停止し、ffmpeg でバックグラウンド変換を開始する。

        Returns:
            成功時: {"ok": True, "path": str, "converting": True}
            失敗時: {"error": "エラーメッセージ"}
        """
        # close wav and start conversion thread
        try:
            if not self._closed:
                try:
                    self._wf.close()
                except Exception:
                    pass
                self._closed = True

            def _convert_and_cleanup(tmp_path, out_path):
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
        """Recorder を初期化する。

        Args:
            sink_mgr: フレームを配信する SinkManager インスタンス。
        """
        self.sink_mgr = sink_mgr
        self._sid = None
        self._sink_obj = None
        self._stream = None
        self.last_input_rms = 0.0

    def is_recording(self):
        """録音中かどうかを返す。"""
        return self._sid is not None

    def start(self, target_path: str, samplerate: int, channels: int):
        """録音を開始する。

        Args:
            target_path: 出力ファイルパス（MP3）。
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。

        Returns:
            成功時: {"ok": True}
            失敗時: {"error": "エラーメッセージ"}
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
        """録音を停止してシンクを解除し、WAV→MP3 変換を実行する。

        Returns:
            成功時: {"ok": True, "path": str, "converting": True}
            失敗時: {"error": "エラーメッセージ"}
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
