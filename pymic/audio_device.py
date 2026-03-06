import traceback

try:
    import sounddevice as sd
except Exception:
    sd = None


def is_available():
    return sd is not None


def query_hostapis():
    if sd is None:
        return []
    return sd.query_hostapis()


def query_devices():
    if sd is None:
        return []
    return sd.query_devices()


def query_device(index):
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.query_devices(index)


def get_default_device():
    if sd is None:
        return None
    try:
        default_dev = sd.default.device
        if default_dev is not None:
            try:
                return list(default_dev)
            except Exception:
                try:
                    return [int(default_dev)]
                except Exception:
                    return None
    except Exception:
        return None


def create_input_stream(device, samplerate, channels, dtype, callback):
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.InputStream(device=device, samplerate=samplerate, channels=channels, dtype=dtype, callback=callback)


def create_stream(device, samplerate, channels, callback):
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.Stream(device=device, samplerate=samplerate, channels=channels, callback=callback)


def get_audio_devices():
    if sd is None:
        return {"error": "sounddevice not available"}
    try:
        hostapis = sd.query_hostapis()
        devs = sd.query_devices()

        default_dev = get_default_device()

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

        wasapi_list = [
            h
            for h in hostapi_list
            if isinstance(h.get("name"), str) and "WASAPI" in h.get("name").upper()
        ]
        if not wasapi_list:
            return {"error": "WASAPI host API not available on this system"}

        seen = set()
        wasapi_devices = []
        for h in wasapi_list:
            for d in h.get("devices", []):
                if d and d.get("index") not in seen:
                    seen.add(d.get("index"))
                    wasapi_devices.append(d)

        return {"devices": wasapi_devices, "hostapis": wasapi_list, "default_device": default_dev}
    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}
