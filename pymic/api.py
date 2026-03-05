from pathlib import Path
import platform
import sys
import traceback

try:
    import sounddevice as sd
except Exception:
    sd = None


class Api:
    def calculate(self, op, value):
        try:
            v = int(value)
        except Exception:
            return {"error": "invalid number"}

        if op == "square":
            return {"result": v * v}
        if op == "factorial":
            if v < 0 or v > 20:
                return {"error": "n must be between 0 and 20"}

            def fact(n):
                return 1 if n <= 1 else n * fact(n - 1)

            return {"result": fact(v)}

        return {"error": "unknown operation"}

    def get_system_info(self):
        return {"platform": platform.platform(), "python": sys.version.split()[0]}

    def echo(self, text):
        return {"echo": text}

    def get_audio_devices(self):
        if sd is None:
            return {"error": "sounddevice not available"}
        try:
            # Use host APIs to gather devices, but keep a flattened devices list for compatibility
            hostapis = sd.query_hostapis()
            devs = sd.query_devices()
            try:
                default_dev = sd.default.device
                if default_dev is not None:
                    try:
                        default_dev = list(default_dev)
                    except Exception:
                        try:
                            default_dev = [int(default_dev)]
                        except Exception:
                            default_dev = None
            except Exception:
                default_dev = None

            devices = []
            for i, d in enumerate(devs):
                devices.append(
                    {
                        "index": i,
                        "name": d.get("name"),
                        "max_input_channels": d.get("max_input_channels"),
                        "max_output_channels": d.get("max_output_channels"),
                        "default_samplerate": d.get("default_samplerate"),
                    }
                )

            hostapi_list = []
            for h in hostapis:
                h_name = h.get("name")
                h_devices = []
                for idx in h.get("devices", []):
                    if isinstance(idx, int) and 0 <= idx < len(devices):
                        h_devices.append(devices[idx])
                hostapi_list.append({"name": h_name, "devices": h_devices})

            return {
                "devices": devices,
                "hostapis": hostapi_list,
                "default_device": default_dev,
            }
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}

    def set_input_device(self, index):
        try:
            idx = int(index)
            self.selected_input = idx
            return {"selected_input": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def set_output_device(self, index):
        try:
            idx = int(index)
            self.selected_output = idx
            return {"selected_output": idx}
        except Exception as e:
            return {"error": "invalid index", "detail": str(e)}

    def get_selected_devices(self):
        return {
            "input": getattr(self, "selected_input", None),
            "output": getattr(self, "selected_output", None),
        }
