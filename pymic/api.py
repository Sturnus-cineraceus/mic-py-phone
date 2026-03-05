import traceback

try:
    import sounddevice as sd
except Exception:
    sd = None


class Api:
    """Audio bypass API: list/select devices and start/stop a direct input->output passthrough."""

    def __init__(self):
        self.selected_input = None
        self.selected_output = None
        self.stream = None

    def get_audio_devices(self):
        if sd is None:
            return {"error": "sounddevice not available"}
        try:
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

            # Filter to WASAPI host APIs only (case-insensitive). If none are present,
            # return an error because the UI should allow selection only for WASAPI.
            wasapi_list = [h for h in hostapi_list if isinstance(h.get("name"), str) and "WASAPI" in h.get("name").upper()]
            if not wasapi_list:
                return {"error": "WASAPI host API not available on this system"}

            # Flatten devices from WASAPI hostapis and remove duplicates by index
            seen = set()
            wasapi_devices = []
            for h in wasapi_list:
                for d in h.get("devices", []):
                    if d and d.get("index") not in seen:
                        seen.add(d.get("index"))
                        wasapi_devices.append(d)

            return {
                "devices": wasapi_devices,
                "hostapis": wasapi_list,
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
        return {"input": self.selected_input, "output": self.selected_output}

    def is_running(self):
        return {"running": self.stream is not None}

    def start_bypass(self):
        if sd is None:
            return {"error": "sounddevice not available"}

        if self.stream is not None:
            return {"error": "already running"}

        if self.selected_input is None or self.selected_output is None:
            return {"error": "input or output device not selected"}

        try:
            in_dev = sd.query_devices(self.selected_input)
            out_dev = sd.query_devices(self.selected_output)

            samplerate = int(
                in_dev.get("default_samplerate")
                or out_dev.get("default_samplerate")
                or 44100
            )
            in_channels = in_dev.get("max_input_channels") or 1
            out_channels = out_dev.get("max_output_channels") or 1
            channels = max(in_channels, out_channels)

            def callback(indata, outdata, frames, time, status):
                if status:
                    # ignore status, don't raise inside audio callback
                    pass
                try:
                    # handle mono/stereo shapes
                    if indata.ndim == 1:
                        # mono input
                        outdata[:, 0] = indata
                        if outdata.shape[1] > 1:
                            outdata[:, 1:] = 0
                    else:
                        nch = min(indata.shape[1], outdata.shape[1])
                        outdata[:, :nch] = indata[:, :nch]
                        if outdata.shape[1] > nch:
                            outdata[:, nch:] = 0
                except Exception:
                    outdata.fill(0)

            self.stream = sd.Stream(
                device=(self.selected_input, self.selected_output),
                samplerate=samplerate,
                channels=channels,
                callback=callback,
            )
            self.stream.start()
            return {"running": True}
        except Exception as e:
            self.stream = None
            return {"error": str(e), "trace": traceback.format_exc()}

    def stop_bypass(self):
        if self.stream is None:
            return {"error": "not running"}
        try:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            return {"running": False}
        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}
