"""Background image loaders used by the UI."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtCore import QObject, QRunnable, Signal

from phototags.services.image_utils import apply_exif_orientation

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
        """Extract embedded RAW preview via exiftool and decode with Pillow.

        OM System (and other manufacturers) embed a preview JPEG that does not
        carry its own Orientation tag — the rotation is only recorded in the
        outer RAW file's EXIF.  A second exiftool call reads that tag and applies
        the correct transform so portrait shots render upright.
        """
        result = subprocess.run(
            ["exiftool", "-b", "-PreviewImage", str(path)],
            capture_output=True,
            check=False,
            timeout=8,
        )
        if result.returncode != 0 or not result.stdout:
            raise UnidentifiedImageError(f"No preview extracted for {path.name}")

        orientation = _read_raw_orientation(path)
        preview_buffer = BytesIO(result.stdout)
        with Image.open(preview_buffer) as preview:
            normalized = apply_exif_orientation(preview, orientation)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGB")
            return normalized.copy()


def _read_raw_orientation(path: Path) -> int:
    """Return the EXIF Orientation integer from a RAW file, or 1 (upright) on any failure."""
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-Orientation#", str(path)],
            capture_output=True,
            check=False,
            timeout=4,
        )
        if result.returncode != 0 or not result.stdout:
            return 1
        data = json.loads(result.stdout)
        return int(data[0].get("Orientation", 1))
    except (json.JSONDecodeError, IndexError, KeyError, ValueError, subprocess.TimeoutExpired):
        return 1
