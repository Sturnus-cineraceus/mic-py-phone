from typing import Optional


class Processor:
    def __init__(self, samplerate: int = 44100, channels: int = 1, **params):
        self.samplerate = samplerate
        self.channels = channels
        self.params = params

    def set_params(self, **params) -> None:
        self.params.update(params)

    def process(self, frames):
        # サブクラスでオーバーライド
        return frames


class GateProcessor(Processor):
    def __init__(
        self, samplerate=44100, channels=1, threshold: float = -40.0, **params
    ):
        super().__init__(samplerate, channels, **params)
        self.threshold = threshold

    def set_params(self, threshold: Optional[float] = None, **params):
        if threshold is not None:
            self.threshold = threshold
        super().set_params(**params)

    def process(self, frames):
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            # compute RMS per frame across channels
            rms = np.sqrt(np.mean(np.square(f.astype(np.float64)), axis=1))
            thr_lin = 10.0 ** (self.threshold / 20.0)
            # simple gate: zero frames below threshold
            mask = rms >= thr_lin
            out = f.copy()
            out[~mask, :] = 0
            return out
        except Exception:
            return frames


class HighpassProcessor(Processor):
    def __init__(self, samplerate=44100, channels=1, cutoff: float = 80.0, **params):
        super().__init__(samplerate, channels, **params)
        self.cutoff = cutoff

    def set_params(self, cutoff: Optional[float] = None, **params):
        if cutoff is not None:
            self.cutoff = cutoff
        super().set_params(**params)

    def process(self, frames):
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            # simple one-pole highpass via naive diff approximation for small cutoff
            # use a first-order highpass: y[n] = a*(y[n-1] + x[n] - x[n-1])
            fs = float(self.samplerate)
            f0 = max(1.0, min(self.cutoff, fs / 2.0 - 1.0))
            omega = 2.0 * 3.141592653589793 * f0 / fs
            alpha = omega / (omega + 1.0)
            out = np.zeros_like(f)
            x_prev = np.zeros((self.channels,), dtype=np.float32)
            y_prev = np.zeros((self.channels,), dtype=np.float32)
            for i in range(f.shape[0]):
                x = f[i, :]
                y = alpha * (y_prev + x - x_prev)
                out[i, :] = y
                x_prev = x
                y_prev = y
            return out
        except Exception:
            return frames


class CompressorProcessor(Processor):
    def __init__(
        self,
        samplerate=44100,
        channels=1,
        ratio: float = 2.0,
        threshold: float = -20.0,
        **params,
    ):
        super().__init__(samplerate, channels, **params)
        self.ratio = ratio
        self.threshold = threshold

    def set_params(
        self, ratio: Optional[float] = None, threshold: Optional[float] = None, **params
    ):
        if ratio is not None:
            self.ratio = ratio
        if threshold is not None:
            self.threshold = threshold
        super().set_params(**params)

    def process(self, frames):
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            # RMS-based soft compressor (simple)
            out = np.empty_like(f)
            thr = float(self.threshold)
            ratio = float(max(1.0, self.ratio))
            # per-frame envelope
            for i in range(f.shape[0]):
                s = f[i, :]
                level = float(np.sqrt(np.mean(np.square(s.astype(np.float64)))))
                db = 20.0 * np.log10(level + 1e-12)
                if db > thr:
                    # reduce above threshold
                    exceed = db - thr
                    reduced_db = thr + exceed / ratio
                    gain_db = reduced_db - db
                    gain = 10.0 ** (gain_db / 20.0)
                else:
                    gain = 1.0
                out[i, :] = s * gain
            return out
        except Exception:
            return frames


class DeHissProcessor(Processor):
    def __init__(self, samplerate=44100, channels=1, strength: float = 0.5, **params):
        super().__init__(samplerate, channels, **params)
        self.strength = strength

    def set_params(self, strength: Optional[float] = None, **params):
        if strength is not None:
            self.strength = strength
        super().set_params(**params)

    def process(self, frames):
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            # one-pole low-pass to reduce hiss (simple)
            fs = float(self.samplerate)
            cutoff = max(100.0, min(12000.0, 1000.0 * float(self.strength)))
            alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / fs)
            out = np.empty_like(f)
            prev = np.zeros((self.channels,), dtype=np.float32)
            for i in range(f.shape[0]):
                x = f[i, :]
                y = prev + alpha * (x - prev)
                out[i, :] = y
                prev = y
            # gentle downward expansion near low levels
            env = np.sqrt(np.mean(np.square(out.astype(np.float64))))
            floor = max(0.15, 1.0 - 0.9 * float(self.strength))
            if env < 1e-6:
                return out * floor
            return out * 1.0
        except Exception:
            return frames
