import os
import uuid
import wave
import subprocess
import numpy as np


class Recorder:
    """Simple recorder that registers a sink with SinkManager and writes WAV.

    The sink is registered via a provided SinkManager instance; the worker
    thread created by SinkManager will call the sink callable and perform
    writes, so no extra threading is required here.
    """

    def __init__(self, sink_mgr):
        self.sink_mgr = sink_mgr
        self._sid = None
        self._wf = None
        self._tmp_path = None
        self._target_path = None

    def is_recording(self):
        return self._sid is not None

    def start(self, target_path: str, samplerate: int, channels: int):
        if self.is_recording():
            return {"error": "already recording"}
        if not target_path:
            return {"error": "no target path"}

        try:
            target_path = str(target_path)
            if not target_path.lower().endswith('.mp3'):
                base = os.path.splitext(target_path)[0]
                mp3_target = base + '.mp3'
            else:
                mp3_target = target_path

            tmp_name = f'.pymic_rec_{uuid.uuid4().hex}.wav'
            tmp_path = os.path.join(os.path.dirname(mp3_target) or '.', tmp_name)

            wf = wave.open(tmp_path, 'wb')
            wf.setnchannels(int(channels or 1))
            wf.setsampwidth(2)
            wf.setframerate(int(samplerate or 44100))

            def _sink(frames):
                try:
                    if frames is None:
                        return
                    arr = np.asarray(frames, dtype=np.float32)
                    if arr.size == 0:
                        return
                    arr = np.clip(arr, -1.0, 1.0)
                    int16 = (arr * 32767.0).astype(np.int16)
                    try:
                        wf.writeframes(int16.tobytes())
                    except Exception:
                        pass
                except Exception:
                    pass

            resp = self.sink_mgr.register(_sink)
            if resp.get('error') or not resp.get('id'):
                try:
                    wf.close()
                except Exception:
                    pass
                return {"error": "failed to register recorder sink"}

            self._sid = resp.get('id')
            self._wf = wf
            self._tmp_path = tmp_path
            self._target_path = mp3_target
            return {"ok": True}
        except Exception as e:
            try:
                if self._wf is not None:
                    self._wf.close()
            except Exception:
                pass
            return {"error": str(e)}

    def stop(self):
        if not self.is_recording():
            return {"error": "not recording"}
        try:
            sid = self._sid
            try:
                # unregister will signal the worker and join
                self.sink_mgr.unregister(sid)
            except Exception:
                pass

            try:
                if self._wf is not None:
                    self._wf.close()
            except Exception:
                pass

            tmp = self._tmp_path
            target = self._target_path

            self._sid = None
            self._wf = None
            self._tmp_path = None
            self._target_path = None

            if not tmp or not os.path.exists(tmp):
                return {"error": "temporary wav not found"}

            try:
                cmd = [
                    'ffmpeg', '-y', '-i', tmp, '-codec:a', 'libmp3lame', '-qscale:a', '2', target
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    return {"error": "ffmpeg conversion failed", "stderr": proc.stderr.decode(errors='replace')}
            except FileNotFoundError:
                return {"error": "ffmpeg not found on PATH; install ffmpeg to enable mp3 export"}
            except Exception as e:
                return {"error": str(e)}

            try:
                os.remove(tmp)
            except Exception:
                pass

            return {"ok": True, "path": str(target)}
        except Exception as e:
            return {"error": str(e)}
