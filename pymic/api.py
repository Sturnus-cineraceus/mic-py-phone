import math
import importlib
import traceback

import numpy as np
import threading
import queue
import wave
import os
import subprocess
import uuid

import webrtcvad

from .settings_manager import SettingsManager
from .sink_manager import SinkManager
from .recorder import Recorder

import sounddevice as sd
import noisereduce as nr
_pedalboard_mod = importlib.import_module("pedalboard._pedalboard")
Pedalboard = getattr(_pedalboard_mod, "Pedalboard", None)
PBNoiseGate = getattr(_pedalboard_mod, "NoiseGate", None)
PBCompressor = getattr(_pedalboard_mod, "Compressor", None)
PBHighpassFilter = getattr(_pedalboard_mod, "HighpassFilter", None)

HAS_PEDALBOARD = all(
    x is not None for x in (Pedalboard, PBNoiseGate, PBCompressor, PBHighpassFilter)
)


class Api:
    """Audio bypass API: list/select devices and start/stop a direct input->output passthrough."""

    def __init__(self):
        # recording state
        self._record_stream = None
        self.selected_input = None
        self.selected_output = None
        self.stream = None
        # last-measured levels (RMS, linear)
        self.last_input_rms = 0.0
        self.last_output_rms = 0.0
        # sink manager (extracted to reduce Api size)
        self._sink_mgr = SinkManager()
        # recorder helper handles WAV writing and ffmpeg conversion
        self._recorder = Recorder(self._sink_mgr)
        # volume as linear multiplier (1.0 = unchanged)
        self.volume = 1.0
        # Noise gate settings
        self.gate_enabled = False
        self.gate_threshold_db = -40.0
        self.gate_attack_ms = 10.0
        self.gate_release_ms = 100.0
        # High-pass filter settings
        self.hpf_enabled = False
        self.hpf_cutoff_hz = 80.0
        # Noise reduction (noisereduce) settings
        self.nr_enabled = False
        self.nr_strength = 0.9
        # Compressor settings
        self.comp_enabled = False
        self.comp_threshold_db = -24.0
        self.comp_ratio = 4.0
        self.comp_attack_ms = 10.0
        self.comp_release_ms = 120.0
        self.comp_makeup_db = 0.0
        # Post-gain de-hiss (white noise suppression) settings
        self.dehiss_enabled = True
        self.dehiss_lpf_hz = 9000.0
        self.dehiss_threshold_db = -58.0
        self.dehiss_strength = 0.65
        # Transcription / VAD settings
        self.transcribe_enabled = False
        # simple VAD experiment params
        self.vad_window_ms = 30
        self.vad_silence_ms = 500
        # sink id for internal VAD/transcription sink
        self._transcribe_sink_id = None
        # Settings persistence
        self._settings_manager = SettingsManager()
        self._apply_settings(self._settings_manager.load())
        # current stream samplerate (set when bypass starts)
        self._current_samplerate = None

    def _to_strength01(self, value):
        try:
            v = float(value)
            if v > 1.0:
                v = v / 100.0
            return max(0.0, min(1.0, v))
        except Exception:
            return 0.5

    def _get_gate_strength(self):
        return max(0.0, min(1.0, (float(self.gate_threshold_db) + 70.0) / 45.0))

    def _get_hpf_strength(self):
        return max(0.0, min(1.0, (float(self.hpf_cutoff_hz) - 50.0) / 150.0))

    def _get_comp_strength(self):
        return max(0.0, min(1.0, (float(self.comp_ratio) - 2.0) / 6.0))

    def _collect_settings(self) -> dict:
        """Collect current API state into a settings dict."""
        gain_db = 0.0
        if self.volume > 0:
            gain_db = 20.0 * math.log10(float(self.volume))
        return {
            "gain_db": gain_db,
            "input_device": self.selected_input,
            "output_device": self.selected_output,
            "gate": {
                "enabled": bool(self.gate_enabled),
                "threshold_db": float(self.gate_threshold_db),
                "attack_ms": float(self.gate_attack_ms),
                "release_ms": float(self.gate_release_ms),
            },
            "hpf": {
                "enabled": bool(self.hpf_enabled),
                "cutoff_hz": float(self.hpf_cutoff_hz),
            },
            "nr": {
                "enabled": bool(self.nr_enabled),
                "strength": float(self.nr_strength),
            },
            "compressor": {
                "enabled": bool(self.comp_enabled),
                "threshold_db": float(self.comp_threshold_db),
                "ratio": float(self.comp_ratio),
                "attack_ms": float(self.comp_attack_ms),
                "release_ms": float(self.comp_release_ms),
                "makeup_db": float(self.comp_makeup_db),
            },
            "dehiss": {
                "enabled": bool(self.dehiss_enabled),
                "strength": float(self.dehiss_strength),
                "threshold_db": float(self.dehiss_threshold_db),
                "lpf_hz": float(self.dehiss_lpf_hz),
            },
        }

    def _apply_settings(self, settings: dict) -> None:
        """Apply a settings dict to the current API state."""
        if not isinstance(settings, dict):
            return
        try:
            gain_db = float(settings.get("gain_db", 0.0))
            self.volume = float(10.0 ** (gain_db / 20.0))
        except Exception:
            pass
        self.selected_input = settings.get("input_device", self.selected_input)
        self.selected_output = settings.get("output_device", self.selected_output)
        gate = settings.get("gate", {})
        if isinstance(gate, dict):
            self.gate_enabled = bool(gate.get("enabled", self.gate_enabled))
            try:
                self.gate_threshold_db = float(
                    gate.get("threshold_db", self.gate_threshold_db)
                )
            except Exception:
                pass
            try:
                self.gate_attack_ms = float(gate.get("attack_ms", self.gate_attack_ms))
            except Exception:
                pass
            try:
                self.gate_release_ms = float(
                    gate.get("release_ms", self.gate_release_ms)
                )
            except Exception:
                pass
        hpf = settings.get("hpf", {})
        if isinstance(hpf, dict):
            self.hpf_enabled = bool(hpf.get("enabled", self.hpf_enabled))
            try:
                self.hpf_cutoff_hz = float(hpf.get("cutoff_hz", self.hpf_cutoff_hz))
            except Exception:
                pass
        nr = settings.get("nr", {})
        if isinstance(nr, dict):
            self.nr_enabled = bool(nr.get("enabled", self.nr_enabled))
            try:
                self.nr_strength = float(nr.get("strength", self.nr_strength))
            except Exception:
                pass
        comp = settings.get("compressor", {})
        if isinstance(comp, dict):
            self.comp_enabled = bool(comp.get("enabled", self.comp_enabled))
            try:
                self.comp_threshold_db = float(
                    comp.get("threshold_db", self.comp_threshold_db)
                )
            except Exception:
                pass
            try:
                self.comp_ratio = float(comp.get("ratio", self.comp_ratio))
            except Exception:
                pass
            try:
                self.comp_attack_ms = float(comp.get("attack_ms", self.comp_attack_ms))
            except Exception:
                pass
            try:
                self.comp_release_ms = float(
                    comp.get("release_ms", self.comp_release_ms)
                )
            except Exception:
                pass
            try:
                self.comp_makeup_db = float(comp.get("makeup_db", self.comp_makeup_db))
            except Exception:
                pass
        dehiss = settings.get("dehiss", {})
        if isinstance(dehiss, dict):
            self.dehiss_enabled = bool(dehiss.get("enabled", self.dehiss_enabled))
            try:
                self.dehiss_strength = float(
                    dehiss.get("strength", self.dehiss_strength)
                )
            except Exception:
                pass
            try:
                self.dehiss_threshold_db = float(
                    dehiss.get("threshold_db", self.dehiss_threshold_db)
                )
            except Exception:
                pass
            try:
                self.dehiss_lpf_hz = float(dehiss.get("lpf_hz", self.dehiss_lpf_hz))
            except Exception:
                pass

    # Settings persistence API (called from JavaScript)

    def save_settings(self):
        """Save current settings to the user data directory."""
        try:
            settings = self._collect_settings()
            self._settings_manager.save(settings)
            return {
                "ok": True,
                "path": str(self._settings_manager.settings_path),
            }
        except Exception as e:
            return {"error": str(e)}

    def load_settings(self):
        """Load settings from disk and apply them."""
        try:
            settings = self._settings_manager.load()
            self._apply_settings(settings)
            return {"ok": True, "settings": settings}
        except Exception as e:
            return {"error": str(e)}

    def reset_settings(self):
        """Reset all settings to defaults and return them."""
        try:
            defaults = self._settings_manager.reset_defaults()
            self._apply_settings(defaults)
            return {"ok": True, "settings": defaults}
        except Exception as e:
            return {"error": str(e)}

    def get_settings_path(self):
        """Return the path where settings are stored."""
        return {"path": str(self._settings_manager.settings_path)}

    def get_easy_settings(self):
        try:
            return {
                "engine": "pedalboard" if Pedalboard is not None else "native",
                "nr": {
                    "enabled": bool(self.nr_enabled),
                    "strength": float(self.nr_strength),
                },
                "gate": {
                    "enabled": bool(self.gate_enabled),
                    "strength": float(self._get_gate_strength()),
                },
                "hpf": {
                    "enabled": bool(self.hpf_enabled),
                    "strength": float(self._get_hpf_strength()),
                },
                "compressor": {
                    "enabled": bool(self.comp_enabled),
                    "strength": float(self._get_comp_strength()),
                },
                "final_noise": {
                    "enabled": bool(self.dehiss_enabled),
                    "strength": float(self.dehiss_strength),
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def get_audio_devices(self):
        if sd is None:
            return {"error": "sounddevice not available"}
        try:
            hostapis = sd.query_hostapis()
            devs = sd.query_devices()

            try:
                default_dev = sd.default.device
                if default_dev is not None:
                    try:
                        default_dev = list(default_dev)
                    except Exception:
                        try:
                            default_dev = [int(default_dev)]
                        except Exception:
                            default_dev = None
            except Exception:
                default_dev = None

            devices = []
            for i, d in enumerate(devs):
                devices.append(
                    {
                        "index": i,
                        "name": d.get("name"),
                        "max_input_channels": d.get("max_input_channels"),
                        "max_output_channels": d.get("max_output_channels"),
                        "default_samplerate": d.get("default_samplerate"),
                    }
                )

            hostapi_list = []
            for h in hostapis:
                h_name = h.get("name")
                h_devices = []
                for idx in h.get("devices", []):
                    if isinstance(idx, int) and 0 <= idx < len(devices):
                        h_devices.append(devices[idx])
                hostapi_list.append({"name": h_name, "devices": h_devices})

            # Filter to WASAPI host APIs only (case-insensitive). If none are present,
            # return an error because the UI should allow selection only for WASAPI.
            wasapi_list = [
                h
                for h in hostapi_list
                if isinstance(h.get("name"), str) and "WASAPI" in h.get("name").upper()
            ]
            if not wasapi_list:
                return {"error": "WASAPI host API not available on this system"}

            # Flatten devices from WASAPI hostapis and remove duplicates by index
            seen = set()
            wasapi_devices = []
            for h in wasapi_list:
                for d in h.get("devices", []):
                    if d and d.get("index") not in seen:
                        seen.add(d.get("index"))
                        wasapi_devices.append(d)

            return {
                "devices": wasapi_devices,
                "hostapis": wasapi_list,
                "default_device": default_dev,
            }
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    # --- Recording / Save dialog API ---
    def open_save_file_dialog(self):
        try:
            # Use tkinter filedialog to show native save dialog
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            try:
                # put dialog on top
                root.call("wm", "attributes", ".", "-topmost", True)
            except Exception:
                pass
            path = filedialog.asksaveasfilename(
                defaultextension=".mp3",
                filetypes=[
                    ("MP3 files", "*.mp3"),
                    ("WAV files", "*.wav"),
                    ("All files", "*.*"),
                ],
            )
            try:
                root.destroy()
            except Exception:
                pass
            if not path:
                return {"path": None}
            return {"path": str(path)}
        except Exception as e:
            return {"error": str(e)}

    def start_record(self, target_path: str):
        """Begin recording from the selected input device and stream samples to
        a temporary WAV file in the same directory as `target_path`.
        The final MP3 will be produced when `stop_record` is called.
        """
        if sd is None:
            return {"error": "sounddevice not available"}
        if self._recorder.is_recording() or self._record_stream is not None:
            return {"error": "already recording"}
        if not target_path:
            return {"error": "no target path"}

        try:
            dev = sd.query_devices(self.selected_input)
            samplerate = int(dev.get("default_samplerate") or 44100)
            channels = int(dev.get("max_input_channels") or 1)

            # register recorder sink which will create a temporary wav and write frames
            resp = self._recorder.start(target_path, samplerate, channels)
            if resp.get("error"):
                return resp

            def callback(indata, frames, time, status):
                try:
                    arr = indata.copy()
                    try:
                        a = np.asarray(arr, dtype=np.float32)
                        if a.ndim == 1:
                            a = a.reshape(-1, 1)
                        self.last_input_rms = float(
                            np.sqrt(np.mean(np.square(a.astype(np.float64))))
                        )
                    except Exception:
                        pass
                    try:
                        self._dispatch_sinks(arr)
                    except Exception:
                        pass
                except Exception:
                    pass

            if self.stream is None:
                stream = sd.InputStream(
                    device=self.selected_input,
                    samplerate=samplerate,
                    channels=channels,
                    dtype="float32",
                    callback=callback,
                )
                stream.start()
                self._record_stream = stream

            return {"ok": True}
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    def stop_record(self):
        """Stop recording, convert temporary WAV -> MP3 using ffmpeg, and
        remove the temporary file. Returns path on success.
        """
        if (not self._recorder.is_recording()) and self._record_stream is None:
            return {"error": "not recording"}
        try:
            had_record_stream = self._record_stream is not None
            try:
                if self._record_stream is not None:
                    if hasattr(self._record_stream, "stop"):
                        try:
                            self._record_stream.stop()
                        except Exception:
                            pass
                    if hasattr(self._record_stream, "close"):
                        try:
                            self._record_stream.close()
                        except Exception:
                            pass
            except Exception:
                pass

            # clear reference to dedicated record stream
            self._record_stream = None

            # stop recorder (unregister sink, convert file)
            try:
                resp = self._recorder.stop()
            except Exception as e:
                resp = {"error": str(e)}

            # clear input level if we stopped a dedicated input stream
            try:
                if had_record_stream:
                    self.last_input_rms = 0.0
            except Exception:
                pass

            return resp
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    def set_input_device(self, index):
        try:
            idx = int(index)
            self.selected_input = idx
            return {"selected_input": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def set_output_device(self, index):
        try:
            idx = int(index)
            self.selected_output = idx
            return {"selected_output": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def get_selected_devices(self):
        return {"input": self.selected_input, "output": self.selected_output}

    def get_gain_db(self):
        try:
            # avoid log10(0)
            if self.volume <= 0:
                gain_db = -999.0
            else:
                gain_db = 20.0 * math.log10(float(self.volume))
            return {"gain_db": float(gain_db)}
        except Exception as e:
            return {"error": str(e)}

    def get_levels(self):
        """Return recent input/output levels (linear RMS and dB)."""
        try:
            in_rms = float(self.last_input_rms or 0.0)
            out_rms = float(self.last_output_rms or 0.0)
            in_db = 20.0 * math.log10(in_rms + 1e-12)
            out_db = 20.0 * math.log10(out_rms + 1e-12)
            return {
                "input_rms": in_rms,
                "output_rms": out_rms,
                "input_db": float(in_db),
                "output_db": float(out_db),
            }
        except Exception as e:
            return {"error": str(e)}

    # Sink management -------------------------------------------------
    def register_sink(self, sink_callable):
        """Register a sink callable that will be invoked with processed frames.

        The callable will be called as sink(frames: np.ndarray).
        Returns an integer sink id which can be used to unregister.
        """
        try:
            return self._sink_mgr.register(sink_callable)
        except Exception as e:
            return {"error": str(e)}

    def unregister_sink(self, sid):
        try:
            return self._sink_mgr.unregister(sid)
        except Exception as e:
            return {"error": str(e)}

    def _dispatch_sinks(self, frames):
        """Call all registered sinks with a copy of frames (non-blocking).

        Exceptions in sinks are caught and ignored to avoid destabilizing the
        audio callback.
        """
        try:
            return self._sink_mgr.dispatch(frames)
        except Exception:
            pass

    # Transcription toggle and VAD helper (experiment)
    def set_transcribe_enabled(self, enabled: bool):
        try:
            self.transcribe_enabled = bool(enabled)
            # register/unregister internal VAD sink
            if self.transcribe_enabled and self._transcribe_sink_id is None:
                # register a sink that performs VAD-based segmentation and emits utterances
                def _vad_sink(frames_np: np.ndarray):
                    try:
                        # closure-local state
                        if not hasattr(_vad_sink, "buf"):
                            _vad_sink.buf = bytearray()
                            _vad_sink.speech_buf = bytearray()
                            _vad_sink.in_speech = False
                            _vad_sink.silence_ms = 0
                            _vad_sink.frame_ms = int(self.vad_window_ms or 30)
                            _vad_sink.vad = None
                            # create webrtcvad instance if available and samplerate supported
                            try:
                                sr = int(self._current_samplerate or 16000)
                            except Exception:
                                sr = 16000
                            if webrtcvad is not None and sr in (
                                8000,
                                16000,
                                32000,
                                48000,
                            ):
                                try:
                                    _vad_sink.vad = webrtcvad.Vad(2)
                                except Exception:
                                    _vad_sink.vad = None

                        # determine samplerate
                        sr = int(self._current_samplerate or 16000)

                        # convert incoming frames to mono int16 bytes
                        arr = np.asarray(frames_np, dtype=np.float32)
                        if arr.ndim > 1:
                            mono = np.mean(arr, axis=1)
                        else:
                            mono = arr
                        mono = np.clip(mono, -1.0, 1.0)
                        int16 = (mono * 32767.0).astype(np.int16)
                        bytes_chunk = int16.tobytes()

                        # accumulate
                        _vad_sink.buf.extend(bytes_chunk)

                        # frame size in bytes for desired frame_ms
                        frame_bytes = int(sr * (_vad_sink.frame_ms / 1000.0) * 2)
                        # process full frames
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
                                    # fallback: energy-based decision
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
                                        # utterance ended — send to transcription placeholder
                                        try:
                                            # convert speech_buf to numpy float array for downstream use
                                            b = bytes(_vad_sink.speech_buf)
                                            arr16 = (
                                                np.frombuffer(b, dtype=np.int16).astype(
                                                    np.float32
                                                )
                                                / 32767.0
                                            )
                                            # Here we would call Whisper or other ASR; for now print debug info
                                            print(
                                                f"[VAD] Utterance end, samples={arr16.size}, sr={sr}"
                                            )
                                        except Exception:
                                            pass
                                        _vad_sink.speech_buf = bytearray()
                                        _vad_sink.in_speech = False
                                        _vad_sink.silence_ms = 0
                                else:
                                    # remain in silence
                                    pass
                    except Exception:
                        pass

                resp = self.register_sink(_vad_sink)
                if resp and resp.get("ok"):
                    self._transcribe_sink_id = resp.get("id")
            elif (not self.transcribe_enabled) and self._transcribe_sink_id is not None:
                try:
                    self.unregister_sink(self._transcribe_sink_id)
                except Exception:
                    pass
                self._transcribe_sink_id = None
            return {"enabled": self.transcribe_enabled}
        except Exception as e:
            return {"error": str(e)}

    def set_gain_db(self, db):
        try:
            dbf = float(db)
            self.volume = float(10.0 ** (dbf / 20.0))
            return {"gain_db": dbf}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def get_gate_settings(self):
        try:
            return {
                "enabled": bool(self.gate_enabled),
                "threshold_db": float(self.gate_threshold_db),
                "attack_ms": float(self.gate_attack_ms),
                "release_ms": float(self.gate_release_ms),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_gate_enabled(self, enabled):
        try:
            self.gate_enabled = bool(enabled)
            return {"enabled": self.gate_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_threshold_db(self, db):
        try:
            self.gate_threshold_db = float(db)
            return {"threshold_db": self.gate_threshold_db}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_attack_ms(self, ms):
        try:
            self.gate_attack_ms = float(ms)
            return {"attack_ms": self.gate_attack_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_release_ms(self, ms):
        try:
            self.gate_release_ms = float(ms)
            return {"release_ms": self.gate_release_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.gate_threshold_db = -70.0 + (45.0 * s)
            self.gate_attack_ms = 8.0
            self.gate_release_ms = 120.0
            return {
                "strength": s,
                "threshold_db": self.gate_threshold_db,
            }
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    # High-pass filter API
    def get_hpf_settings(self):
        try:
            return {
                "enabled": bool(self.hpf_enabled),
                "cutoff_hz": float(self.hpf_cutoff_hz),
            }
        except Exception as e:
            return {"error": str(e)}

    # Noise reduction (noisereduce) API
    def get_nr_settings(self):
        try:
            return {
                "enabled": bool(self.nr_enabled),
                "strength": float(self.nr_strength),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_nr_enabled(self, enabled):
        try:
            self.nr_enabled = bool(enabled)
            return {"enabled": self.nr_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_nr_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.nr_strength = s
            return {"strength": self.nr_strength}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    # Final noise adjustment (post-gain de-hiss) API
    def get_final_noise_settings(self):
        try:
            return {
                "enabled": bool(self.dehiss_enabled),
                "strength": float(self.dehiss_strength),
                "threshold_db": float(self.dehiss_threshold_db),
                "lpf_hz": float(self.dehiss_lpf_hz),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_final_noise_enabled(self, enabled):
        try:
            self.dehiss_enabled = bool(enabled)
            return {"enabled": self.dehiss_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_final_noise_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.dehiss_strength = s
            # stronger setting: slightly higher threshold and lower LPF cutoff
            self.dehiss_threshold_db = -64.0 + (16.0 * s)
            self.dehiss_lpf_hz = 12000.0 - (5000.0 * s)
            return {
                "strength": self.dehiss_strength,
                "threshold_db": self.dehiss_threshold_db,
                "lpf_hz": self.dehiss_lpf_hz,
            }
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    # Compressor API
    def get_compressor_settings(self):
        try:
            return {
                "enabled": bool(self.comp_enabled),
                "threshold_db": float(self.comp_threshold_db),
                "ratio": float(self.comp_ratio),
                "attack_ms": float(self.comp_attack_ms),
                "release_ms": float(self.comp_release_ms),
                "makeup_db": float(self.comp_makeup_db),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_compressor_enabled(self, enabled):
        try:
            self.comp_enabled = bool(enabled)
            return {"enabled": self.comp_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_threshold_db(self, db):
        try:
            self.comp_threshold_db = float(db)
            return {"threshold_db": self.comp_threshold_db}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_ratio(self, ratio):
        try:
            r = float(ratio)
            if r < 1.0:
                return {"error": "ratio must be >= 1.0"}
            self.comp_ratio = r
            return {"ratio": self.comp_ratio}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_attack_ms(self, ms):
        try:
            m = float(ms)
            if m <= 0:
                return {"error": "attack must be > 0"}
            self.comp_attack_ms = m
            return {"attack_ms": self.comp_attack_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_release_ms(self, ms):
        try:
            m = float(ms)
            if m <= 0:
                return {"error": "release must be > 0"}
            self.comp_release_ms = m
            return {"release_ms": self.comp_release_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_makeup_db(self, db):
        try:
            self.comp_makeup_db = float(db)
            return {"makeup_db": self.comp_makeup_db}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.comp_ratio = 2.0 + (6.0 * s)
            self.comp_threshold_db = -12.0 - (20.0 * s)
            self.comp_attack_ms = 8.0
            self.comp_release_ms = 120.0
            self.comp_makeup_db = 0.0 + (4.0 * s)
            return {
                "strength": s,
                "ratio": self.comp_ratio,
                "threshold_db": self.comp_threshold_db,
                "makeup_db": self.comp_makeup_db,
            }
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_enabled(self, enabled):
        try:
            self.hpf_enabled = bool(enabled)
            return {"enabled": self.hpf_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_cutoff_hz(self, hz):
        try:
            hzf = float(hz)
            if hzf <= 0:
                return {"error": "cutoff must be > 0"}
            self.hpf_cutoff_hz = hzf
            return {"cutoff_hz": self.hpf_cutoff_hz}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.hpf_cutoff_hz = 50.0 + (150.0 * s)
            return {
                "strength": s,
                "cutoff_hz": self.hpf_cutoff_hz,
            }
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def get_transcribe_settings(self):
        try:
            return {
                "enabled": bool(self.transcribe_enabled),
                "vad_window_ms": int(self.vad_window_ms),
                "vad_silence_ms": int(self.vad_silence_ms),
            }
        except Exception as e:
            return {"error": str(e)}

    def is_running(self):
        return {"running": self.stream is not None}

    def start_bypass(self):
        if sd is None:
            return {"error": "sounddevice not available"}

        if self.stream is not None:
            return {"error": "already running"}

        if self.selected_input is None or self.selected_output is None:
            return {"error": "input or output device not selected"}

        try:
            in_dev = sd.query_devices(self.selected_input)
            out_dev = sd.query_devices(self.selected_output)

            samplerate = int(
                in_dev.get("default_samplerate")
                or out_dev.get("default_samplerate")
                or 44100
            )
            in_channels = in_dev.get("max_input_channels") or 1
            out_channels = out_dev.get("max_output_channels") or 1
            channels = max(in_channels, out_channels)

            # helper: scale a 1-D buffer into the requested target dtype safely
            def _scale_buffer(buf, target_dtype):
                # buf: 1-d ndarray
                # target_dtype: numpy dtype to cast final result into
                # Work in float32 normalized range to avoid repeated integer quantization loss.
                if np.issubdtype(buf.dtype, np.integer) or np.issubdtype(
                    target_dtype, np.integer
                ):
                    # Determine integer target bounds
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
                    # float path, assume -1.0..1.0 range
                    f = buf.astype(np.float32)
                    f = np.clip(f, -1.0, 1.0)
                    return f.astype(target_dtype)

            # prepare gate smoothing coefficients (used in closure)
            gate_attack_ms = float(self.gate_attack_ms)
            gate_release_ms = float(self.gate_release_ms)
            # compute per-sample smoothing alphas
            alpha_attack = math.exp(
                -1.0 / (max(samplerate * (gate_attack_ms / 1000.0), 1.0))
            )
            alpha_release = math.exp(
                -1.0 / (max(samplerate * (gate_release_ms / 1000.0), 1.0))
            )
            gate_attack_prev = gate_attack_ms
            gate_release_prev = gate_release_ms

            # envelope and gain state for closure
            env = 0.0
            gain_sm = 1.0

            # compressor envelope/gain state
            comp_env = 0.0
            comp_gain_sm = 1.0

            # HPF state: we'll implement a biquad HPF with per-channel state and allow runtime coefficient updates
            hpf_enabled = False
            hpf_cutoff_prev = None
            # biquad coeffs (normalized): b0,b1,b2,a1,a2
            b0 = b1 = b2 = a1 = a2 = 0.0
            # per-channel delay states
            hpf_x1 = np.zeros(channels, dtype=np.float32)
            hpf_x2 = np.zeros(channels, dtype=np.float32)
            hpf_y1 = np.zeros(channels, dtype=np.float32)
            hpf_y2 = np.zeros(channels, dtype=np.float32)

            # Post-gain de-hiss state: one-pole LPF + downward expander
            dehiss_lp_prev = np.zeros(channels, dtype=np.float32)
            dehiss_env = 0.0
            dehiss_gain_sm = 1.0

            # helper to ensure HPF state arrays are numpy arrays with required length
            def _ensure_hpf_state():
                nonlocal hpf_x1, hpf_x2, hpf_y1, hpf_y2
                try:
                    if not isinstance(hpf_x1, np.ndarray):
                        hpf_x1 = np.asarray(hpf_x1, dtype=np.float32)
                    if not isinstance(hpf_x2, np.ndarray):
                        hpf_x2 = np.asarray(hpf_x2, dtype=np.float32)
                    if not isinstance(hpf_y1, np.ndarray):
                        hpf_y1 = np.asarray(hpf_y1, dtype=np.float32)
                    if not isinstance(hpf_y2, np.ndarray):
                        hpf_y2 = np.asarray(hpf_y2, dtype=np.float32)

                    req = int(max(1, channels))
                    if hpf_x1.shape[0] < req:
                        hpf_x1 = np.pad(hpf_x1, (0, req - hpf_x1.shape[0]))
                    if hpf_x2.shape[0] < req:
                        hpf_x2 = np.pad(hpf_x2, (0, req - hpf_x2.shape[0]))
                    if hpf_y1.shape[0] < req:
                        hpf_y1 = np.pad(hpf_y1, (0, req - hpf_y1.shape[0]))
                    if hpf_y2.shape[0] < req:
                        hpf_y2 = np.pad(hpf_y2, (0, req - hpf_y2.shape[0]))
                except Exception:
                    hpf_x1 = np.zeros(channels, dtype=np.float32)
                    hpf_x2 = np.zeros(channels, dtype=np.float32)
                    hpf_y1 = np.zeros(channels, dtype=np.float32)
                    hpf_y2 = np.zeros(channels, dtype=np.float32)

            def _ensure_dehiss_state():
                nonlocal dehiss_lp_prev
                try:
                    if not isinstance(dehiss_lp_prev, np.ndarray):
                        dehiss_lp_prev = np.asarray(dehiss_lp_prev, dtype=np.float32)
                    req = int(max(1, channels))
                    if dehiss_lp_prev.shape[0] < req:
                        dehiss_lp_prev = np.pad(
                            dehiss_lp_prev, (0, req - dehiss_lp_prev.shape[0])
                        )
                except Exception:
                    dehiss_lp_prev = np.zeros(channels, dtype=np.float32)

            def callback(indata, outdata, frames, time, status):
                nonlocal hpf_enabled, hpf_cutoff_prev, b0, b1, b2, a1, a2
                nonlocal hpf_x1, hpf_x2, hpf_y1, hpf_y2
                nonlocal \
                    alpha_attack, \
                    alpha_release, \
                    gate_attack_prev, \
                    gate_release_prev
                nonlocal comp_env, comp_gain_sm
                nonlocal dehiss_lp_prev, dehiss_env, dehiss_gain_sm
                if status:
                    # ignore status, don't raise inside audio callback
                    pass
                try:
                    # normalize input to -1..1 float32 and ensure 2D shape (frames, channels)
                    if np.issubdtype(indata.dtype, np.integer):
                        info = np.iinfo(indata.dtype)
                        denom = float(max(abs(info.min), abs(info.max)))
                        fdata = indata.astype(np.float32) / denom
                    else:
                        fdata = indata.astype(np.float32)

                    # Ensure fdata is a numpy array and 2D (frames, channels)
                    fdata = np.asarray(fdata)
                    if fdata.ndim == 1:
                        fdata = fdata.reshape(-1, 1)

                    # update input RMS (before processing)
                    try:
                        self.last_input_rms = float(
                            np.sqrt(np.mean(np.square(fdata.astype(np.float64))))
                        )
                    except Exception:
                        pass

                    # Apply noise reduction if enabled and available.
                    # Use per-channel stationary spectral gating which works well for white noise.
                    try:
                        if bool(self.nr_enabled) and nr is not None and fdata.size > 0:
                            prop_decrease = float(max(0.0, min(1.0, self.nr_strength)))
                            nch = fdata.shape[1]
                            if nch == 1:
                                # reduce_noise expects 1D
                                out_nr = nr.reduce_noise(
                                    y=fdata[:, 0],
                                    sr=samplerate,
                                    stationary=True,
                                    prop_decrease=prop_decrease,
                                )
                                fdata = np.asarray(out_nr).reshape(-1, 1)
                            else:
                                # process each channel separately to avoid mixing
                                out_nr = np.empty_like(fdata)
                                for ch in range(nch):
                                    out_nr[:, ch] = nr.reduce_noise(
                                        y=fdata[:, ch],
                                        sr=samplerate,
                                        stationary=True,
                                        prop_decrease=prop_decrease,
                                    )
                                fdata = out_nr
                    except Exception:
                        # keep original data if noise reduction fails
                        pass

                    use_pedalboard = HAS_PEDALBOARD and (
                        bool(self.hpf_enabled)
                        or bool(self.gate_enabled)
                        or bool(self.comp_enabled)
                    )

                    if use_pedalboard and fdata.size > 0:
                        assert Pedalboard is not None
                        assert PBHighpassFilter is not None
                        assert PBNoiseGate is not None
                        assert PBCompressor is not None
                        plugins = []
                        if bool(self.hpf_enabled):
                            plugins.append(
                                PBHighpassFilter(
                                    cutoff_frequency_hz=float(self.hpf_cutoff_hz)
                                )
                            )
                        if bool(self.gate_enabled):
                            plugins.append(
                                PBNoiseGate(
                                    threshold_db=float(self.gate_threshold_db),
                                    ratio=10.0,
                                    attack_ms=float(self.gate_attack_ms),
                                    release_ms=float(self.gate_release_ms),
                                )
                            )
                        if bool(self.comp_enabled):
                            plugins.append(
                                PBCompressor(
                                    threshold_db=float(self.comp_threshold_db),
                                    ratio=float(self.comp_ratio),
                                    attack_ms=float(self.comp_attack_ms),
                                    release_ms=float(self.comp_release_ms),
                                )
                            )

                        if plugins:
                            board = Pedalboard(plugins)
                            pb_in = np.ascontiguousarray(fdata.T.astype(np.float32))
                            pb_out = board(pb_in, samplerate)
                            pb_out = np.asarray(pb_out, dtype=np.float32)
                            fdata = pb_out.T
                            if (
                                bool(self.comp_enabled)
                                and float(self.comp_makeup_db) != 0.0
                            ):
                                fdata = fdata * float(
                                    10.0 ** (float(self.comp_makeup_db) / 20.0)
                                )

                    # apply compressor (with soft-knee curve and smoothed gain)
                    if (
                        (not use_pedalboard)
                        and bool(self.comp_enabled)
                        and fdata.size > 0
                    ):
                        thr = float(self.comp_threshold_db)
                        ratio = max(1.0, float(self.comp_ratio))
                        attack_ms = max(0.1, float(self.comp_attack_ms))
                        release_ms = max(1.0, float(self.comp_release_ms))
                        makeup = float(10.0 ** (float(self.comp_makeup_db) / 20.0))

                        alpha_comp_attack = math.exp(
                            -1.0 / (max(samplerate * (attack_ms / 1000.0), 1.0))
                        )
                        alpha_comp_release = math.exp(
                            -1.0 / (max(samplerate * (release_ms / 1000.0), 1.0))
                        )

                        knee_db = 6.0

                        def _compress_db(x_db, threshold_db, ratio_v, knee_v):
                            if knee_v <= 0.0:
                                if x_db <= threshold_db:
                                    return x_db
                                return threshold_db + (x_db - threshold_db) / ratio_v
                            if (2.0 * (x_db - threshold_db)) < -knee_v:
                                return x_db
                            if abs(2.0 * (x_db - threshold_db)) <= knee_v:
                                return x_db + (
                                    (1.0 / ratio_v - 1.0)
                                    * ((x_db - threshold_db + knee_v / 2.0) ** 2)
                                    / (2.0 * knee_v)
                                )
                            return threshold_db + (x_db - threshold_db) / ratio_v

                        out_comp = np.empty_like(fdata)
                        for i in range(fdata.shape[0]):
                            s = fdata[i, :]
                            level = float(
                                np.sqrt(np.mean(np.square(s.astype(np.float64))))
                            )
                            if level > comp_env:
                                comp_env = (
                                    alpha_comp_attack * comp_env
                                    + (1.0 - alpha_comp_attack) * level
                                )
                            else:
                                comp_env = (
                                    alpha_comp_release * comp_env
                                    + (1.0 - alpha_comp_release) * level
                                )

                            in_db = 20.0 * math.log10(comp_env + 1e-12)
                            out_db = _compress_db(in_db, thr, ratio, knee_db)
                            gain_db = out_db - in_db
                            target_gain = float(10.0 ** (gain_db / 20.0))

                            if target_gain < comp_gain_sm:
                                alpha_g = alpha_comp_attack
                            else:
                                alpha_g = alpha_comp_release
                            comp_gain_sm = (
                                alpha_g * comp_gain_sm + (1.0 - alpha_g) * target_gain
                            )

                            out_comp[i, :] = s * comp_gain_sm * makeup

                        fdata = out_comp

                    # Ensure HPF state arrays are ready
                    _ensure_hpf_state()

                    # apply HPF per-sample if enabled (biquad). Recompute coeffs if cutoff changed.
                    cur_hpf_enabled = bool(self.hpf_enabled)
                    cur_cutoff = float(self.hpf_cutoff_hz)
                    if (
                        (not use_pedalboard)
                        and cur_hpf_enabled
                        and (not hpf_enabled or hpf_cutoff_prev != cur_cutoff)
                    ):
                        # compute biquad HPF coefficients (RBJ cookbook), Q=0.707
                        fs = float(samplerate)
                        f0 = max(1.0, min(cur_cutoff, fs / 2.0 - 1.0))
                        Q = 0.7071
                        omega = 2.0 * math.pi * f0 / fs
                        sn = math.sin(omega)
                        cs = math.cos(omega)
                        alpha_b = sn / (2.0 * Q)
                        b0_raw = (1 + cs) / 2.0 * 1.0
                        b1_raw = -(1 + cs)
                        b2_raw = (1 + cs) / 2.0
                        a0_raw = 1.0 + alpha_b
                        a1_raw = -2.0 * cs
                        a2_raw = 1.0 - alpha_b
                        b0 = b0_raw / a0_raw
                        b1 = b1_raw / a0_raw
                        b2 = b2_raw / a0_raw
                        a1 = a1_raw / a0_raw
                        a2 = a2_raw / a0_raw
                        hpf_enabled = True
                        hpf_cutoff_prev = cur_cutoff
                    elif (not use_pedalboard) and (not cur_hpf_enabled):
                        hpf_enabled = False

                    if (not use_pedalboard) and hpf_enabled:
                        nch = min(fdata.shape[1], channels)
                        out_f = np.empty_like(fdata)
                        # per-sample per-channel biquad
                        for i in range(fdata.shape[0]):
                            for ch in range(nch):
                                x = float(fdata[i, ch])
                                y = (
                                    b0 * x
                                    + b1 * hpf_x1[ch]
                                    + b2 * hpf_x2[ch]
                                    - a1 * hpf_y1[ch]
                                    - a2 * hpf_y2[ch]
                                )
                                out_f[i, ch] = y
                                hpf_x2[ch] = hpf_x1[ch]
                                hpf_x1[ch] = x
                                hpf_y2[ch] = hpf_y1[ch]
                                hpf_y1[ch] = y
                            if fdata.shape[1] > nch:
                                out_f[i, nch:] = fdata[i, nch:]
                        fdata = out_f

                    # apply noise gate decision based on RMS envelope (soft knee + smoothed gain)
                    if (not use_pedalboard) and bool(self.gate_enabled):
                        nonlocal env, gain_sm
                        cur_gate_attack_ms = max(0.1, float(self.gate_attack_ms))
                        cur_gate_release_ms = max(1.0, float(self.gate_release_ms))
                        if (
                            cur_gate_attack_ms != gate_attack_prev
                            or cur_gate_release_ms != gate_release_prev
                        ):
                            alpha_attack = math.exp(
                                -1.0
                                / (
                                    max(
                                        samplerate * (cur_gate_attack_ms / 1000.0),
                                        1.0,
                                    )
                                )
                            )
                            alpha_release = math.exp(
                                -1.0
                                / (
                                    max(
                                        samplerate * (cur_gate_release_ms / 1000.0),
                                        1.0,
                                    )
                                )
                            )
                            gate_attack_prev = cur_gate_attack_ms
                            gate_release_prev = cur_gate_release_ms
                        # compute RMS across channels
                        if fdata.size == 0:
                            rms = 0.0
                        else:
                            rms = float(
                                np.sqrt(np.mean(np.square(fdata.astype(np.float64))))
                            )
                        # update envelope smoothing
                        if rms > env:
                            env = alpha_attack * env + (1.0 - alpha_attack) * rms
                        else:
                            env = alpha_release * env + (1.0 - alpha_release) * rms
                        env_db = 20.0 * math.log10(env + 1e-12)
                        # soft knee parameters
                        knee_db = 12.0
                        thr = float(self.gate_threshold_db)
                        if env_db >= thr:
                            target_gain = 1.0
                        elif env_db <= (thr - knee_db):
                            target_gain = 0.0
                        else:
                            # linear interpolation in dB domain
                            t = (env_db - (thr - knee_db)) / knee_db
                            target_gain = max(0.0, min(1.0, t))
                        # choose attack/release for gain smoothing
                        if target_gain > gain_sm:
                            alpha_g = alpha_attack
                        else:
                            alpha_g = alpha_release
                        gain_sm = alpha_g * gain_sm + (1.0 - alpha_g) * target_gain
                        # apply smoothed gain
                        if gain_sm <= 0.001:
                            # if muted, still dispatch silence to sinks if active
                            try:
                                outdata.fill(0)
                                if self._sink_mgr and self._sink_mgr.has_sinks():
                                    zeros = np.zeros_like(fdata)
                                    try:
                                        self._dispatch_sinks(zeros)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            return
                        fdata = fdata * float(gain_sm)

                    # post stage: explicit gain then de-hiss to reduce amplified white noise
                    if fdata.size > 0:
                        fdata = fdata * float(self.volume)
                        fdata = np.clip(fdata, -1.0, 1.0)

                    if bool(self.dehiss_enabled) and fdata.size > 0:
                        _ensure_dehiss_state()
                        fs = float(samplerate)
                        cutoff = max(
                            500.0, min(float(self.dehiss_lpf_hz), fs / 2.0 - 50.0)
                        )
                        alpha_lp = 1.0 - math.exp(-2.0 * math.pi * cutoff / fs)
                        nch = min(fdata.shape[1], channels)

                        # one-pole low-pass to tame hiss-heavy upper band
                        for i in range(fdata.shape[0]):
                            for ch in range(nch):
                                x = float(fdata[i, ch])
                                prev = float(dehiss_lp_prev[ch])
                                y = prev + alpha_lp * (x - prev)
                                dehiss_lp_prev[ch] = y
                                fdata[i, ch] = y

                        # downward expander when level is near noise floor
                        rms_post = float(
                            np.sqrt(np.mean(np.square(fdata.astype(np.float64))))
                        )
                        alpha_env_attack = math.exp(
                            -1.0 / (max(fs * (8.0 / 1000.0), 1.0))
                        )
                        alpha_env_release = math.exp(
                            -1.0 / (max(fs * (140.0 / 1000.0), 1.0))
                        )
                        if rms_post > dehiss_env:
                            dehiss_env = (
                                alpha_env_attack * dehiss_env
                                + (1.0 - alpha_env_attack) * rms_post
                            )
                        else:
                            dehiss_env = (
                                alpha_env_release * dehiss_env
                                + (1.0 - alpha_env_release) * rms_post
                            )

                        thr_lin = float(
                            10.0 ** (float(self.dehiss_threshold_db) / 20.0)
                        )
                        strength = max(0.0, min(1.0, float(self.dehiss_strength)))
                        if dehiss_env >= thr_lin:
                            target_post_gain = 1.0
                        else:
                            rel = dehiss_env / max(thr_lin, 1e-9)
                            floor_gain = max(0.15, 1.0 - 0.9 * strength)
                            target_post_gain = floor_gain + (1.0 - floor_gain) * rel
                            target_post_gain = max(
                                floor_gain, min(1.0, target_post_gain)
                            )

                        alpha_post_open = math.exp(
                            -1.0 / (max(fs * (8.0 / 1000.0), 1.0))
                        )
                        alpha_post_close = math.exp(
                            -1.0 / (max(fs * (220.0 / 1000.0), 1.0))
                        )
                        if target_post_gain > dehiss_gain_sm:
                            alpha_pg = alpha_post_open
                        else:
                            alpha_pg = alpha_post_close
                        dehiss_gain_sm = (
                            alpha_pg * dehiss_gain_sm
                            + (1.0 - alpha_pg) * target_post_gain
                        )
                        fdata = fdata * float(dehiss_gain_sm)

                    # update output RMS (after processing)
                    try:
                        self.last_output_rms = float(
                            np.sqrt(np.mean(np.square(fdata.astype(np.float64))))
                        )
                    except Exception:
                        pass

                    # dispatch processed frames to all sinks (recorder, others)
                    try:
                        if (
                            self._sink_mgr
                            and self._sink_mgr.has_sinks()
                            and fdata.size > 0
                        ):
                            try:
                                self._dispatch_sinks(fdata)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # write to outdata, scaling per channel
                    if fdata.shape[1] == 1 and outdata.shape[1] > 1:
                        # mono to multi: fill first channel and zero others
                        out_ch_dtype = outdata.dtype
                        outdata[:, 0] = _scale_buffer(fdata[:, 0], out_ch_dtype)
                        if outdata.shape[1] > 1:
                            outdata[:, 1:] = 0
                    else:
                        nch = min(fdata.shape[1], outdata.shape[1])
                        for ch in range(nch):
                            out_ch_dtype = outdata.dtype
                            outdata[:, ch] = _scale_buffer(fdata[:, ch], out_ch_dtype)
                        if outdata.shape[1] > nch:
                            outdata[:, nch:] = 0
                except Exception:
                    outdata.fill(0)

            # remember samplerate for sinks (VAD/transcribe)
            self._current_samplerate = samplerate

            self.stream = sd.Stream(
                device=(self.selected_input, self.selected_output),
                samplerate=samplerate,
                channels=channels,
                callback=callback,
            )
            self.stream.start()
            return {"running": True}
        except Exception as e:
            self.stream = None
            return {"error": str(e), "trace": traceback.format_exc()}

    def stop_bypass(self):
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
