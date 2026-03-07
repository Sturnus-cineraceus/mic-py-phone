try:
    import noisereduce as nr
except Exception:
    nr = None


def is_available():
    """noisereduce ライブラリが利用可能かどうかを返す。

    Returns:
        bool: 利用可能な場合は True、そうでない場合は False。
    """
    return nr is not None


def reduce_noise(y, sr, strength=0.9):
    """noisereduce を使ってノイズ低減を行い、処理後の音声配列を返す。

    Args:
        y: 入力音声の numpy 配列。
        sr: サンプルレート（Hz）。
        strength: ノイズ低減強度（0.0〜1.0）。デフォルトは 0.9。

    Returns:
        ノイズ低減後の numpy 配列。

    Raises:
        RuntimeError: noisereduce が利用できない場合。
    """
    if nr is None:
        raise RuntimeError("noisereduce not available")
    try:
        # use prop_decrease to control reduction strength (0..1)
        return nr.reduce_noise(y=y, sr=int(sr), prop_decrease=float(strength))
    except Exception:
        # re-raise to let callers handle
        raise
