"""Application setup and startup helpers."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from phototags.ui.main_window import MainWindow


DEFAULT_SOURCE_CANDIDATES: tuple[Path, ...] = (
    Path("/Volumes/OM SYSTEM"),
    Path("/Volumes/OM System"),
    Path("/volumes/OM SYSTEM"),
    Path("/volumes/OM System"),
)


def detect_default_source_dir() -> Path:
    """Return best available default SD card source path."""
    for candidate in DEFAULT_SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_SOURCE_CANDIDATES[0]


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
    window = MainWindow(source_dir=source_dir)
    window.show()

    if smoke_test_ms > 0:
        QTimer.singleShot(smoke_test_ms, app.quit)

    return app.exec()


def main() -> int:
    """Parse CLI args and start the application."""
    args = build_parser().parse_args()
    return run(source_dir=args.source, smoke_test_ms=args.smoke_test_ms)
