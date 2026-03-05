"""Unit tests for pymic.settings_manager.SettingsManager."""

import json
from pathlib import Path

import pytest

from pymic.settings_manager import DEFAULT_SETTINGS, SettingsManager


@pytest.fixture()
def tmp_settings(tmp_path):
    """Return a SettingsManager whose data file lives in *tmp_path*."""
    manager = SettingsManager.__new__(SettingsManager)
    manager._settings_path = tmp_path / "settings.json"
    return manager


class TestResetDefaults:
    def test_returns_dict(self, tmp_settings):
        result = tmp_settings.reset_defaults()
        assert isinstance(result, dict)

    def test_matches_default_settings(self, tmp_settings):
        result = tmp_settings.reset_defaults()
        assert result == DEFAULT_SETTINGS

    def test_returns_independent_copy(self, tmp_settings):
        result = tmp_settings.reset_defaults()
        result["gain_db"] = 999
        assert DEFAULT_SETTINGS["gain_db"] != 999


class TestSave:
    def test_creates_file(self, tmp_settings):
        tmp_settings.save({"gain_db": 3.0})
        assert tmp_settings.settings_path.exists()

    def test_valid_json(self, tmp_settings):
        data = {"gain_db": 3.0, "input_device": 1}
        tmp_settings.save(data)
        with open(tmp_settings.settings_path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded == data

    def test_formatted_with_indent(self, tmp_settings):
        tmp_settings.save({"gain_db": 0.0})
        raw = tmp_settings.settings_path.read_text(encoding="utf-8")
        # indent=2 means there should be newlines and spaces in the file
        assert "\n" in raw
        assert "  " in raw

    def test_overwrites_existing_file(self, tmp_settings):
        tmp_settings.save({"gain_db": 1.0})
        tmp_settings.save({"gain_db": 2.0})
        with open(tmp_settings.settings_path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["gain_db"] == 2.0

    def test_creates_parent_dirs(self, tmp_path):
        manager = SettingsManager.__new__(SettingsManager)
        manager._settings_path = tmp_path / "nested" / "deep" / "settings.json"
        manager.save({"gain_db": 0.0})
        assert manager.settings_path.exists()


class TestLoad:
    def test_returns_defaults_when_no_file(self, tmp_settings):
        result = tmp_settings.load()
        assert result == DEFAULT_SETTINGS

    def test_loads_saved_data(self, tmp_settings):
        data = {"gain_db": 6.0, "nr": {"enabled": True, "strength": 0.8}}
        tmp_settings.save(data)
        result = tmp_settings.load()
        assert result == data

    def test_returns_defaults_on_invalid_json(self, tmp_settings):
        tmp_settings.settings_path.write_text("not valid json", encoding="utf-8")
        result = tmp_settings.load()
        assert result == DEFAULT_SETTINGS

    def test_returns_defaults_when_file_contains_non_dict(self, tmp_settings):
        tmp_settings.settings_path.write_text("[1, 2, 3]", encoding="utf-8")
        result = tmp_settings.load()
        assert result == DEFAULT_SETTINGS

    def test_roundtrip(self, tmp_settings):
        original = tmp_settings.reset_defaults()
        original["gain_db"] = 12.0
        original["gate"]["enabled"] = True
        tmp_settings.save(original)
        loaded = tmp_settings.load()
        assert loaded == original


class TestSettingsPath:
    def test_settings_path_property(self, tmp_settings):
        path = tmp_settings.settings_path
        assert isinstance(path, Path)
        assert path.name == "settings.json"

    def test_real_manager_uses_appdir(self):
        """SettingsManager should place the file in the user data dir."""
        manager = SettingsManager()
        assert manager.settings_path.name == "settings.json"
        # The parent directory should contain 'pymic' as part of the path
        assert "pymic" in str(manager.settings_path).lower()
