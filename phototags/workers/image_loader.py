"""Background image loaders used by the UI."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import subprocess

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtCore import QObject, QRunnable, Signal

RAW_SUFFIXES = {".orf", ".raf", ".nef", ".cr2", ".cr3", ".arw", ".rw2"}


class ImageLoadSignals(QObject):
    """Signals emitted by image loading workers."""

    loaded = Signal(str, bytes, int, int)
    failed = Signal(str, str)


class ImageLoadTask(QRunnable):
    """Load and optionally downscale an image in a background thread."""

    def __init__(self, image_path: Path, signals: ImageLoadSignals, max_edge: int) -> None:
        super().__init__()
        self.image_path = image_path
        self.signals = signals
        self.max_edge = max_edge

    def run(self) -> None:
        """Decode image and emit PNG bytes with size metadata."""
        try:
            normalized = self._load_best_image()
            width, height = normalized.size
            largest_edge = max(width, height)
            if largest_edge > self.max_edge:
                scale = self.max_edge / float(largest_edge)
                new_size = (int(width * scale), int(height * scale))
                normalized = normalized.resize(new_size, Image.Resampling.LANCZOS)

            out = BytesIO()
            normalized.save(out, format="PNG")
            data = out.getvalue()
            out_width, out_height = normalized.size
            try:
                self.signals.loaded.emit(str(self.image_path), data, out_width, out_height)
            except RuntimeError:
                return
        except (OSError, ValueError, UnidentifiedImageError, subprocess.SubprocessError) as exc:
            try:
                self.signals.failed.emit(str(self.image_path), str(exc))
            except RuntimeError:
                return

    def _load_best_image(self) -> Image.Image:
        """Load image via Pillow, with exiftool preview fallback for RAW formats."""
        try:
            return self._load_with_pillow(self.image_path)
        except UnidentifiedImageError:
            if self.image_path.suffix.lower() not in RAW_SUFFIXES:
                raise
            return self._load_with_exiftool_preview(self.image_path)

    def _load_with_pillow(self, path: Path) -> Image.Image:
        """Load and normalize image from file path using Pillow."""
        with Image.open(path) as img:
            normalized = ImageOps.exif_transpose(img)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGB")
            return normalized.copy()

    def _load_with_exiftool_preview(self, path: Path) -> Image.Image:
        """Extract embedded RAW preview via exiftool and decode with Pillow."""
        result = subprocess.run(
            ["exiftool", "-b", "-PreviewImage", str(path)],
            capture_output=True,
            check=False,
            timeout=8,
        )
        if result.returncode != 0 or not result.stdout:
            raise UnidentifiedImageError(f"No preview extracted for {path.name}")

        preview_buffer = BytesIO(result.stdout)
        with Image.open(preview_buffer) as preview:
            normalized = ImageOps.exif_transpose(preview)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGB")
            return normalized.copy()
