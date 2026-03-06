import threading
import queue
import numpy as np


class SinkManager:
    """Manage registered sinks: queueing, worker threads and dispatch.

    This is a thin port of the sink-related logic previously embedded in
    `pymic.api.Api` so that the Api class can delegate and stay smaller.
    """

    def __init__(self):
        self._sinks = {}
        self._sinks_lock = threading.Lock()
        self._next_sink_id = 1

    def register(self, sink_callable, *, policy: str = "drop", maxsize: int = 16):
        try:
            with self._sinks_lock:
                sid = self._next_sink_id
                self._next_sink_id += 1
                q = queue.Queue(maxsize=maxsize)
                stop_ev = threading.Event()
                metrics = {"dropped": 0, "processed": 0}

                def _worker():
                    # worker consumes queued frames and calls sink
                    while not stop_ev.is_set():
                        try:
                            item = q.get()
                            if item is None:
                                break
                            try:
                                # support object-style sinks with `consume` or plain callables
                                if hasattr(sink_callable, "consume"):
                                    sink_callable.consume(item, meta={})
                                else:
                                    sink_callable(item)
                                metrics["processed"] += 1
                            except Exception:
                                # swallow to avoid crashing worker
                                pass
                        except Exception:
                            continue

                th = threading.Thread(target=_worker, daemon=True)
                th.start()
                self._sinks[sid] = {
                    "fn": sink_callable,
                    "queue": q,
                    "thread": th,
                    "stop": stop_ev,
                    "policy": policy,
                    "metrics": metrics,
                }
            return {"ok": True, "id": sid}
        except Exception as e:
            return {"error": str(e)}

    def unregister(self, sid):
        try:
            with self._sinks_lock:
                info = self._sinks.pop(sid, None)
            if info is not None:
                try:
                    info.get("stop").set()
                except Exception:
                    pass
                try:
                    q = info.get("queue")
                    if q is not None:
                        try:
                            q.put_nowait(None)
                        except Exception:
                            try:
                                q.put(None, block=False)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    th = info.get("thread")
                    if th is not None and th.is_alive():
                        th.join(timeout=1.0)
                except Exception:
                    pass
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def dispatch(self, frames):
        try:
            if frames is None:
                return
            arr = np.asarray(frames, dtype=np.float32)
            with self._sinks_lock:
                sinks = list(self._sinks.items())
            for sid, info in sinks:
                try:
                    q = info.get("queue")
                    if q is None:
                        continue
                    policy = info.get("policy", "drop")
                    try:
                        q.put_nowait(arr.copy())
                    except queue.Full:
                        # handle backpressure according to policy
                        try:
                            if policy == "block":
                                q.put(arr.copy(), timeout=0.1)
                                continue
                        except Exception:
                            pass
                        # drop by default
                        try:
                            info.get("metrics")["dropped"] += 1
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def has_sinks(self):
        try:
            with self._sinks_lock:
                return bool(self._sinks)
        except Exception:
            return False

    def get_metrics(self, sid):
        try:
            with self._sinks_lock:
                info = self._sinks.get(sid)
            if not info:
                return {"error": "not found"}
            return {"metrics": info.get("metrics", {})}
        except Exception as e:
            return {"error": str(e)}
