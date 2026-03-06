import time
import numpy as np

from pymic.api import Api
from pymic.pipeline import BypassPipeline


def test_api_pipeline_sink_dispatch():
    api = Api()

    # inject a pipeline instance and apply current settings
    pipeline = BypassPipeline(samplerate=16000, channels=1)
    api._pipeline = pipeline
    api._maybe_apply_pipeline_settings()

    received = []

    def sink_fn(frames):
        # store a copy to avoid shared-memory surprises
        received.append(np.asarray(frames, dtype=np.float32).copy())

    resp = api.register_sink(sink_fn)
    assert resp.get("ok") is True
    sid = resp.get("id")

    try:
        # dispatch a small test buffer
        frames = np.ones((16, 1), dtype=np.float32) * 0.2
        api._dispatch_sinks(frames)

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
            api.unregister_sink(sid)
        except Exception:
            pass
