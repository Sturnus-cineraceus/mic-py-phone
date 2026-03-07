"""Settings persistence module for pymic.

Saves and loads user settings as JSON to/from the platform-appropriate
user data directory (e.g. %APPDATA%\\pymic on Windows) using appdirs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from appdirs import user_data_dir
except ImportError:  # pragma: no cover – appdirs not installed

    def user_data_dir(appname: str, appauthor: str) -> str:  # type: ignore[misc]
        """Minimal fallback: use a .pymic directory next to this file."""
        return str(Path(__file__).parent.parent / ".pymic_data")


APP_NAME = "pymic"
APP_AUTHOR = "pymic"
SETTINGS_FILENAME = "settings.json"

# Default values mirror the defaults in Api.__init__
DEFAULT_SETTINGS: dict = {
    "gain_db": 0.0,
    "input_device": None,
    "output_device": None,
    "gate": {
        "enabled": False,
        "threshold_db": -40.0,
        "attack_ms": 10.0,
        "release_ms": 100.0,
    },
    "hpf": {
        "enabled": False,
        "cutoff_hz": 80.0,
    },
    "nr": {
        "enabled": False,
        "strength": 0.9,
    },
    "compressor": {
        "enabled": False,
        "threshold_db": -24.0,
        "ratio": 4.0,
        "attack_ms": 10.0,
        "release_ms": 120.0,
        "makeup_db": 0.0,
    },
    "dehiss": {
        "enabled": True,
        "strength": 0.65,
        "threshold_db": -58.0,
        "lpf_hz": 9000.0,
    },
}


class SettingsManager:
    """Persist and restore user settings to/from a JSON file.

    The settings file is stored in the platform-appropriate user data
    directory returned by :func:`appdirs.user_data_dir`.

    Example path on Windows::

        C:\\Users\\<user>\\AppData\\Roaming\\pymic\\settings.json
    """

    def __init__(self) -> None:
        """SettingsManager を初期化し、設定ファイルのパスを決定する。"""
        data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
        self._settings_path = Path(data_dir) / SETTINGS_FILENAME

    @property
    def settings_path(self) -> Path:
        """Return the absolute path to the settings file."""
        return self._settings_path

    def load(self) -> dict:
        """Load settings from disk.

        Returns the stored settings dict, or a copy of
        :data:`DEFAULT_SETTINGS` when the file does not exist or cannot
        be parsed.
        """
        if not self._settings_path.exists():
            return self.reset_defaults()
        try:
            with open(self._settings_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return self.reset_defaults()
            return data
        except (OSError, json.JSONDecodeError):
            import logging

            logging.getLogger(__name__).exception("Failed to load settings, resetting to defaults")
            return self.reset_defaults()

    def save(self, settings: dict) -> None:
        """Write *settings* to disk as formatted JSON (indent=2).

        Creates parent directories as needed.  Overwrites any existing
        settings file.

        Args:
            settings: Mapping of setting key → value to persist.

        Raises:
            OSError: If the file cannot be written.
        """
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._settings_path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, ensure_ascii=False)
            fh.write(os.linesep)
        import logging

        logging.getLogger(__name__).info("Saved settings to %s", str(self._settings_path))

    def reset_defaults(self) -> dict:
        """Return a fresh copy of the default settings dict."""
        import copy

        return copy.deepcopy(DEFAULT_SETTINGS)
