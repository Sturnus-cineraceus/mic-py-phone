"""オーディオデバイス操作のラッパーモジュール。

sounddevice ライブラリをラップし、デバイス一覧取得・ストリーム作成などの
共通インターフェースを提供する。sounddevice が利用不可の場合は安全にフォールバックする。
"""

import traceback

try:
    import sounddevice as sd
except Exception:
    sd = None
import logging


def is_available():
    """sounddevice ライブラリが利用可能かどうかを返す。"""
    return sd is not None


def query_hostapis():
    """利用可能なホスト API の一覧を返す。sounddevice 非対応時は空リストを返す。"""
    if sd is None:
        return []
    return sd.query_hostapis()


def query_devices():
    """利用可能な全オーディオデバイスの一覧を返す。sounddevice 非対応時は空リストを返す。"""
    if sd is None:
        return []
    return sd.query_devices()


def query_device(index):
    """指定インデックスのデバイス情報を返す。

    Args:
        index: デバイスのインデックス番号。

    Raises:
        RuntimeError: sounddevice が利用不可の場合。
    """
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.query_devices(index)


def get_default_device():
    """システムのデフォルトデバイス（入力・出力）のインデックスリストを返す。

    取得できない場合は None を返す。
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
    """sounddevice の入力専用ストリームを作成して返す。

    Args:
        device: 入力デバイスのインデックス。
        samplerate: サンプルレート（Hz）。
        channels: チャンネル数。
        dtype: サンプルのデータ型（例: 'float32'）。
        callback: 音声データを受け取るコールバック関数。

    Raises:
        RuntimeError: sounddevice が利用不可の場合。
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
    """sounddevice のフルデュプレックスストリームを作成して返す。

    Args:
        device: (入力デバイス, 出力デバイス) のタプル、またはデバイスインデックス。
        samplerate: サンプルレート（Hz）。
        channels: チャンネル数。
        callback: 音声データを処理するコールバック関数。

    Raises:
        RuntimeError: sounddevice が利用不可の場合。
    """
    if sd is None:
        raise RuntimeError("sounddevice not available")
    return sd.Stream(
        device=device, samplerate=samplerate, channels=channels, callback=callback
    )


def get_audio_devices():
    """WASAPI デバイス一覧とデフォルトデバイス情報を辞書形式で返す。

    Returns:
        成功時: {"devices": [...], "hostapis": [...], "default_device": ...}
        失敗時: {"error": "エラーメッセージ", "trace": "トレースバック"}
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
