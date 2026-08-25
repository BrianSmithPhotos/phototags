"""Application setup and startup helpers."""

from __future__ import annotations

from argparse import ArgumentParser
import re
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from phototags.ui.main_window import MainWindow


DEFAULT_SOURCE_CANDIDATES: tuple[Path, ...] = (
    Path("/Volumes/OM SYSTEM"),
    Path("/Volumes/OM System"),
    Path("/volumes/OM SYSTEM"),
    Path("/volumes/OM System"),
)

FALLBACK_SOURCE_DIR = Path("/Volumes")

# Drawn by Tools/IconGen; see docs/PACKAGING.md. The .app bundle gets its icon
# from resources/AppIcon.icns via Info.plist, but a plain `uv run python
# main.py` has no bundle and so no plist to name one - Qt has to be handed the
# image itself or the Dock shows a generic Python rocket.
APP_ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "AppIcon.png"

# Olympus/OM System cameras roll over to a new DCIM subfolder named
# "<3-digit-number>OMSYS" every 10,000 images (e.g. "105OMSYS"). Two such
# folders rarely coexist, but when they do the lower-numbered one is the
# one still being imported from.
_OMSYS_FOLDER_PATTERN = re.compile(r"^(\d{3})OMSYS$", re.IGNORECASE)


def _lowest_numbered_omsys_dir(sd_card_root: Path) -> Path | None:
    """Return the lowest-numbered DCIM/<NNN>OMSYS folder under an SD card root."""
    dcim_dir = sd_card_root / "DCIM"
    if not dcim_dir.is_dir():
        return None
    numbered_dirs: list[tuple[int, Path]] = []
    try:
        for entry in dcim_dir.iterdir():
            match = _OMSYS_FOLDER_PATTERN.match(entry.name) if entry.is_dir() else None
            if match is not None:
                numbered_dirs.append((int(match.group(1)), entry))
    except OSError:
        return None
    if not numbered_dirs:
        return None
    return min(numbered_dirs, key=lambda item: item[0])[1]


def detect_default_source_dir() -> Path:
    """Return the active DCIM/<NNN>OMSYS folder on a mounted SD card, else /Volumes."""
    for candidate_root in DEFAULT_SOURCE_CANDIDATES:
        if not candidate_root.exists():
            continue
        omsys_dir = _lowest_numbered_omsys_dir(candidate_root)
        if omsys_dir is not None:
            return omsys_dir
    return FALLBACK_SOURCE_DIR


def build_parser() -> ArgumentParser:
    """Build CLI argument parser for app startup."""
    parser = ArgumentParser(description="MacPhotoMaster")
    parser.add_argument(
        "--source",
        type=Path,
        default=detect_default_source_dir(),
        help="Initial source directory, defaults to the SD card mount path.",
    )
    parser.add_argument(
        "--dark",
        action="store_true",
        help="Launch in dark mode (light mode is the default).",
    )
    parser.add_argument(
        "--smoke-test-ms",
        type=int,
        default=0,
        help="Exit automatically after N milliseconds (used for automated smoke tests).",
    )
    return parser


def run(source_dir: Path, smoke_test_ms: int = 0) -> int:
    """Run the Qt event loop.

    Args:
        source_dir: Initial folder path shown in the source panel.
        smoke_test_ms: If positive, auto-quit after this duration.

    Returns:
        The Qt application exit code.
    """
    app = QApplication([])
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow(source_dir=source_dir)
    window.show()

    if smoke_test_ms > 0:
        QTimer.singleShot(smoke_test_ms, app.quit)

    return app.exec()


def main() -> int:
    """Parse CLI args and start the application."""
    args = build_parser().parse_args()
    return run(source_dir=args.source, smoke_test_ms=args.smoke_test_ms)
