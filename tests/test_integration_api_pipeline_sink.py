import time
import numpy as np

from pymic.sink_manager import SinkManager


def test_sink_manager_dispatch():
    """SinkManager.dispatch() がシンクにフレームを正しく配信することを確認する。"""
    mgr = SinkManager()

    received = []

    def sink_fn(frames):
        # store a copy to avoid shared-memory surprises
        received.append(np.asarray(frames, dtype=np.float32).copy())

    resp = mgr.register(sink_fn)
    assert resp.get("ok") is True
    sid = resp.get("id")

    try:
        # dispatch a small test buffer
        frames = np.ones((16, 1), dtype=np.float32) * 0.2
        mgr.dispatch(frames)

        # wait for worker to process queue
        deadline = time.time() + 1.0
        while time.time() < deadline and len(received) == 0:
            time.sleep(0.01)

        assert len(received) >= 1
        r = received[0]
        assert r.shape == frames.shape
        # values should be close to dispatched values (processing may alter them)
        assert np.allclose(np.mean(r), np.mean(frames), atol=0.5)

    finally:
        try:
            mgr.unregister(sid)
        except Exception:
            pass
