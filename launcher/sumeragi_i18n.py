#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Compatibility shim for Sumeragi Native+ i18n subsystem."""

from i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    I18nManager,
    get_available_languages,
    get_i18n,
    get_language,
    on_language_change,
    set_language,
    t,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "I18nManager",
    "get_available_languages",
    "get_i18n",
    "get_language",
    "on_language_change",
    "set_language",
    "t",
]
