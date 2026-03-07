import math
import importlib
import traceback
import logging

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
    """オーディオバイパス API。

    Audio bypass API: list/select devices and start/stop a direct input->output passthrough.

    デバイスの列挙・選択、バイパスの開始/停止、各種エフェクト設定、
    録音制御、設定の保存/読み込みを JavaScript フロントエンドに提供する。
    """

    def __init__(self):
        """API インスタンスを初期化し、設定を読み込んでコンポーネントをセットアップする。"""
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
        self._logger = logging.getLogger(__name__)
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
        """現在の設定をユーザーデータディレクトリに保存する。

        Save current settings to the user data directory.

        Returns:
            dict: {"ok": True, "path": <保存パス>} または {"error": ...}。
        """
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
        """設定をディスクから読み込んで適用する。

        Load settings from disk and apply them.

        Returns:
            dict: {"ok": True, "settings": dict} または {"error": ...}。
        """
        try:
            settings = self._settings_manager.load()
            self._apply_settings(settings)
            return {"ok": True, "settings": settings}
        except Exception as e:
            return {"error": str(e)}

    def reset_settings(self):
        """全設定をデフォルト値にリセットして返す。

        Reset all settings to defaults and return them.

        Returns:
            dict: {"ok": True, "settings": dict} または {"error": ...}。
        """
        try:
            defaults = self._settings_manager.reset_defaults()
            self._apply_settings(defaults)
            return {"ok": True, "settings": defaults}
        except Exception as e:
            return {"error": str(e)}

    def get_settings_path(self):
        """設定ファイルの保存パスを返す。

        Return the path where settings are stored.
        """
        return {"path": str(self._settings_manager.settings_path)}

    def get_easy_settings(self):
        """現在の全エフェクト設定を簡易形式で返す。

        Returns:
            dict: エンジン名と各エフェクト（NR・ゲート・HPF・コンプレッサー・
                  デヒス）の enabled/strength をまとめた辞書。
        """
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
        """入力を 0.0〜1.0 の float に変換して返す。

        Convert input to a float in the 0.0-1.0 range.
        Raises ValueError for non-numeric or out-of-range inputs.

        Args:
            value: 変換する値。

        Returns:
            float: 0.0〜1.0 の強度値。

        Raises:
            ValueError: 数値でない、または範囲外の場合。
        """
        try:
            s = float(value)
        except Exception:
            raise ValueError("strength must be a number")
        if s < 0.0 or s > 1.0:
            raise ValueError("strength must be between 0 and 1")
        return s

    def _get_gate_strength(self):
        """ゲートしきい値から 0〜1 の強度値を計算して返す。"""
        try:
            s = (float(self.gate_threshold_db) + 70.0) / 45.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _get_hpf_strength(self):
        """ハイパスカットオフ周波数から 0〜1 の強度値を計算して返す。"""
        try:
            s = (float(self.hpf_cutoff_hz) - 50.0) / 150.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _get_comp_strength(self):
        """コンプレッサー比率から 0〜1 の強度値を計算して返す。"""
        try:
            s = (float(self.comp_ratio) - 2.0) / 6.0
            return max(0.0, min(1.0, s))
        except Exception:
            return 0.0

    def _collect_settings(self):
        """現在の全設定値をまとめた辞書を生成して返す。

        Returns:
            dict: gain_db、input_device、output_device、各エフェクト設定を含む辞書。
        """
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
        """設定辞書を読み込んで各内部プロパティに反映する。

        Args:
            settings: gain_db や各エフェクト設定を含む辞書。
                      辞書でない値は無視される。
        """
        try:
            try:
                if getattr(self, "_logger", None) is not None:
                    self._logger.info("Applying settings from load/reset: %s", str(settings))
            except Exception:
                pass
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
        """パイプラインが存在する場合、現在の設定スナップショットを適用する。

        If a pipeline exists, apply the current settings snapshot to it.
        """
        try:
            # Collect snapshot once and log it for diagnostics
            settings = self._collect_settings()
            self._logger.info("Applying settings snapshot to pipeline")

            # First try Api-level pipeline (if present)
            pipeline = getattr(self, "_pipeline", None)
            if pipeline is not None:
                try:
                    pipeline.apply_settings(settings)
                except Exception:
                    self._logger.exception("Failed to apply settings to API pipeline")
            else:
                # If bypass controller manages the active pipeline, delegate to it
                bypass_controller = getattr(self, "_bypass_controller", None)
                if bypass_controller is not None:
                    try:
                        bypass_controller.apply_settings(settings)
                    except Exception:
                        self._logger.exception("Failed to apply settings to bypass controller")
        except Exception:
            pass

    def get_audio_devices(self):
        """利用可能な WASAPI 音声デバイスの一覧を返す。

        Returns:
            dict: デバイスリストとデフォルトデバイス情報を含む辞書。
        """
        return audio_device.get_audio_devices()

    # --- Recording / Save dialog API ---
    def open_save_file_dialog(self):
        """ネイティブの「名前を付けて保存」ダイアログを表示し、選択パスを返す。

        Returns:
            dict: {"path": <選択パス>} または {"path": None}（キャンセル時）、
                  エラー時は {"error": ...}。
        """
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
        """選択中の入力デバイスから録音を開始する。

        Begin recording from the selected input device and stream samples to
        a temporary WAV file in the same directory as `target_path`.
        The final MP3 will be produced when `stop_record` is called.

        Args:
            target_path: 録音結果の出力先ファイルパス（.mp3）。

        Returns:
            dict: {"ok": True} または {"error": ...}。
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
            self._logger.info(
                "API: start_record target=%s input=%s sr=%s ch=%s",
                str(target_path),
                str(self.selected_input),
                samplerate,
                channels,
            )
            return self._recorder.start(target_path, samplerate, channels)
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    def stop_record(self):
        """録音を停止し、一時 WAV を最終ファイルに変換する。

        Stop recording and convert the temporary WAV to the final file.

        Returns:
            dict: 変換情報（RecorderSink.stop() の戻り値）または {"error": ...}。
        """
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
            self._logger.info("API: stop_record called")
            try:
                resp = self._recorder.stop()
            except Exception as e:
                self._logger.exception("API: error stopping recorder")
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
        """入力デバイスを選択する。

        Args:
            index: 選択するデバイスのインデックス。

        Returns:
            dict: {"selected_input": int} または {"error": ...}。
        """
        try:
            idx = int(index)
            self.selected_input = idx
            self._logger.info("API: set_input_device %s", idx)
            return {"selected_input": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def set_output_device(self, index):
        """出力デバイスを選択する。

        Args:
            index: 選択するデバイスのインデックス。

        Returns:
            dict: {"selected_output": int} または {"error": ...}。
        """
        try:
            idx = int(index)
            self.selected_output = idx
            self._logger.info("API: set_output_device %s", idx)
            return {"selected_output": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def get_selected_devices(self):
        """現在選択中の入出力デバイスインデックスを返す。

        Returns:
            dict: {"input": int|None, "output": int|None}。
        """
        return {"input": self.selected_input, "output": self.selected_output}

    def get_gain_db(self):
        """現在のゲイン値を dB で返す。

        Returns:
            dict: {"gain_db": float} または {"error": ...}。
        """
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
        """最近の入出力レベル（線形 RMS および dB）を返す。

        Return recent input/output levels (linear RMS and dB).

        Returns:
            dict: input_rms、output_rms、input_db、output_db を含む辞書。
        """
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
        """処理済みフレームを受け取るシンクを登録する。

        Register a sink callable that will be invoked with processed frames.
        The callable will be called as sink(frames).

        Args:
            sink_callable: フレームを受け取るコールバック関数またはオブジェクト。

        Returns:
            dict: {"ok": True, "id": <sink_id>} または {"error": ...}。
        """
        try:
            return self._sink_mgr.register(sink_callable)
        except Exception as e:
            return {"error": str(e)}

    def unregister_sink(self, sid):
        """指定 ID のシンクを登録解除する。

        Args:
            sid: `register_sink` が返したシンク ID。

        Returns:
            dict: {"ok": True} または {"error": ...}。
        """
        try:
            return self._sink_mgr.unregister(sid)
        except Exception as e:
            return {"error": str(e)}

    def _dispatch_sinks(self, frames):
        """登録済みの全シンクにフレームのコピーを非同期で送る。

        Call all registered sinks with a copy of frames (non-blocking).

        シンク内の例外は握りつぶし、オーディオコールバックを不安定にしないようにする。
        Exceptions in sinks are caught and ignored to avoid destabilizing the
        audio callback.
        """
        try:
            return self._sink_mgr.dispatch(frames)
        except Exception:
            pass

    # Transcription toggle and VAD helper (experiment)
    def set_transcribe_enabled(self, enabled: bool):
        """文字起こし（VAD）機能の有効/無効を切り替える。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
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
        """ゲイン値を dB で設定する。

        Args:
            db: 設定するゲイン値（dB）。

        Returns:
            dict: {"gain_db": float} または {"error": ...}。
        """
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
        """現在のゲート設定を返す。

        Returns:
            dict: enabled、threshold_db、attack_ms、release_ms を含む辞書。
        """
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
        """ゲートのリリース時間を設定する。

        Args:
            ms: リリース時間（ミリ秒）。

        Returns:
            dict: {"release_ms": float} または {"error": ...}。
        """
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
        """ゲート強度（0〜1）を設定し、しきい値・アタック・リリースを更新する。

        Args:
            strength: ゲート強度（0.0〜1.0）。

        Returns:
            dict: {"strength": float, "threshold_db": float} または {"error": ...}。
        """
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
        """現在のハイパスフィルタ設定を返す。

        Returns:
            dict: enabled、cutoff_hz を含む辞書。
        """
        try:
            return {
                "enabled": bool(self.hpf_enabled),
                "cutoff_hz": float(self.hpf_cutoff_hz),
            }
        except Exception as e:
            return {"error": str(e)}

    # Noise reduction (noisereduce) API
    def get_nr_settings(self):
        """現在のノイズ低減設定を返す。

        Returns:
            dict: enabled、strength を含む辞書。
        """
        try:
            return {
                "enabled": bool(self.nr_enabled),
                "strength": float(self.nr_strength),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_nr_enabled(self, enabled):
        """ノイズ低減の有効/無効を切り替える。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
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
        """ノイズ低減強度を設定する。

        Args:
            strength: ノイズ低減強度（0.0〜1.0）。

        Returns:
            dict: {"strength": float} または {"error": ...}。
        """
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
        """現在のデヒス（最終ノイズ調整）設定を返す。

        Returns:
            dict: enabled、strength、threshold_db、lpf_hz を含む辞書。
        """
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
        """デヒス（最終ノイズ調整）の有効/無効を切り替える。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
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
        """デヒス強度を設定し、しきい値・LPF カットオフを更新する。

        Args:
            strength: デヒス強度（0.0〜1.0）。

        Returns:
            dict: {"strength": float, "threshold_db": float, "lpf_hz": float}
                  または {"error": ...}。
        """
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
        """現在のコンプレッサー設定を返す。

        Returns:
            dict: enabled、threshold_db、ratio、attack_ms、release_ms、makeup_db を含む辞書。
        """
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
        """コンプレッサーの有効/無効を切り替える。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
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
        """コンプレッサーの圧縮開始しきい値を設定する。

        Args:
            db: しきい値（dB）。

        Returns:
            dict: {"threshold_db": float} または {"error": ...}。
        """
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
        """コンプレッサーの圧縮比を設定する。

        Args:
            ratio: 圧縮比（1.0 以上）。

        Returns:
            dict: {"ratio": float} または {"error": ...}。
        """
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
        """コンプレッサーのアタック時間を設定する。

        Args:
            ms: アタック時間（ミリ秒、0 より大きい値）。

        Returns:
            dict: {"attack_ms": float} または {"error": ...}。
        """
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
        """コンプレッサーのリリース時間を設定する。

        Args:
            ms: リリース時間（ミリ秒、0 より大きい値）。

        Returns:
            dict: {"release_ms": float} または {"error": ...}。
        """
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
        """コンプレッサーのメイクアップゲインを設定する。

        Args:
            db: メイクアップゲイン（dB）。

        Returns:
            dict: {"makeup_db": float} または {"error": ...}。
        """
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
        """コンプレッサー強度（0〜1）を設定し、比率・しきい値・ゲインを更新する。

        Args:
            strength: コンプレッサー強度（0.0〜1.0）。

        Returns:
            dict: {"strength", "ratio", "threshold_db", "makeup_db"} または {"error": ...}。
        """
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
        """ハイパスフィルタの有効/無効を切り替える。

        Args:
            enabled: True で有効化、False で無効化。

        Returns:
            dict: {"enabled": bool} または {"error": ...}。
        """
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
        """ハイパスフィルタのカットオフ周波数を設定する。

        Args:
            hz: カットオフ周波数（Hz、0 より大きい値）。

        Returns:
            dict: {"cutoff_hz": float} または {"error": ...}。
        """
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
        """ハイパスフィルタ強度（0〜1）を設定し、カットオフ周波数を更新する。

        Args:
            strength: フィルタ強度（0.0〜1.0）。

        Returns:
            dict: {"strength": float, "cutoff_hz": float} または {"error": ...}。
        """
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
        """現在の文字起こし（VAD）設定を返す。

        Returns:
            dict: enabled、vad_window_ms、vad_silence_ms を含む辞書。
        """
        try:
            return {
                "enabled": bool(self.transcribe_enabled),
                "vad_window_ms": int(self.vad_window_ms),
                "vad_silence_ms": int(self.vad_silence_ms),
            }
        except Exception as e:
            return {"error": str(e)}

    def is_running(self):
        """バイパスストリームが現在動作中かどうかを返す。

        Returns:
            dict: {"running": bool}。
        """
        try:
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return {"running": bool(bypass_controller.is_running())}
        except Exception:
            pass
        return {"running": self.stream is not None}

    def start_bypass(self):
        """バイパスを開始する。

        選択中の入出力デバイスを使ってリアルタイム音声処理を開始する。
        デバイスが未選択の場合はシステムデフォルトを試みる。

        Returns:
            dict: {"running": True} または {"error": ...}。
        """
        try:
            # If devices not explicitly selected, try to use system defaults
            try:
                if self.selected_input is None or self.selected_output is None:
                    try:
                        default_dev = audio_device.get_default_device()
                        if isinstance(default_dev, (list, tuple)):
                            if self.selected_input is None and len(default_dev) > 0:
                                self.selected_input = default_dev[0]
                            if self.selected_output is None and len(default_dev) > 1:
                                self.selected_output = default_dev[1]
                    except Exception:
                        pass

            except Exception:
                pass

            self._logger.info(
                "API: start_bypass input=%s output=%s",
                str(self.selected_input),
                str(self.selected_output),
            )
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
        """バイパスを停止する。

        Returns:
            dict: {"running": False} または {"error": "not running"}。
        """
        try:
            self._logger.info("API: stop_bypass requested")
            bypass_controller = getattr(self, "_bypass_controller", None)
            if bypass_controller is not None:
                return bypass_controller.stop()
        except Exception:
            pass
        return {"error": "not running"}
