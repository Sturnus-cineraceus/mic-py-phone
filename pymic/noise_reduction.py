"""noisereduce ライブラリを用いたノイズ低減のラッパーモジュール。

noisereduce が利用不可の場合は is_available() で確認し、
reduce_noise() 呼び出し時に RuntimeError が送出される。
"""

try:
    import noisereduce as nr
except Exception:
    nr = None


def is_available():
    """noisereduce ライブラリが利用可能かどうかを返す。"""
    return nr is not None


def reduce_noise(y, sr, strength=0.9):
    """noisereduce を使って音声配列のノイズを低減する。

    Args:
        y: 処理対象の音声配列（numpy array）。
        sr: サンプルレート（Hz）。
        strength: ノイズ低減の強さ（0.0〜1.0）。

    Returns:
        ノイズ低減後の numpy 配列。

    Raises:
        RuntimeError: noisereduce が利用不可の場合。
    """
    if nr is None:
        raise RuntimeError("noisereduce not available")
    try:
        # use prop_decrease to control reduction strength (0..1)
        return nr.reduce_noise(y=y, sr=int(sr), prop_decrease=float(strength))
    except Exception:
        # re-raise to let callers handle
        raise
