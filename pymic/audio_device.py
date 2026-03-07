import traceback

try:
    import sounddevice as sd
except Exception:
    sd = None
import logging


def is_available():
    """sounddevice ライブラリが利用可能かどうかを返す。

    Returns:
        bool: 利用可能な場合は True、そうでない場合は False。
    """
    return sd is not None


def query_hostapis():
    """利用可能なホスト API のリストを返す。

    Returns:
        list: ホスト API 情報のリスト。sounddevice が未インストールの場合は空リスト。
    """
    if sd is None:
        return []
    return sd.query_hostapis()


def query_devices():
    """利用可能な音声デバイスのリストを返す。

    Returns:
        list: デバイス情報のリスト。sounddevice が未インストールの場合は空リスト。
    """
    if sd is None:
        return []
    return sd.query_devices()


def query_device(index):
    """指定インデックスの音声デバイス情報を返す。

    Args:
        index: デバイスインデックス。

    Returns:
        dict: デバイス情報。

    Raises:
        RuntimeError: sounddevice が利用できない場合。
    """
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.query_devices(index)


def get_default_device():
    """デフォルトの入出力デバイスインデックスをリストで返す。

    Returns:
        list または None: デフォルトデバイスのインデックスリスト。取得できない場合は None。
    """
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
    """sounddevice の入力ストリームを作成して返す。

    Args:
        device: 使用するデバイスのインデックス。
        samplerate: サンプルレート（Hz）。
        channels: チャンネル数。
        dtype: データ型（例: "float32"）。
        callback: フレーム受信時に呼ばれるコールバック関数。

    Returns:
        sd.InputStream: 作成された入力ストリーム。

    Raises:
        RuntimeError: sounddevice が利用できない場合。
    """
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.InputStream(
        device=device,
        samplerate=samplerate,
        channels=channels,
        dtype=dtype,
        callback=callback,
    )


def create_stream(device, samplerate, channels, callback):
    """sounddevice の全二重ストリームを作成して返す。

    Args:
        device: 使用するデバイスの (入力, 出力) インデックスタプル。
        samplerate: サンプルレート（Hz）。
        channels: チャンネル数。
        callback: フレーム処理時に呼ばれるコールバック関数。

    Returns:
        sd.Stream: 作成された全二重ストリーム。

    Raises:
        RuntimeError: sounddevice が利用できない場合。
    """
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.Stream(
        device=device, samplerate=samplerate, channels=channels, callback=callback
    )


def get_audio_devices():
    """WASAPI デバイスの一覧を取得して返す。

    Returns:
        dict: "devices"、"hostapis"、"default_device" キーを含む辞書。
              WASAPI が利用できない場合や例外発生時は "error" キーを返す。
    """
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

        resp = {
            "devices": wasapi_devices,
            "hostapis": wasapi_list,
            "default_device": default_dev,
        }
        logging.getLogger(__name__).info(
            "Enumerated audio devices: %d devices, default=%s",
            len(wasapi_devices),
            str(default_dev),
        )
        return resp
    except Exception as e:
        logging.getLogger(__name__).exception("Error enumerating audio devices")
        return {"error": str(e), "trace": traceback.format_exc()}
