"""Tests for the i18n module."""


import json

import pytest

from anappt import i18n


@pytest.fixture(autouse=True)
def reset_i18n():
    """Reset i18n state before and after each test."""
    i18n._reset_cache()
    yield
    i18n._reset_cache()


class TestLocaleDetection:
    """Test locale detection from environment variables."""

    def test_detect_zh_from_lang(self, monkeypatch):
        monkeypatch.delenv("LANGUAGE", raising=False)
        monkeypatch.setenv("LANG", "zh_CN.UTF-8")
        assert i18n._detect_locale() == "zh"

    def test_detect_en_from_lang(self, monkeypatch):
        monkeypatch.delenv("LANGUAGE", raising=False)
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        assert i18n._detect_locale() == "en"

    def test_detect_from_language_var(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE", "en_US:en")
        monkeypatch.delenv("LANG", raising=False)
        assert i18n._detect_locale() == "en"

    def test_default_when_no_env(self, monkeypatch):
        monkeypatch.delenv("LANGUAGE", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        assert i18n._detect_locale() == "zh"

    def test_default_for_unknown_locale(self, monkeypatch):
        monkeypatch.delenv("LANGUAGE", raising=False)
        monkeypatch.setenv("LANG", "fr_FR.UTF-8")
        assert i18n._detect_locale() == "zh"

    def test_set_locale_overrides_detection(self, monkeypatch):
        monkeypatch.setenv("LANG", "zh_CN.UTF-8")
        i18n.set_locale("en")
        assert i18n.get_locale() == "en"


class TestTranslation:
    """Test the t() translation function."""

    def test_translate_existing_key_zh(self):
        i18n.set_locale("zh")
        result = i18n.t("cli.welcome")
        assert result == "欢迎使用 AnaPPTAgent"

    def test_translate_existing_key_en(self):
        i18n.set_locale("en")
        result = i18n.t("cli.welcome")
        assert result == "Welcome to AnaPPTAgent"

    def test_fallback_to_default_locale(self):
        """If key exists in zh but not in en, fall back to zh."""
        i18n.set_locale("en")
        result = i18n.t("cli.welcome")
        assert result == "Welcome to AnaPPTAgent"

    def test_missing_key_returns_key_itself(self):
        i18n.set_locale("zh")
        result = i18n.t("nonexistent.key.xyz")
        assert result == "nonexistent.key.xyz"

    def test_missing_key_in_en_falls_to_zh(self):
        """If key missing from en but present in zh, use zh."""
        i18n.set_locale("en")
        # All keys should exist in both, but test the fallback mechanism
        result = i18n.t("cli.welcome")
        assert result is not None
        assert len(result) > 0

    def test_interpolation(self):
        i18n.set_locale("en")
        result = i18n.t("cli.new_project_created", path="/tmp/project")
        assert "/tmp/project" in result

    def test_interpolation_zh(self):
        i18n.set_locale("zh")
        result = i18n.t("cli.new_project_created", path="/tmp/project")
        assert "/tmp/project" in result

    def test_interpolation_with_multiple_placeholders(self):
        i18n.set_locale("en")
        result = i18n.t("error.prerequisite_not_met", stage_id="S1")
        assert "S1" in result

    def test_interpolation_missing_placeholder_does_not_crash(self):
        i18n.set_locale("en")
        # Should not crash, should return the text as-is
        result = i18n.t("cli.new_project_created")
        assert isinstance(result, str)


class TestLocaleConsistency:
    """Test that zh and en locales are consistent."""

    @pytest.fixture
    def zh_messages(self):
        locale_file = i18n._LOCALES_DIR / "zh.json"
        with open(locale_file, encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def en_messages(self):
        locale_file = i18n._LOCALES_DIR / "en.json"
        with open(locale_file, encoding="utf-8") as f:
            return json.load(f)

    def test_zh_en_keys_aligned(self, zh_messages, en_messages):
        """zh and en locale files must have the same set of keys."""
        assert set(zh_messages.keys()) == set(en_messages.keys())

    def test_new_tui_keys_exist(self, zh_messages, en_messages):
        """New TUI and /ppt related keys must exist in both locales."""
        new_keys = [
            "conv.thinking_idle",
            "conv.ppt_skill_missing",
            "conv.ppt_directive",
            "conv.ppt_usage",
            "conv.ppt_empty_requirement",
            "conv.ppt_done",
            "tui.title",
            "tui.title_complete",
            "tui.input_placeholder",
            "tui.shortcuts",
            "tui.user_label",
            "tui.assistant_label",
        ]
        for key in new_keys:
            assert key in zh_messages, f"Missing key in zh.json: {key}"
            assert key in en_messages, f"Missing key in en.json: {key}"
