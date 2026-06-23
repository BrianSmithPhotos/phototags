"""Shared UI style values.

Light/dark mode is decided once at import time from a persisted QSettings
preference (toggled via the "Dark Mode" checkbox in the source panel) — there
is no live re-styling, the app must be restarted for a change to take effect.
Every color is exported as a plain module-level string constant so existing
`from phototags.ui.styles import ACCENT_CYAN, ...` imports keep working
unchanged regardless of which palette is active.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

DARK_MODE_SETTINGS_KEY = "ui/dark_mode"
SETTINGS_ORGANIZATION = "BrianSmithPhotos"
SETTINGS_APPLICATION = "MacPhotoMaster"


def _settings() -> QSettings:
    """Build the app's QSettings store with explicit org/app name.

    Explicit args (rather than QCoreApplication.setOrganizationName/
    setApplicationName + the no-arg constructor) avoid depending on import
    order: this module's palette selection runs at import time, which can
    happen before any app-level setup code has a chance to run.
    """
    return QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


@dataclass(frozen=True, slots=True)
class Palette:
    """Named color set for one theme (light or dark)."""

    accent_cyan: str
    orange_primary: str
    salmon_secondary: str
    dark_teal: str
    brown_text: str
    panel_background: str
    window_background: str
    tile_bg_default: str
    tile_bg_selected: str
    tile_border: str
    thumb_placeholder_border: str
    thumb_placeholder_bg: str
    button_disabled_bg: str
    button_disabled_text: str
    error_text: str
    variant_button_bg: str
    variant_button_border: str
    variant_button_checked_bg: str
    variant_button_checked_text: str
    preview_background: str


LIGHT_PALETTE = Palette(
    accent_cyan="#20d6d3",
    orange_primary="#d68220",
    salmon_secondary="#d6755f",
    dark_teal="#385756",
    brown_text="#574938",
    panel_background="#fbfaf8",
    window_background="#f1ede7",
    tile_bg_default="white",
    tile_bg_selected="#eefcfb",
    tile_border="#d6d2ce",
    thumb_placeholder_border="#e8e4df",
    thumb_placeholder_bg="#f8f6f4",
    button_disabled_bg="#d7ccc6",
    button_disabled_text="#f6f3f1",
    error_text="#c84d3a",
    variant_button_bg="#efe8e2",
    variant_button_border="#d8cdc4",
    variant_button_checked_bg="#dff7f6",
    variant_button_checked_text="#2e4746",
    preview_background="white",
)

# Dark grey background per the user's request; other colors lightened/brightened
# from their light-mode counterparts (not simply inverted) to keep WCAG-reasonable
# contrast against the dark grey surfaces.
DARK_PALETTE = Palette(
    accent_cyan="#20d6d3",
    orange_primary="#e8a050",
    salmon_secondary="#d6755f",
    dark_teal="#7fd9d6",
    brown_text="#d9cfc4",
    panel_background="#26282b",
    window_background="#1c1d1f",
    tile_bg_default="#2f3133",
    tile_bg_selected="#1f3a39",
    tile_border="#46484a",
    thumb_placeholder_border="#3d3f41",
    thumb_placeholder_bg="#343638",
    button_disabled_bg="#3a3b3d",
    button_disabled_text="#7a7a7a",
    error_text="#e8705a",
    variant_button_bg="#332f2a",
    variant_button_border="#4a4540",
    variant_button_checked_bg="#1f3a39",
    variant_button_checked_text="#bdf2f0",
    preview_background="#2f3133",
)


def is_dark_mode_enabled() -> bool:
    """Return the persisted dark-mode preference (default: off)."""
    return bool(_settings().value(DARK_MODE_SETTINGS_KEY, False, type=bool))


def set_dark_mode_enabled(enabled: bool) -> None:
    """Persist the dark-mode preference; takes effect on next app launch."""
    _settings().setValue(DARK_MODE_SETTINGS_KEY, enabled)


_ACTIVE_PALETTE = DARK_PALETTE if is_dark_mode_enabled() else LIGHT_PALETTE

ACCENT_CYAN = _ACTIVE_PALETTE.accent_cyan
ORANGE_PRIMARY = _ACTIVE_PALETTE.orange_primary
SALMON_SECONDARY = _ACTIVE_PALETTE.salmon_secondary
DARK_TEAL = _ACTIVE_PALETTE.dark_teal
BROWN_TEXT = _ACTIVE_PALETTE.brown_text
PANEL_BACKGROUND = _ACTIVE_PALETTE.panel_background
WINDOW_BACKGROUND = _ACTIVE_PALETTE.window_background
TILE_BG_DEFAULT = _ACTIVE_PALETTE.tile_bg_default
TILE_BG_SELECTED = _ACTIVE_PALETTE.tile_bg_selected
TILE_BORDER = _ACTIVE_PALETTE.tile_border
THUMB_PLACEHOLDER_BORDER = _ACTIVE_PALETTE.thumb_placeholder_border
THUMB_PLACEHOLDER_BG = _ACTIVE_PALETTE.thumb_placeholder_bg
BUTTON_DISABLED_BG = _ACTIVE_PALETTE.button_disabled_bg
BUTTON_DISABLED_TEXT = _ACTIVE_PALETTE.button_disabled_text
ERROR_TEXT = _ACTIVE_PALETTE.error_text
VARIANT_BUTTON_BG = _ACTIVE_PALETTE.variant_button_bg
VARIANT_BUTTON_BORDER = _ACTIVE_PALETTE.variant_button_border
VARIANT_BUTTON_CHECKED_BG = _ACTIVE_PALETTE.variant_button_checked_bg
VARIANT_BUTTON_CHECKED_TEXT = _ACTIVE_PALETTE.variant_button_checked_text
PREVIEW_BACKGROUND = _ACTIVE_PALETTE.preview_background
