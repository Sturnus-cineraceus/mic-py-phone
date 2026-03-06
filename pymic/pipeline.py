from typing import Any, Dict, Optional
import copy
import logging
import numpy as np

from .processors import (
    GateProcessor,
    HighpassProcessor,
    CompressorProcessor,
    DeHissProcessor,
)


class BypassPipeline:
    """Pipeline that applies processors in order.

    Order: NoiseReduction (external wrapper) -> Highpass -> Gate -> Compressor -> DeHiss -> post-gain
    This class keeps simple processor instances and a settings snapshot.
    """

    def __init__(
        self,
        samplerate: Optional[int] = None,
        channels: Optional[int] = None,
        settings: Optional[Dict] = None,
    ):
        self.samplerate = int(samplerate or 44100)
        self.channels = int(channels or 1)
        self.settings = settings or {}
        # gain as linear multiplier (from settings.gain_db)
        try:
            gain_db = float(self.settings.get("gain_db", 0.0))
            self.gain = float(10.0 ** (gain_db / 20.0))
        except Exception:
            self.gain = 1.0
        self._running = False
        self._last_input_level = 0.0
        self._last_output_level = 0.0

        # processors (initialized from settings)
        self._hpf = None
        self._gate = None
        self._comp = None
        self._dehiss = None

        self._init_processors(self.settings)
        self._logger = logging.getLogger(__name__)

    def _init_processors(self, settings: Dict[str, Any]):
        # instantiate processors according to settings
        try:
            gate_cfg = settings.get("gate", {}) if isinstance(settings, dict) else {}
            hpf_cfg = settings.get("hpf", {}) if isinstance(settings, dict) else {}
            comp_cfg = (
                settings.get("compressor", {}) if isinstance(settings, dict) else {}
            )
            deh_cfg = settings.get("dehiss", {}) if isinstance(settings, dict) else {}
            # Respect 'enabled' flags in settings; only instantiate processors when enabled
            try:
                hpf_enabled = bool(hpf_cfg.get("enabled", False))
            except Exception:
                hpf_enabled = False
            try:
                gate_enabled = bool(gate_cfg.get("enabled", False))
            except Exception:
                gate_enabled = False
            try:
                comp_enabled = bool(comp_cfg.get("enabled", False))
            except Exception:
                comp_enabled = False
            try:
                deh_enabled = bool(deh_cfg.get("enabled", False))
            except Exception:
                deh_enabled = False

            self._hpf = (
                HighpassProcessor(
                    samplerate=self.samplerate,
                    channels=self.channels,
                    cutoff=float(hpf_cfg.get("cutoff_hz", 80.0)),
                )
                if hpf_enabled
                else None
            )
            self._gate = (
                GateProcessor(
                    samplerate=self.samplerate,
                    channels=self.channels,
                    threshold=float(gate_cfg.get("threshold_db", -40.0)),
                )
                if gate_enabled
                else None
            )
            self._comp = (
                CompressorProcessor(
                    samplerate=self.samplerate,
                    channels=self.channels,
                    ratio=float(comp_cfg.get("ratio", 4.0)),
                    threshold=float(comp_cfg.get("threshold_db", -24.0)),
                )
                if comp_enabled
                else None
            )
            self._dehiss = (
                DeHissProcessor(
                    samplerate=self.samplerate,
                    channels=self.channels,
                    strength=float(deh_cfg.get("strength", 0.5)),
                )
                if deh_enabled
                else None
            )
            # Log instantiated processors and key params
            try:
                self._logger.info(
                    "Pipeline processors - HPF=%s cutoff=%s, Gate=%s threshold=%s, Comp=%s ratio=%s, DeHiss=%s strength=%s",
                    bool(self._hpf is not None),
                    getattr(self._hpf, "cutoff", None) if self._hpf is not None else None,
                    bool(self._gate is not None),
                    getattr(self._gate, "threshold", None) if self._gate is not None else None,
                    bool(self._comp is not None),
                    getattr(self._comp, "ratio", None) if self._comp is not None else None,
                    bool(self._dehiss is not None),
                    getattr(self._dehiss, "strength", None) if self._dehiss is not None else None,
                )
            except Exception:
                pass
        except Exception:
            # fallback to defaults
            self._hpf = HighpassProcessor(
                samplerate=self.samplerate, channels=self.channels
            )
            self._gate = GateProcessor(
                samplerate=self.samplerate, channels=self.channels
            )
            self._comp = CompressorProcessor(
                samplerate=self.samplerate, channels=self.channels
            )
            self._dehiss = DeHissProcessor(
                samplerate=self.samplerate, channels=self.channels
            )
            try:
                self._logger.info("Pipeline processors - default instances created")
            except Exception:
                pass

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def apply_settings(self, settings_snapshot: Dict[str, Any]) -> None:
        old = self.settings or {}
        new = settings_snapshot or {}
        self.settings = new
        # log what changed between old and new (shallow diff)
        try:
            diffs = {}
            for k in set(list(old.keys()) + list(new.keys())):
                if old.get(k) != new.get(k):
                    diffs[k] = {"old": old.get(k), "new": new.get(k)}
            if diffs:
                self._logger.info("Applying pipeline settings diff: %s", diffs)
            else:
                self._logger.debug("Applying pipeline settings: no changes detected")
        except Exception:
            self._logger.debug("Applying pipeline settings (unable to compute diff)")

        # update gain from settings
        try:
            gain_db = float(self.settings.get("gain_db", 0.0))
            self.gain = float(10.0 ** (gain_db / 20.0))
        except Exception:
            self.gain = 1.0

        self._init_processors(self.settings)

    def apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Alias for apply_settings for clearer intent when applying a snapshot."""
        self.apply_settings(snapshot)

    def snapshot(self) -> Dict[str, Any]:
        """Return a settings snapshot reflecting the current pipeline configuration.

        The snapshot is a plain dict suitable for re-applying via `apply_snapshot`.
        """
        s: Dict[str, Any] = {
            "samplerate": int(self.samplerate),
            "channels": int(self.channels),
        }

        try:
            s["hpf"] = {
                "enabled": bool(self._hpf is not None),
                "cutoff_hz": float(
                    getattr(
                        self._hpf,
                        "cutoff",
                        self.settings.get("hpf", {}).get("cutoff_hz", 80.0),
                    )
                ),
            }
        except Exception:
            s["hpf"] = {"enabled": False, "cutoff_hz": 80.0}

        try:
            s["gate"] = {
                "enabled": bool(self._gate is not None),
                "threshold_db": float(
                    getattr(
                        self._gate,
                        "threshold",
                        self.settings.get("gate", {}).get("threshold_db", -40.0),
                    )
                ),
            }
        except Exception:
            s["gate"] = {"enabled": False, "threshold_db": -40.0}

        try:
            comp_ratio = float(
                getattr(
                    self._comp,
                    "ratio",
                    self.settings.get("compressor", {}).get("ratio", 4.0),
                )
            )
            # compressor may store threshold in attribute or in params dict
            comp_threshold = None
            if hasattr(self._comp, "threshold"):
                comp_threshold = float(getattr(self._comp, "threshold"))
            elif hasattr(self._comp, "params") and isinstance(self._comp.params, dict):
                comp_threshold = float(
                    self._comp.params.get("threshold")
                    or self._comp.params.get("threshold_db")
                    or self.settings.get("compressor", {}).get("threshold_db", -24.0)
                )
            else:
                comp_threshold = float(
                    self.settings.get("compressor", {}).get("threshold_db", -24.0)
                )
            s["compressor"] = {
                "enabled": bool(self._comp is not None),
                "ratio": comp_ratio,
                "threshold_db": comp_threshold,
            }
        except Exception:
            s["compressor"] = {"enabled": False, "ratio": 4.0, "threshold_db": -24.0}

        try:
            s["dehiss"] = {
                "enabled": bool(self._dehiss is not None),
                "strength": float(
                    getattr(
                        self._dehiss,
                        "strength",
                        self.settings.get("dehiss", {}).get("strength", 0.5),
                    )
                ),
            }
        except Exception:
            s["dehiss"] = {"enabled": False, "strength": 0.5}

        # preserve any unknown keys present in the original settings
        try:
            for k, v in (self.settings or {}).items():
                if k not in s:
                    s[k] = copy.deepcopy(v)
        except Exception:
            pass

        return s

    def process_frame(self, frames: np.ndarray) -> np.ndarray:
        """Apply processing chain to frames and return processed frames."""
        try:
            if frames is None:
                return frames
            f = np.asarray(frames, dtype=np.float32)
            if f.ndim == 1:
                f = f.reshape(-1, 1)

            # update input level
            try:
                self._last_input_level = float(
                    np.sqrt(np.mean(np.square(f.astype(np.float64))))
                )
            except Exception:
                pass

            # sequentially apply processors
            try:
                # Noise reduction handled externally (existing module) - pipeline expects caller to enable
                if self._hpf is not None:
                    f = self._hpf.process(f)
                if self._gate is not None:
                    f = self._gate.process(f)
                if self._comp is not None:
                    f = self._comp.process(f)
                if self._dehiss is not None:
                    f = self._dehiss.process(f)
            except Exception:
                pass

            # update output level
            try:
                self._last_output_level = float(
                    np.sqrt(np.mean(np.square(f.astype(np.float64))))
                )
            except Exception:
                pass

                # apply post-gain (linear)
                try:
                    f = f * float(getattr(self, "gain", 1.0))
                except Exception:
                    pass

            return f
        except Exception:
            return frames

    def get_levels(self) -> Dict[str, float]:
        return {
            "input_rms": self._last_input_level,
            "output_rms": self._last_output_level,
        }
