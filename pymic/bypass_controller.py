import traceback
import logging

import numpy as np

from . import audio_device
from .pipeline import BypassPipeline


class BypassController:
    """Manages the input->pipeline->output stream and related lifecycle.

    This encapsulates the callback, pipeline creation, scaling, and sink
    dispatch so `Api` can delegate start/stop responsibilities.
    """

    def __init__(self, sink_mgr, collect_settings_callable):
        """バイパスコントローラーを初期化する。

        Args:
            sink_mgr: フレームを配送する SinkManager インスタンス。
            collect_settings_callable: 現在の設定スナップショットを返す呼び出し可能オブジェクト。
        """
        self.sink_mgr = sink_mgr
        self.collect_settings = collect_settings_callable
        self.stream = None
        self._pipeline = None
        self._current_samplerate = None
        self.last_input_rms = 0.0
        self.last_output_rms = 0.0
        self._transcribe_sink_id = None
        self.vad_window_ms = 30
        self.vad_silence_ms = 500
        # debug logging removed for production
        self._logger = logging.getLogger(__name__)

    def is_running(self):
        """バイパスストリームが現在動作中かどうかを返す。

        Returns:
            bool: ストリームが起動中の場合は True。
        """
        return self.stream is not None

    def start(self, selected_input, selected_output):
        """指定デバイスでバイパスストリームを開始する。

        入力デバイスの音声をパイプラインで処理して出力デバイスへ流す全二重ストリームを起動する。

        Args:
            selected_input: 入力デバイスのインデックス。
            selected_output: 出力デバイスのインデックス。

        Returns:
            dict: 成功時は {"running": True}、失敗時は {"error": ...}。
        """

        if not audio_device.is_available():
            self._logger.error("sounddevice library not available")
            return {"error": "sounddevice not available"}

        if self.stream is not None:
            return {"error": "already running"}

        if selected_input is None or selected_output is None:
            return {"error": "input or output device not selected"}

        try:
            in_dev = audio_device.query_device(selected_input)
            out_dev = audio_device.query_device(selected_output)

            samplerate = int(
                in_dev.get("default_samplerate")
                or out_dev.get("default_samplerate")
                or 44100
            )
            in_channels = int(in_dev.get("max_input_channels") or 1)
            out_channels = int(out_dev.get("max_output_channels") or 1)
            channels = max(in_channels, out_channels)

            settings_snapshot = self.collect_settings()
            self._pipeline = BypassPipeline(
                samplerate=samplerate, channels=channels, settings=settings_snapshot
            )
            try:
                self._pipeline.start()
            except Exception:
                self._logger.exception("Failed to start pipeline")

            # remember samplerate for sinks (VAD/transcribe)
            self._current_samplerate = samplerate

            # Ensure selected input/output are compatible (same host API). If not,
            # attempt to pick a compatible pair from available hostapis.
            try:
                devs = audio_device.query_devices()
                hostapis = audio_device.query_hostapis()
                compatible = False
                for h in hostapis or []:
                    h_devs = h.get("devices") or []
                    if (
                        isinstance(h_devs, (list, tuple))
                        and selected_input in h_devs
                        and selected_output in h_devs
                    ):
                        compatible = True
                        break
                if not compatible:
                    # find a hostapi that has at least one input and one output device
                    picked_in = None
                    picked_out = None
                    for h in hostapis or []:
                        for idx in (h.get("devices") or []):
                            try:
                                d = devs[int(idx)]
                            except Exception:
                                continue
                            if picked_in is None and d.get("max_input_channels", 0) > 0:
                                picked_in = int(idx)
                            if picked_out is None and d.get("max_output_channels", 0) > 0:
                                picked_out = int(idx)
                            if picked_in is not None and picked_out is not None:
                                break
                        if picked_in is not None and picked_out is not None:
                            break
                    if picked_in is not None and picked_out is not None:
                        # override selection with compatible pair
                        try:
                            selected_input = picked_in
                            selected_output = picked_out
                        except Exception:
                            pass
                    else:
                        # leave selections as-is; let create_stream raise a clear error
                        pass
            except Exception:
                pass

            def _scale_buffer(buf, target_dtype):
                """バッファを target_dtype にスケーリングして変換する。整数型への変換時はクリッピングを行う。"""
                if np.issubdtype(buf.dtype, np.integer) or np.issubdtype(
                    target_dtype, np.integer
                ):
                    tgt_info = (
                        np.iinfo(target_dtype)
                        if np.issubdtype(target_dtype, np.integer)
                        else np.iinfo(buf.dtype)
                    )
                    denom = float(max(abs(tgt_info.min), abs(tgt_info.max)))
                    f = buf.astype(np.float32) / denom
                    f = np.clip(f, -1.0, 1.0 - (1.0 / denom))
                    return np.rint(f * denom).astype(target_dtype)
                else:
                    f = buf.astype(np.float32)
                    f = np.clip(f, -1.0, 1.0)
                    return f.astype(target_dtype)

            def callback(indata, outdata, frames, time, status):
                """入力を正規化してパイプライン処理し、出力バッファに書き込む sounddevice コールバック。"""
                if status:
                    self._logger.warning("Stream callback status: %s", status)
                try:
                    # normalize input
                    if np.issubdtype(indata.dtype, np.integer):
                        info = np.iinfo(indata.dtype)
                        denom = float(max(abs(info.min), abs(info.max)))
                        fdata = indata.astype(np.float32) / denom
                    else:
                        fdata = indata.astype(np.float32)

                    fdata = np.asarray(fdata)
                    if fdata.ndim == 1:
                        fdata = fdata.reshape(-1, 1)

                    # update input level
                    try:
                        self.last_input_rms = float(
                            np.sqrt(np.mean(np.square(fdata.astype(np.float64))))
                        )
                    except Exception:
                        pass


                    # process via pipeline
                    try:
                        if self._pipeline is not None:
                            out_frames = self._pipeline.process_frame(fdata)
                        else:
                            out_frames = fdata
                    except Exception:
                        out_frames = fdata


                    # update output level from pipeline if available
                    try:
                        if self._pipeline is not None:
                            lv = self._pipeline.get_levels()
                            self.last_input_rms = float(
                                lv.get("input_rms", self.last_input_rms)
                            )
                            self.last_output_rms = float(
                                lv.get("output_rms", self.last_output_rms)
                            )
                    except Exception:
                        try:
                            self.last_output_rms = float(
                                np.sqrt(
                                    np.mean(np.square(out_frames.astype(np.float64)))
                                )
                            )
                        except Exception:
                            pass

                    # levels updated; no debug logging

                    # dispatch to sinks (non-blocking)
                    try:
                        if out_frames.size > 0:
                            self.sink_mgr.dispatch(out_frames)
                    except Exception:
                        self._logger.exception("Error dispatching to sinks")

                    # write to outdata with simple scaling
                    try:
                        if out_frames.shape[1] == 1 and outdata.shape[1] > 1:
                            out_ch_dtype = outdata.dtype
                            outdata[:, 0] = _scale_buffer(
                                out_frames[:, 0], out_ch_dtype
                            )
                            if outdata.shape[1] > 1:
                                outdata[:, 1:] = 0
                        else:
                            nch = min(out_frames.shape[1], outdata.shape[1])
                            for ch in range(nch):
                                out_ch_dtype = outdata.dtype
                                outdata[:, ch] = _scale_buffer(
                                    out_frames[:, ch], out_ch_dtype
                                )
                            if outdata.shape[1] > nch:
                                outdata[:, nch:] = 0
                    except Exception:
                        outdata.fill(0)
                except Exception:
                    outdata.fill(0)

            self.stream = audio_device.create_stream(
                device=(selected_input, selected_output),
                samplerate=samplerate,
                channels=channels,
                callback=callback,
            )
            self.stream.start()
            return {"running": True}
        except Exception as e:
            self.stream = None
            self._logger.exception("Bypass start() exception: %s", str(e))
            return {"error": str(e), "trace": traceback.format_exc()}

    def stop(self):
        """バイパスストリームとパイプラインを停止し、レベル値をリセットする。

        Returns:
            dict: 成功時は {"running": False}、起動していない場合は {"error": "not running"}。
        """
        if self.stream is None:
            return {"error": "not running"}
        try:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

            # stop pipeline if present
            try:
                if self._pipeline is not None:
                    try:
                        self._pipeline.stop()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._pipeline = None

            # clear measured levels when bypass stops
            try:
                self.last_input_rms = 0.0
            except Exception:
                pass
            try:
                self.last_output_rms = 0.0
            except Exception:
                pass
            try:
                self._current_samplerate = None
            except Exception:
                pass

            return {"running": False}
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    # Transcription / VAD control moved here to centralize numpy usage
    def set_transcribe_enabled(self, enabled: bool):
        """VAD（音声区間検出）・文字起こし機能を有効または無効にする。

        有効化時は内部 VAD シンクを SinkManager に登録し、
        無効化時はシンクを登録解除する。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
        try:
            enabled = bool(enabled)
            self.vad_enabled = enabled
            # register/unregister internal VAD sink
            if enabled and self._transcribe_sink_id is None:

                def _vad_sink(frames_np: np.ndarray):
                    """音声区間検出（VAD）を行い、発話終了時にログ出力するシンク関数。"""
                    try:
                        if not hasattr(_vad_sink, "buf"):
                            _vad_sink.buf = bytearray()
                            _vad_sink.speech_buf = bytearray()
                            _vad_sink.in_speech = False
                            _vad_sink.silence_ms = 0
                            _vad_sink.frame_ms = int(self.vad_window_ms or 30)
                            _vad_sink.vad = None
                            try:
                                sr = int(self._current_samplerate or 16000)
                            except Exception:
                                sr = 16000
                            if sr in (8000, 16000, 32000, 48000):
                                try:
                                    import webrtcvad

                                    _vad_sink.vad = webrtcvad.Vad(2)
                                except Exception:
                                    _vad_sink.vad = None

                        sr = int(self._current_samplerate or 16000)

                        arr = np.asarray(frames_np, dtype=np.float32)
                        if arr.ndim > 1:
                            mono = np.mean(arr, axis=1)
                        else:
                            mono = arr
                        mono = np.clip(mono, -1.0, 1.0)
                        int16 = (mono * 32767.0).astype(np.int16)
                        bytes_chunk = int16.tobytes()

                        _vad_sink.buf.extend(bytes_chunk)

                        frame_bytes = int(sr * (_vad_sink.frame_ms / 1000.0) * 2)
                        while len(_vad_sink.buf) >= frame_bytes:
                            frame = bytes(_vad_sink.buf[:frame_bytes])
                            del _vad_sink.buf[:frame_bytes]
                            is_speech = False
                            if _vad_sink.vad is not None:
                                try:
                                    is_speech = _vad_sink.vad.is_speech(frame, sr)
                                except Exception:
                                    is_speech = False
                            else:
                                try:
                                    tmp = (
                                        np.frombuffer(frame, dtype=np.int16).astype(
                                            np.float32
                                        )
                                        / 32767.0
                                    )
                                    rms = float(
                                        np.sqrt(
                                            np.mean(np.square(tmp.astype(np.float64)))
                                        )
                                    )
                                    is_speech = rms > 1e-4
                                except Exception:
                                    is_speech = False

                            if is_speech:
                                _vad_sink.speech_buf.extend(frame)
                                _vad_sink.in_speech = True
                                _vad_sink.silence_ms = 0
                            else:
                                if _vad_sink.in_speech:
                                    _vad_sink.silence_ms += _vad_sink.frame_ms
                                    if _vad_sink.silence_ms >= int(
                                        self.vad_silence_ms or 500
                                    ):
                                        try:
                                            b = bytes(_vad_sink.speech_buf)
                                            arr16 = (
                                                np.frombuffer(b, dtype=np.int16).astype(
                                                    np.float32
                                                )
                                                / 32767.0
                                            )
                                            try:
                                                self._logger.info(
                                                    "VAD utterance end, samples=%s, sr=%s",
                                                    arr16.size,
                                                    sr,
                                                )
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                        _vad_sink.speech_buf = bytearray()
                                        _vad_sink.in_speech = False
                                        _vad_sink.silence_ms = 0
                                else:
                                    pass
                    except Exception:
                        pass

                resp = self.sink_mgr.register(_vad_sink)
                if resp and resp.get("ok"):
                    self._transcribe_sink_id = resp.get("id")
            elif (not enabled) and self._transcribe_sink_id is not None:
                try:
                    self.sink_mgr.unregister(self._transcribe_sink_id)
                except Exception:
                    pass
                self._transcribe_sink_id = None
            return {"enabled": enabled}
        except Exception as e:
            return {"error": str(e)}

    def get_levels(self):
        """現在の入出力 RMS レベルを返す。

        パイプラインが存在する場合はパイプラインから取得し、
        そうでなければコントローラーが保持する値を返す。

        Returns:
            dict: {"input_rms": float, "output_rms": float}。
        """
        try:
            if self._pipeline is not None:
                return self._pipeline.get_levels()
        except Exception:
            pass
        return {
            "input_rms": float(self.last_input_rms or 0.0),
            "output_rms": float(self.last_output_rms or 0.0),
        }

    def apply_settings(self, settings_snapshot: dict):
        """Apply settings snapshot to the active pipeline if present."""
        try:
            if self._pipeline is not None:
                try:
                    self._pipeline.apply_settings(settings_snapshot or {})
                    return {"ok": True}
                except Exception as e:
                    return {"error": str(e)}
            return {"error": "no pipeline"}
        except Exception as e:
            return {"error": str(e)}
