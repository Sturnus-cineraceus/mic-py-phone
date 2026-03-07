import numpy as np

from pymic.processors import (
    GateProcessor,
    HighpassProcessor,
    CompressorProcessor,
    DeHissProcessor,
)


def test_gate_processor_silences_below_threshold():
    """閾値以下のフレームがゼロにミュートされることを確認する。"""
    # generate frames: first half low, second half high
    low = np.zeros((50, 1), dtype=np.float32) + 1e-6
    high = np.ones((50, 1), dtype=np.float32) * 0.2
    frames = np.vstack((low, high))

    gate = GateProcessor(samplerate=44100, channels=1, threshold=-20.0)
    out = gate.process(frames)

    # RMS of high (~0.2) is above threshold -20dB (~0.1), low is below
    assert out.shape == frames.shape
    assert np.allclose(out[:50, :], 0, atol=1e-7)
    assert np.allclose(out[50:, :], high, rtol=1e-2)


def test_highpass_reduces_dc():
    """DC 成分（定常入力）がハイパスフィルタで低減されることを確認する。"""
    # constant DC input should be reduced by a highpass
    frames = np.ones((100, 1), dtype=np.float32) * 0.5
    hpf = HighpassProcessor(samplerate=44100, channels=1, cutoff=80.0)
    out = hpf.process(frames)
    assert out.shape == frames.shape
    # mean absolute value should be significantly smaller
    assert np.mean(np.abs(out)) < 0.2


def test_compressor_reduces_above_threshold():
    """閾値を超えるレベルのフレームにゲイン低下が適用されることを確認する。"""
    # create loud frames that exceed threshold
    frames = np.ones((10, 1), dtype=np.float32) * 1.0
    comp = CompressorProcessor(samplerate=44100, channels=1, ratio=4.0)
    # ensure threshold attribute exists to match runtime usage
    comp.threshold = -6.0
    out = comp.process(frames)
    assert out.shape == frames.shape
    # some gain reduction should be applied (output < input)
    assert np.mean(np.abs(out)) < np.mean(np.abs(frames))


def test_dehiss_process_no_crash_and_shape():
    """DeHissProcessor がクラッシュせず、出力形状が入力と一致することを確認する。"""
    frames = np.random.randn(128, 1).astype(np.float32) * 0.01
    dh = DeHissProcessor(samplerate=44100, channels=1, strength=0.5)
    out = dh.process(frames)
    assert out.shape == frames.shape
