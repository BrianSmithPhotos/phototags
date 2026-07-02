"""Resolve the exiftool binary path, robust to GUI-launched app bundles."""

from __future__ import annotations

from pathlib import Path
import shutil

_HOMEBREW_CANDIDATES = (
    "/opt/homebrew/bin/exiftool",  # Homebrew on Apple Silicon
    "/usr/local/bin/exiftool",  # Homebrew on Intel
)


def _resolve_exiftool_path() -> str:
    """Locate exiftool, falling back past PATH for GUI-launched app bundles.

    macOS launches .app bundles (Dock/Finder/`open`) with a minimal PATH
    (`/usr/bin:/bin:/usr/sbin:/sbin`) that excludes Homebrew's install
    directories, so a bare "exiftool" lookup that works from a terminal shell
    fails with FileNotFoundError inside the packaged app.
    """
    found = shutil.which("exiftool")
    if found is not None:
        return found
    for candidate in _HOMEBREW_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return "exiftool"


EXIFTOOL_PATH = _resolve_exiftool_path()
