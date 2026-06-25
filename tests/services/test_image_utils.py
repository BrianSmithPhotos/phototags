from PIL import Image

from phototags.services.image_utils import apply_exif_orientation


def _landscape(width: int = 4, height: int = 2) -> Image.Image:
    """Return a solid-colour landscape image (width > height)."""
    return Image.new("RGB", (width, height), color=(200, 100, 50))


# ---------------------------------------------------------------------------
# Orientation 1: identity – no transform
# ---------------------------------------------------------------------------

def test_orientation_1_is_identity() -> None:
    img = _landscape()
    result = apply_exif_orientation(img, 1)
    assert result.size == (4, 2)


def test_orientation_1_pixel_unchanged() -> None:
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 0, 255))
    result = apply_exif_orientation(img, 1)
    assert result.getpixel((0, 0)) == (255, 0, 0)
    assert result.getpixel((1, 0)) == (0, 0, 255)


# ---------------------------------------------------------------------------
# Orientation 2: horizontal flip
# ---------------------------------------------------------------------------

def test_orientation_2_preserves_size() -> None:
    result = apply_exif_orientation(_landscape(), 2)
    assert result.size == (4, 2)


def test_orientation_2_mirrors_pixels_horizontally() -> None:
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 0, 255))
    result = apply_exif_orientation(img, 2)
    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((1, 0)) == (255, 0, 0)


# ---------------------------------------------------------------------------
# Orientation 3: 180-degree rotation
# ---------------------------------------------------------------------------

def test_orientation_3_preserves_size() -> None:
    result = apply_exif_orientation(_landscape(), 3)
    assert result.size == (4, 2)


def test_orientation_3_rotates_pixels_180() -> None:
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 0, 255))
    result = apply_exif_orientation(img, 3)
    # After 180° rotation the first pixel becomes the last
    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((1, 0)) == (255, 0, 0)


# ---------------------------------------------------------------------------
# Orientation 4: vertical flip
# ---------------------------------------------------------------------------

def test_orientation_4_preserves_size() -> None:
    result = apply_exif_orientation(_landscape(), 4)
    assert result.size == (4, 2)


def test_orientation_4_mirrors_pixels_vertically() -> None:
    img = Image.new("RGB", (1, 2))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((0, 1), (0, 0, 255))
    result = apply_exif_orientation(img, 4)
    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((0, 1)) == (255, 0, 0)


# ---------------------------------------------------------------------------
# Orientation 5: transpose (diagonal flip; swaps width and height)
# ---------------------------------------------------------------------------

def test_orientation_5_swaps_dimensions() -> None:
    result = apply_exif_orientation(_landscape(4, 2), 5)
    assert result.size == (2, 4)


# ---------------------------------------------------------------------------
# Orientation 6: rotate 90° CW (= ROTATE_270 in PIL conventions)
# The most common portrait-camera case: sensor data is landscape but the
# image should be displayed as portrait.
# ---------------------------------------------------------------------------

def test_orientation_6_swaps_dimensions_to_portrait() -> None:
    # Landscape stored data (4 wide, 2 tall) → portrait output (2 wide, 4 tall)
    result = apply_exif_orientation(_landscape(4, 2), 6)
    assert result.size == (2, 4)


def test_orientation_6_pixel_values_are_correctly_rotated() -> None:
    # 2×1 image: left=red, right=blue
    # Orientation 6 → PIL ROTATE_270 (270° CCW = 90° CW display correction)
    # Pixel transform for ROTATE_270 in W×H→H×W: (x,y)→(H-1-y, x)
    # (0,0)→(0,0): red stays top; (1,0)→(0,1): blue goes bottom
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))  # left = red
    img.putpixel((1, 0), (0, 0, 255))  # right = blue
    result = apply_exif_orientation(img, 6)
    assert result.size == (1, 2)
    assert result.getpixel((0, 0)) == (255, 0, 0)   # top = was left = red
    assert result.getpixel((0, 1)) == (0, 0, 255)   # bottom = was right = blue


# ---------------------------------------------------------------------------
# Orientation 7: transverse (anti-diagonal flip; swaps width and height)
# ---------------------------------------------------------------------------

def test_orientation_7_swaps_dimensions() -> None:
    result = apply_exif_orientation(_landscape(4, 2), 7)
    assert result.size == (2, 4)


# ---------------------------------------------------------------------------
# Orientation 8: rotate 90° CCW (= ROTATE_90 in PIL conventions)
# ---------------------------------------------------------------------------

def test_orientation_8_swaps_dimensions_to_portrait() -> None:
    result = apply_exif_orientation(_landscape(4, 2), 8)
    assert result.size == (2, 4)


def test_orientation_8_pixel_values_are_correctly_rotated() -> None:
    # 2×1 image: left=red, right=blue
    # Orientation 8 → PIL ROTATE_90 (90° CCW)
    # Pixel transform for ROTATE_90 in W×H→H×W: (x,y)→(y, W-1-x)
    # (0,0)→(0,1): red goes bottom; (1,0)→(0,0): blue goes top
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 0, 0))
    img.putpixel((1, 0), (0, 0, 255))
    result = apply_exif_orientation(img, 8)
    assert result.size == (1, 2)
    assert result.getpixel((0, 0)) == (0, 0, 255)   # top = was right = blue
    assert result.getpixel((0, 1)) == (255, 0, 0)   # bottom = was left = red


# ---------------------------------------------------------------------------
# Unknown / out-of-range orientations: no transform
# ---------------------------------------------------------------------------

def test_unknown_orientation_0_returns_original_size() -> None:
    img = _landscape()
    result = apply_exif_orientation(img, 0)
    assert result.size == (4, 2)


def test_unknown_orientation_9_returns_original_size() -> None:
    img = _landscape()
    result = apply_exif_orientation(img, 9)
    assert result.size == (4, 2)
