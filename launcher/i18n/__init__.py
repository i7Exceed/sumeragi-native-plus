#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Internationalization (i18n) Engine for Sumeragi Native+.

Provides robust, centralized localization with:
- JSON-based translation dictionaries in locales/
- Default English fallback for missing keys
- Safe string formatting with named placeholders
- Dynamic language change notifications for runtime UI updates
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Set

# Supported languages mapping: code -> Native Display Name
SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "id": "Bahasa Indonesia",
}

DEFAULT_LANGUAGE = "en"


class SafeDict(dict):
    """Dictionary that leaves missing format keys intact instead of throwing KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class I18nManager:
    """Manages translation loading, fallback resolution, and language change subscriptions."""

    def __init__(self, default_lang: str = DEFAULT_LANGUAGE) -> None:
        self._current_lang = default_lang
        self._locales_dir = self._find_locales_dir()
        self._translations: Dict[str, Dict[str, str]] = {}
        self._fallback_dict: Dict[str, str] = {}
        self._subscribers: List[Callable[[str], None]] = []

        # Preload default fallback (English)
        self._fallback_dict = self._load_dict(DEFAULT_LANGUAGE)
        self._translations[DEFAULT_LANGUAGE] = self._fallback_dict

        # Load initial language
        self.set_language(default_lang, notify=False)

    def _find_locales_dir(self) -> Path:
        """Resolves the locales directory across source and PyInstaller environments."""
        candidates = [
            Path(__file__).resolve().parent / "locales",
            getattr(sys, "_MEIPASS", None) and Path(sys._MEIPASS) / "launcher" / "i18n" / "locales",
            getattr(sys, "_MEIPASS", None) and Path(sys._MEIPASS) / "locales",
            Path(__file__).resolve().parent.parent / "i18n" / "locales",
        ]
        for c in candidates:
            if c and c.is_dir():
                return c
        return Path(__file__).resolve().parent / "locales"

    def _load_dict(self, lang: str) -> Dict[str, str]:
        """Loads a JSON translation file for the given language code."""
        path = self._locales_dir / f"{lang}.json"
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def get_language(self) -> str:
        """Returns the currently active language code."""
        return self._current_lang

    def set_language(self, lang: str, notify: bool = True) -> bool:
        """Switches the active language, falling back to English if unsupported."""
        clean_lang = lang.lower().strip() if lang else DEFAULT_LANGUAGE
        if clean_lang not in SUPPORTED_LANGUAGES:
            clean_lang = DEFAULT_LANGUAGE

        self._current_lang = clean_lang
        if clean_lang not in self._translations:
            self._translations[clean_lang] = self._load_dict(clean_lang)

        if notify:
            for sub in list(self._subscribers):
                try:
                    sub(self._current_lang)
                except Exception:
                    pass
        return True

    def subscribe(self, callback: Callable[[str], None]) -> None:
        """Subscribes a callable to be notified when the active language changes."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str], None]) -> None:
        """Removes a previously subscribed callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def translate(self, key: str, **kwargs: Any) -> str:
        """Translates a key with safe fallback and safe placeholder replacement."""
        if not key:
            return ""

        current_dict = self._translations.get(self._current_lang, {})
        raw_text = current_dict.get(key)

        # Fallback to English if missing or empty
        if raw_text is None:
            raw_text = self._fallback_dict.get(key)

        # Fallback to key itself if not found anywhere
        if raw_text is None:
            raw_text = key

        if not kwargs:
            return raw_text

        # Format placeholders safely
        try:
            return raw_text.format_map(SafeDict(kwargs))
        except Exception:
            # If standard format fails, attempt manual token replace
            out = raw_text
            for k, v in kwargs.items():
                out = out.replace(f"{{{k}}}", str(v))
            return out

    def get_all_keys(self, lang: str) -> Set[str]:
        """Returns all keys present in the dictionary for the specified language."""
        return set(self._load_dict(lang).keys())


# Singleton instance
_i18n_instance = I18nManager()

# Global export helpers
def t(key: str, **kwargs: Any) -> str:
    """Translates a key into the currently active language with safe keyword formatting."""
    return _i18n_instance.translate(key, **kwargs)

def get_language() -> str:
    return _i18n_instance.get_language()

def set_language(lang: str, notify: bool = True) -> bool:
    return _i18n_instance.set_language(lang, notify=notify)

def on_language_change(callback: Callable[[str], None]) -> None:
    _i18n_instance.subscribe(callback)

def get_available_languages() -> Dict[str, str]:
    return dict(SUPPORTED_LANGUAGES)

def get_i18n() -> I18nManager:
    return _i18n_instance
