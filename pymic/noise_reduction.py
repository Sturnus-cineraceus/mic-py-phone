try:
    import noisereduce as nr
except Exception:
    nr = None


def is_available():
    return nr is not None


def reduce_noise(y, sr, strength=0.9):
    if nr is None:
        raise RuntimeError("noisereduce not available")
    try:
        # use prop_decrease to control reduction strength (0..1)
        return nr.reduce_noise(y=y, sr=int(sr), prop_decrease=float(strength))
    except Exception:
        # re-raise to let callers handle
        raise
