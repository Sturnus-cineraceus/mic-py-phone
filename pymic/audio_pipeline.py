"""リアルタイムでマイク入力にゲインとノイズゲートをかけてスピーカー出力するモジュール。

依存: sounddevice, numpy

使い方例:
python -m pymic.audio_pipeline --gain-db 6 --threshold-db -40
"""

from __future__ import annotations

import argparse
import math
import threading
import logging

import numpy as np
import sounddevice as sd

_logger = logging.getLogger(__name__)


class NoiseGate:
    def __init__(
        self,
        samplerate: int,
        threshold_db: float = -40.0,
        attack_ms: float = 10.0,
        release_ms: float = 100.0,
    ):
        self.sr = float(samplerate)
        self.threshold_db = float(threshold_db)
        self.attack_ms = float(attack_ms)
        self.release_ms = float(release_ms)
        # time constants to smoothing coefficients
        self.alpha_attack = math.exp(
            -1.0 / (max(self.sr * (self.attack_ms / 1000.0), 1.0))
        )
        self.alpha_release = math.exp(
            -1.0 / (max(self.sr * (self.release_ms / 1000.0), 1.0))
        )
        self.env = 0.0

    def _rms(self, block: np.ndarray) -> float:
        # block shape: (frames, channels)
        if block.size == 0:
            return 0.0
        # compute RMS across all channels
        return float(np.sqrt(np.mean(np.square(block.astype(np.float64)))))

    def process(self, block: np.ndarray) -> np.ndarray:
        """Apply smoothed noise gate to the given block and return processed block.

        This method only computes a scalar gate gain for the whole block using a smoothed
        envelope tracker based on RMS. It mutes blocks whose envelope is below threshold.
        """
        rms = self._rms(block)
        if rms > self.env:
            self.env = self.alpha_attack * self.env + (1.0 - self.alpha_attack) * rms
        else:
            self.env = self.alpha_release * self.env + (1.0 - self.alpha_release) * rms

        env_db = 20.0 * math.log10(self.env + 1e-12)
        if env_db < self.threshold_db:
            gate_gain = 0.0
        else:
            gate_gain = 1.0

        return block * gate_gain


def run_stream(
    gain_db: float = 0.0,
    threshold_db: float = -40.0,
    device: int | None = None,
    samplerate: int | None = None,
    channels: int = 1,
    blocksize: int = 1024,
):
    """Run full duplex stream: mic -> gain -> noise gate -> speakers."""
    try:
        # Query default sample rate if not provided
        if samplerate is None:
            default = sd.query_devices(device, "input")
            samplerate = int(default["default_samplerate"])
    except Exception:
        samplerate = 48000

    gain_mul = 10.0 ** (gain_db / 20.0)

    gate = NoiseGate(samplerate=samplerate, threshold_db=threshold_db)

    stop_event = threading.Event()

    def callback(indata, outdata, frames, time_info, status):
        if status:
            _logger.warning("Stream callback status: %s", status)
        # ensure float32
        data = indata.copy().astype(np.float32)
        # apply boost
        data *= gain_mul
        # apply gate (returns array)
        processed = gate.process(data)
        # write to output (match channels)
        if processed.shape[1] < outdata.shape[1]:
            # pad channels if needed
            out = np.zeros_like(outdata)
            out[:, : processed.shape[1]] = processed
            outdata[:] = out
        else:
            outdata[:] = processed

    _logger.info(
        "Starting audio: gain=%s dB (%.3fx), gate threshold=%s dB, sr=%s, channels=%s",
        gain_db,
        gain_mul,
        threshold_db,
        samplerate,
        channels,
    )

    try:
        with sd.Stream(
            samplerate=samplerate,
            blocksize=blocksize,
            dtype="float32",
            channels=channels,
            callback=callback,
            device=device,
        ):
            _logger.info("Press Ctrl+C to stop")
            while not stop_event.is_set():
                stop_event.wait(0.1)
    except KeyboardInterrupt:
        _logger.info("Stopped by user via KeyboardInterrupt")
    except Exception as e:
        _logger.exception("Stream error: %s", e)


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="リアルタイムでゲインとノイズゲートをかける"
    )
    p.add_argument("--gain-db", type=float, default=0.0, help="増幅量（dB）")
    p.add_argument(
        "--threshold-db", type=float, default=-40.0, help="ノイズゲート閾値（dB）"
    )
    p.add_argument(
        "--device", type=int, default=None, help="音声デバイスID（省略でデフォルト）"
    )
    p.add_argument(
        "--samplerate",
        type=int,
        default=None,
        help="サンプルレート（省略で入力デバイスのデフォルト）",
    )
    p.add_argument(
        "--channels", type=int, default=1, help="チャンネル数（デフォルト1=mono）"
    )
    p.add_argument("--blocksize", type=int, default=1024, help="ブロックサイズ")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    run_stream(
        gain_db=args.gain_db,
        threshold_db=args.threshold_db,
        device=args.device,
        samplerate=args.samplerate,
        channels=args.channels,
        blocksize=args.blocksize,
    )
