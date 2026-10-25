# SPDX-License-Identifier: GPL-2.0-or-later
# Compatibility shim for SpartanPort localization table lookups.
import sumeragi_native_trophies


def table(language: str = "en"):
    """Returns the localization dictionary for the specified language."""
    return sumeragi_native_trophies.get_ui(language)
