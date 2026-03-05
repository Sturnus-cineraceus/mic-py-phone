import traceback
import math
import numpy as np

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
        # volume as linear multiplier (1.0 = unchanged)
        self.volume = 1.0
        # Noise gate settings
        self.gate_enabled = False
        self.gate_threshold_db = -40.0
        self.gate_attack_ms = 10.0
        self.gate_release_ms = 100.0
        # High-pass filter settings
        self.hpf_enabled = False
        self.hpf_cutoff_hz = 80.0

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

    def get_gain_db(self):
        try:
            # avoid log10(0)
            if self.volume <= 0:
                gain_db = -999.0
            else:
                gain_db = 20.0 * math.log10(float(self.volume))
            return {"gain_db": float(gain_db)}
        except Exception as e:
            return {"error": str(e)}

    def set_gain_db(self, db):
        try:
            dbf = float(db)
            self.volume = float(10.0 ** (dbf / 20.0))
            return {"gain_db": dbf}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def get_gate_settings(self):
        try:
            return {
                "enabled": bool(self.gate_enabled),
                "threshold_db": float(self.gate_threshold_db),
                "attack_ms": float(self.gate_attack_ms),
                "release_ms": float(self.gate_release_ms),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_gate_enabled(self, enabled):
        try:
            self.gate_enabled = bool(enabled)
            return {"enabled": self.gate_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_threshold_db(self, db):
        try:
            self.gate_threshold_db = float(db)
            return {"threshold_db": self.gate_threshold_db}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_attack_ms(self, ms):
        try:
            self.gate_attack_ms = float(ms)
            return {"attack_ms": self.gate_attack_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_gate_release_ms(self, ms):
        try:
            self.gate_release_ms = float(ms)
            return {"release_ms": self.gate_release_ms}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    # High-pass filter API
    def get_hpf_settings(self):
        try:
            return {"enabled": bool(self.hpf_enabled), "cutoff_hz": float(self.hpf_cutoff_hz)}
        except Exception as e:
            return {"error": str(e)}

    def set_hpf_enabled(self, enabled):
        try:
            self.hpf_enabled = bool(enabled)
            return {"enabled": self.hpf_enabled}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

    def set_hpf_cutoff_hz(self, hz):
        try:
            hzf = float(hz)
            if hzf <= 0:
                return {"error": "cutoff must be > 0"}
            self.hpf_cutoff_hz = hzf
            return {"cutoff_hz": self.hpf_cutoff_hz}
        except Exception as e:
            return {"error": "invalid value", "detail": str(e)}

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

            # helper: scale a 1-D buffer into the requested target dtype safely
            def _scale_buffer(buf, target_dtype):
                # buf: 1-d ndarray
                # target_dtype: numpy dtype to cast final result into
                # Work in float32 normalized range to avoid repeated integer quantization loss.
                if np.issubdtype(buf.dtype, np.integer) or np.issubdtype(target_dtype, np.integer):
                    # Determine integer target bounds
                    tgt_info = np.iinfo(target_dtype) if np.issubdtype(target_dtype, np.integer) else np.iinfo(buf.dtype)
                    denom = float(max(abs(tgt_info.min), abs(tgt_info.max)))
                    f = buf.astype(np.float32) / denom
                    f *= float(self.volume)
                    f = np.clip(f, -1.0, 1.0 - (1.0 / denom))
                    return np.rint(f * denom).astype(target_dtype)
                else:
                    # float path, assume -1.0..1.0 range
                    f = buf.astype(np.float32) * float(self.volume)
                    f = np.clip(f, -1.0, 1.0)
                    return f.astype(target_dtype)
            # prepare gate smoothing coefficients (used in closure)
            gate_enabled = bool(self.gate_enabled)
            gate_threshold_db = float(self.gate_threshold_db)
            gate_attack_ms = float(self.gate_attack_ms)
            gate_release_ms = float(self.gate_release_ms)
            # compute per-sample smoothing alphas
            alpha_attack = math.exp(-1.0 / (max(samplerate * (gate_attack_ms / 1000.0), 1.0)))
            alpha_release = math.exp(-1.0 / (max(samplerate * (gate_release_ms / 1000.0), 1.0)))

            # envelope and gain state for closure
            env = 0.0
            gain_sm = 1.0

            # HPF state: we'll implement a biquad HPF with per-channel state and allow runtime coefficient updates
            hpf_enabled = False
            hpf_cutoff_prev = None
            # biquad coeffs (normalized): b0,b1,b2,a1,a2
            b0 = b1 = b2 = a1 = a2 = 0.0
            # per-channel delay states
            hpf_x1 = np.zeros(channels, dtype=np.float32)
            hpf_x2 = np.zeros(channels, dtype=np.float32)
            hpf_y1 = np.zeros(channels, dtype=np.float32)
            hpf_y2 = np.zeros(channels, dtype=np.float32)

            def callback(indata, outdata, frames, time, status):
                nonlocal hpf_enabled, hpf_cutoff_prev, b0, b1, b2, a1, a2
                if status:
                    # ignore status, don't raise inside audio callback
                    pass
                try:
                    # normalize input to -1..1 float32
                    if np.issubdtype(indata.dtype, np.integer):
                        info = np.iinfo(indata.dtype)
                        denom = float(max(abs(info.min), abs(info.max)))
                        fdata = indata.astype(np.float32) / denom
                    else:
                        fdata = indata.astype(np.float32)

                    # ensure 2D shape (frames, channels)
                    if fdata.ndim == 1:
                        fdata = fdata.reshape(-1, 1)

                    # apply HPF per-sample if enabled (biquad). Recompute coeffs if cutoff changed.
                    cur_hpf_enabled = bool(self.hpf_enabled)
                    cur_cutoff = float(self.hpf_cutoff_hz)
                    if cur_hpf_enabled and (not hpf_enabled or hpf_cutoff_prev != cur_cutoff):
                        # compute biquad HPF coefficients (RBJ cookbook), Q=0.707
                        fs = float(samplerate)
                        f0 = max(1.0, min(cur_cutoff, fs / 2.0 - 1.0))
                        Q = 0.7071
                        omega = 2.0 * math.pi * f0 / fs
                        sn = math.sin(omega)
                        cs = math.cos(omega)
                        alpha_b = sn / (2.0 * Q)
                        b0_raw = (1 + cs) / 2.0 * 1.0
                        b1_raw = -(1 + cs)
                        b2_raw = (1 + cs) / 2.0
                        a0_raw = 1.0 + alpha_b
                        a1_raw = -2.0 * cs
                        a2_raw = 1.0 - alpha_b
                        b0 = b0_raw / a0_raw
                        b1 = b1_raw / a0_raw
                        b2 = b2_raw / a0_raw
                        a1 = a1_raw / a0_raw
                        a2 = a2_raw / a0_raw
                        hpf_enabled = True
                        hpf_cutoff_prev = cur_cutoff
                    elif not cur_hpf_enabled:
                        hpf_enabled = False

                    if hpf_enabled:
                        nch = min(fdata.shape[1], channels)
                        out_f = np.empty_like(fdata)
                        # per-sample per-channel biquad
                        for i in range(fdata.shape[0]):
                            for ch in range(nch):
                                x = float(fdata[i, ch])
                                y = b0 * x + b1 * hpf_x1[ch] + b2 * hpf_x2[ch] - a1 * hpf_y1[ch] - a2 * hpf_y2[ch]
                                out_f[i, ch] = y
                                hpf_x2[ch] = hpf_x1[ch]
                                hpf_x1[ch] = x
                                hpf_y2[ch] = hpf_y1[ch]
                                hpf_y1[ch] = y
                            if fdata.shape[1] > nch:
                                out_f[i, nch:] = fdata[i, nch:]
                        fdata = out_f

                    # apply noise gate decision based on RMS envelope (soft knee + smoothed gain)
                    if bool(self.gate_enabled):
                        nonlocal env, gain_sm
                        # compute RMS across channels
                        if fdata.size == 0:
                            rms = 0.0
                        else:
                            rms = float(np.sqrt(np.mean(np.square(fdata.astype(np.float64)))))
                        # update envelope smoothing
                        if rms > env:
                            env = alpha_attack * env + (1.0 - alpha_attack) * rms
                        else:
                            env = alpha_release * env + (1.0 - alpha_release) * rms
                        env_db = 20.0 * math.log10(env + 1e-12)
                        # soft knee parameters
                        knee_db = 12.0
                        thr = float(self.gate_threshold_db)
                        if env_db >= thr:
                            target_gain = 1.0
                        elif env_db <= (thr - knee_db):
                            target_gain = 0.0
                        else:
                            # linear interpolation in dB domain
                            t = (env_db - (thr - knee_db)) / knee_db
                            target_gain = max(0.0, min(1.0, t))
                        # choose attack/release for gain smoothing
                        if target_gain > gain_sm:
                            alpha_g = alpha_attack
                        else:
                            alpha_g = alpha_release
                        gain_sm = alpha_g * gain_sm + (1.0 - alpha_g) * target_gain
                        # apply smoothed gain
                        if gain_sm <= 0.001:
                            outdata.fill(0)
                            return
                        fdata = fdata * float(gain_sm)

                    # write to outdata, scaling per channel
                    if fdata.shape[1] == 1 and outdata.shape[1] > 1:
                        # mono to multi: fill first channel and zero others
                        out_ch_dtype = outdata.dtype
                        outdata[:, 0] = _scale_buffer(fdata[:, 0], out_ch_dtype)
                        if outdata.shape[1] > 1:
                            outdata[:, 1:] = 0
                    else:
                        nch = min(fdata.shape[1], outdata.shape[1])
                        for ch in range(nch):
                            out_ch_dtype = outdata.dtype
                            outdata[:, ch] = _scale_buffer(fdata[:, ch], out_ch_dtype)
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
