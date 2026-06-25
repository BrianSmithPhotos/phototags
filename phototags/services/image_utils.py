"""Pure image utility functions shared across services and workers."""

from __future__ import annotations

from PIL import Image

_EXIF_TRANSPOSE: dict[int, Image.Transpose] = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def apply_exif_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """Apply an EXIF Orientation integer to an image, returning a correctly-oriented copy.

    EXIF Orientation 1 is upright (identity).  Values 2–8 encode rotations and
    mirror flips.  Any value outside 1–8 is treated as 1 (no transform applied).

    Use this instead of ImageOps.exif_transpose when the orientation value comes
    from the *outer* file's EXIF (e.g. an ORF's Orientation tag) rather than from
    the embedded image stream's own EXIF header, where exif_transpose would be a
    no-op because the embedded preview JPEG carries no Orientation tag of its own.
    """
    method = _EXIF_TRANSPOSE.get(orientation)
    if method is None:
        return img
    return img.transpose(method)
