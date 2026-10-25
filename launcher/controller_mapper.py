#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Compatibility shim for controller mapping utilities."""

from sumeragi_controller_controls import (
    DEFAULT_PAD_CONTROLS,
    LOGICAL_ACTIONS,
    VALID_ACTION_NAMES,
    VALID_SDL_BUTTONS,
    BUTTON_LABELS,
    ControllerControlsWindow,
    bind_button,
    build_pad_map_spec,
    diff_controls,
    format_button_label,
    get_default_controls,
    reset_all_controls,
    reset_button,
    validate_controls,
)

__all__ = [
    "DEFAULT_PAD_CONTROLS",
    "LOGICAL_ACTIONS",
    "VALID_ACTION_NAMES",
    "VALID_SDL_BUTTONS",
    "BUTTON_LABELS",
    "ControllerControlsWindow",
    "bind_button",
    "build_pad_map_spec",
    "diff_controls",
    "format_button_label",
    "get_default_controls",
    "reset_all_controls",
    "reset_button",
    "validate_controls",
]
