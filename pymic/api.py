import math
import importlib
import traceback

# numpy usage moved to pipeline/recorder/bypass_controller; avoid importing here


from .settings_manager import SettingsManager
from .sink_manager import SinkManager
from .recorder import Recorder
from .bypass_controller import BypassController

from . import audio_device

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
        # recording state (delegated to Recorder)
        self.selected_input = None
        self.selected_output = None
        self.stream = None
        self._record_stream = None
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
        # injected pipeline instance (BypassPipeline)
        self._pipeline = None
        # bypass controller handles stream and pipeline lifecycle
        try:
            self._bypass_controller = BypassController(
                self._sink_mgr, self._collect_settings
            )
        except Exception:
            self._bypass_controller = None

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

    def _to_strength01(self, value):
        """
        Convert input to a float in the 0.0-1.0 range.
        Raises ValueError for non-numeric or out-of-range inputs.
        """
        try:
            s = float(value)
        except Exception:
            raise ValueError("strength must be a number")
        if s < 0.0 or s > 1.0:
            raise ValueError("strength must be between 0 and 1")
        return s

    def _get_gate_strength(self):
        try:
            s = (float(self.gate_threshold_db) + 70.0) / 45.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _get_hpf_strength(self):
        try:
            s = (float(self.hpf_cutoff_hz) - 50.0) / 150.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _get_comp_strength(self):
        try:
            s = (float(self.comp_ratio) - 2.0) / 6.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _collect_settings(self):
        try:
            gain_db = 20.0 * math.log10(self.volume) if self.volume > 0 else 0.0
        except Exception:
            gain_db = 0.0
        return {
            "gain_db": float(gain_db),
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

    def _apply_settings(self, settings: dict):
        try:
            if not isinstance(settings, dict):
                return
            if "gain_db" in settings:
                try:
                    g = float(settings.get("gain_db", 0.0))
                    self.volume = float(10.0 ** (g / 20.0))
                except Exception:
                    pass
            if "input_device" in settings:
                try:
                    self.selected_input = settings.get("input_device")
                except Exception:
                    pass
            if "output_device" in settings:
                try:
                    self.selected_output = settings.get("output_device")
                except Exception:
                    pass
            gate = settings.get("gate") or {}
            try:
                self.gate_enabled = bool(gate.get("enabled", self.gate_enabled))
                self.gate_threshold_db = float(
                    gate.get("threshold_db", self.gate_threshold_db)
                )
                self.gate_attack_ms = float(gate.get("attack_ms", self.gate_attack_ms))
                self.gate_release_ms = float(
                    gate.get("release_ms", self.gate_release_ms)
                )
            except Exception:
                pass

            hpf = settings.get("hpf") or {}
            try:
                self.hpf_enabled = bool(hpf.get("enabled", self.hpf_enabled))
                self.hpf_cutoff_hz = float(hpf.get("cutoff_hz", self.hpf_cutoff_hz))
            except Exception:
                pass

            nr = settings.get("nr") or {}
            try:
                self.nr_enabled = bool(nr.get("enabled", self.nr_enabled))
                self.nr_strength = float(nr.get("strength", self.nr_strength))
            except Exception:
                pass

            comp = settings.get("compressor") or {}
            try:
                self.comp_enabled = bool(comp.get("enabled", self.comp_enabled))
                self.comp_threshold_db = float(
                    comp.get("threshold_db", self.comp_threshold_db)
                )
                self.comp_ratio = float(comp.get("ratio", self.comp_ratio))
                self.comp_attack_ms = float(comp.get("attack_ms", self.comp_attack_ms))
                self.comp_release_ms = float(
                    comp.get("release_ms", self.comp_release_ms)
                )
                self.comp_makeup_db = float(comp.get("makeup_db", self.comp_makeup_db))
            except Exception:
                pass

            deh = settings.get("dehiss") or {}
            try:
                self.dehiss_enabled = bool(deh.get("enabled", self.dehiss_enabled))
                self.dehiss_strength = float(deh.get("strength", self.dehiss_strength))
                self.dehiss_threshold_db = float(
                    deh.get("threshold_db", self.dehiss_threshold_db)
                )
                self.dehiss_lpf_hz = float(deh.get("lpf_hz", self.dehiss_lpf_hz))
            except Exception:
                pass
        except Exception:
            pass

    def _maybe_apply_pipeline_settings(self):
        """If a pipeline exists, apply the current settings snapshot to it."""
        try:
            pipeline = getattr(self, "_pipeline", None)
            if pipeline is not None:
                try:
                    pipeline.apply_settings(self._collect_settings())
                except Exception:
                    pass
        except Exception:
            pass

    def get_audio_devices(self):
        return audio_device.get_audio_devices()

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
        if not audio_device.is_available():
            return {"error": "sounddevice not available"}
        if self._recorder.is_recording() or self._record_stream is not None:
            return {"error": "already recording"}
        # Delegate recording to Recorder which manages stream and sinks
        try:
            dev = audio_device.query_device(self.selected_input)
            samplerate = int(dev.get("default_samplerate") or 44100)
            channels = int(dev.get("max_input_channels") or 1)
            return self._recorder.start(target_path, samplerate, channels)
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}
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
            # Prefer pipeline/bypass controller levels when available
            in_rms = 0.0
            out_rms = 0.0
            try:
                bypass_controller = getattr(self, "_bypass_controller", None)
                if bypass_controller is not None and bypass_controller.is_running():
                    lv = bypass_controller.get_levels()
                    in_rms = float(lv.get("input_rms", 0.0))
                    out_rms = float(lv.get("output_rms", 0.0))
                else:
                    # fall back to recorder/last measured
                    try:
                        in_rms = float(
                            getattr(self._recorder, "last_input_rms", 0.0) or 0.0
                        )
                    except Exception:
                        in_rms = float(self.last_input_rms or 0.0)
                    out_rms = float(self.last_output_rms or 0.0)
            except Exception:
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

        The callable will be called as sink(frames).
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
            # delegate to bypass controller if available
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return bypass_controller.set_transcribe_enabled(enabled)
            # otherwise fall back to previous behavior (minimal)
            self.transcribe_enabled = bool(enabled)
            return {"enabled": self.transcribe_enabled}
        except Exception as e:
            return {"error": str(e)}

    def set_gain_db(self, db):
        try:
            dbf = float(db)
            self.volume = float(10.0 ** (dbf / 20.0))
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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

    def set_gate_release_ms(self, ms):
        try:
            self.gate_release_ms = float(ms)
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"release_ms": self.gate_release_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.gate_threshold_db = -70.0 + (45.0 * s)
            self.gate_attack_ms = 8.0
            self.gate_release_ms = 120.0
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"enabled": self.nr_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_nr_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.nr_strength = s
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"enabled": self.comp_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_threshold_db(self, db):
        try:
            self.comp_threshold_db = float(db)
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"threshold_db": self.comp_threshold_db}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_ratio(self, ratio):
        try:
            r = float(ratio)
            if r < 1.0:
                return {"error": "ratio must be >= 1.0"}
            self.comp_ratio = r
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"ratio": self.comp_ratio}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_attack_ms(self, ms):
        try:
            m = float(ms)
            if m <= 0:
                return {"error": "attack must be > 0"}
            self.comp_attack_ms = m
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"attack_ms": self.comp_attack_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_release_ms(self, ms):
        try:
            m = float(ms)
            if m <= 0:
                return {"error": "release must be > 0"}
            self.comp_release_ms = m
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"release_ms": self.comp_release_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_compressor_makeup_db(self, db):
        try:
            self.comp_makeup_db = float(db)
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"enabled": self.hpf_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_cutoff_hz(self, hz):
        try:
            hzf = float(hz)
            if hzf <= 0:
                return {"error": "cutoff must be > 0"}
            self.hpf_cutoff_hz = hzf
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
            return {"cutoff_hz": self.hpf_cutoff_hz}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_strength(self, strength):
        try:
            s = self._to_strength01(strength)
            self.hpf_cutoff_hz = 50.0 + (150.0 * s)
            try:
                self._maybe_apply_pipeline_settings()
            except Exception:
                pass
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
        try:
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return {"running": bool(bypass_controller.is_running())}
        except Exception:
            pass
        return {"running": self.stream is not None}

    def start_bypass(self):
        # Delegate to BypassController if available
        try:
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return bypass_controller.start(
                    self.selected_input, self.selected_output
                )
        except Exception:
            pass
        # fallback: original checks (kept minimal)
        if not audio_device.is_available():
            return {"error": "sounddevice not available"}
        return {"error": "unable to start bypass"}

    def stop_bypass(self):
        try:
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return bypass_controller.stop()
        except Exception:
            pass
        return {"error": "not running"}
