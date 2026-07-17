"""Internationalization (i18n) module for AnaPPTAgent.

Provides locale detection and message translation with placeholder interpolation.
Supports Chinese (zh) and English (en), with fallback to Chinese.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent / "locales"
_MESSAGES_CACHE: dict[str, dict[str, str]] = {}
_DEFAULT_LOCALE = "zh"
_current_locale: str | None = None


def _detect_locale() -> str:
    """Detect locale from LANG / LANGUAGE environment variables.

    Returns 'zh' for Chinese locales, 'en' for English, defaults to 'zh'.
    """
    for var_name in ("LANGUAGE", "LANG"):
        raw = os.environ.get(var_name, "")
        if not raw:
            continue
        lang = raw.split(":")[0].split(".")[0].lower()
        if lang.startswith("zh"):
            return "zh"
        if lang.startswith("en"):
            return "en"
        if lang in ("zh", "en"):
            return lang
    return _DEFAULT_LOCALE


def get_locale() -> str:
    """Return the current locale, detecting it if not explicitly set."""
    global _current_locale
    if _current_locale is None:
        _current_locale = _detect_locale()
    return _current_locale


def set_locale(locale: str) -> None:
    """Explicitly set the current locale.

    Args:
        locale: Locale code ('zh' or 'en').
    """
    global _current_locale
    _current_locale = locale


def _load_messages(locale: str) -> dict[str, str]:
    """Load message catalog for the given locale, with caching."""
    if locale in _MESSAGES_CACHE:
        return _MESSAGES_CACHE[locale]
    locale_file = _LOCALES_DIR / f"{locale}.json"
    if locale_file.exists():
        with open(locale_file, encoding="utf-8") as f:
            _MESSAGES_CACHE[locale] = json.load(f)
    else:
        _MESSAGES_CACHE[locale] = {}
    return _MESSAGES_CACHE[locale]


def t(key: str, **kwargs: Any) -> str:
    """Translate a message key with optional placeholder interpolation.

    Looks up the key in the current locale's message catalog.
    If not found, falls back to the default locale (zh).
    If still not found, returns the key itself.

    Args:
        key: Message key (e.g., 'cli.welcome').
        **kwargs: Placeholder values for interpolation (e.g., name='World').

    Returns:
        Translated string with placeholders filled in.
    """
    locale = get_locale()
    messages = _load_messages(locale)
    if key not in messages:
        messages = _load_messages(_DEFAULT_LOCALE)
    text = messages.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def _reset_cache() -> None:
    """Reset the locale and message cache. For testing purposes."""
    global _current_locale, _MESSAGES_CACHE
    _current_locale = None
    _MESSAGES_CACHE.clear()
