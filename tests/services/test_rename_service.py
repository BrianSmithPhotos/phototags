from pathlib import Path

from phototags.services.rename_service import RenameContext, RenameService


def _context(**overrides: object) -> RenameContext:
    defaults: dict = {
        "source_path": Path("P1010042.JPG"),
        "captured_at": "2026:06:21 14:05:30",
        "camera_model": "OM-1",
        "lens_model": "12-40mm F2.8",
        "location": "Yosemite",
        "art_filter_token": "",
    }
    defaults.update(overrides)
    return RenameContext(**defaults)


def test_build_filename_includes_sequence_date_time_camera_lens() -> None:
    service = RenameService()

    name = service.build_filename(_context())

    assert name == "1010042_Yosemite_20260621_1405_OM-1_12-40mm-F2.8.jpg"


def test_build_filename_includes_art_filter_token_when_present() -> None:
    service = RenameService()

    name = service.build_filename(_context(art_filter_token="Grainy Film"))

    assert "_Grainy-Film_" in name


def test_build_filename_omits_location_when_blank() -> None:
    service = RenameService()

    name = service.build_filename(_context(location=""))

    assert "Yosemite" not in name
    assert name.startswith("1010042_20260621_1405_")


def test_build_filename_falls_back_to_unknown_for_missing_camera_and_lens() -> None:
    service = RenameService()

    name = service.build_filename(_context(camera_model="", lens_model=""))

    assert "UnknownCamera" in name
    assert "UnknownLens" in name


def test_build_filename_falls_back_to_unknown_date_time_when_captured_at_unparseable() -> None:
    service = RenameService()

    name = service.build_filename(_context(captured_at="not-a-date"))

    assert "UnknownDate_UnknownTime" in name


def test_build_filename_sanitizes_invalid_filename_characters() -> None:
    service = RenameService()

    name = service.build_filename(_context(location="Yosemite/Half:Dome"))

    assert "/" not in name
    assert ":" not in name


def test_build_filename_preserves_source_extension_case_insensitively() -> None:
    service = RenameService()

    name = service.build_filename(_context(source_path=Path("P1010042.ORF")))

    assert name.endswith(".orf")


def test_ensure_unique_name_returns_candidate_when_no_collision() -> None:
    service = RenameService()

    assert service.ensure_unique_name("photo.jpg", set()) == "photo.jpg"


def test_ensure_unique_name_appends_numeric_suffix_on_collision() -> None:
    service = RenameService()

    result = service.ensure_unique_name("photo.jpg", {"photo.jpg"})

    assert result == "photo_1.jpg"


def test_ensure_unique_name_increments_past_multiple_collisions() -> None:
    service = RenameService()

    result = service.ensure_unique_name("photo.jpg", {"photo.jpg", "photo_1.jpg", "photo_2.jpg"})

    assert result == "photo_3.jpg"
