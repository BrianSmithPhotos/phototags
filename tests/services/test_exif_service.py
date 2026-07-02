from pathlib import Path
import subprocess

import pytest

from phototags.services import exif_service as exif_service_module
from phototags.services.exif_service import ExifService, ExifToolReadError


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_map_for_ui_prefers_first_available_key_per_field() -> None:
    service = ExifService()
    metadata = {
        "XMP:Title": "Sunset",
        "IPTC:ObjectName": "Should not win",
        "IFD0:Make": "OM Digital Solutions",
        "IFD0:Model": "OM-1",
        "Composite:Aperture": "4",
        "Composite:ShutterSpeed": "1/500",
        "ExifIFD:FocalLength": "150 mm",
        "ExifIFD:DateTimeOriginal": "2026:06:21 10:00:00",
        "ExifIFD:ISO": "200",
    }

    mapped = service.map_for_ui(metadata)

    assert mapped.title == "Sunset"
    assert mapped.camera == "OM Digital Solutions OM-1"
    assert mapped.camera_model == "OM-1"
    assert mapped.aperture == "f/4"
    assert mapped.shutter_speed == "1/500"
    assert mapped.focal_length == "150 mm"
    assert mapped.iso == "200"
    assert mapped.captured_at == "2026:06:21 10:00:00"
    assert mapped.captured_at_display == "Sun, Jun 21, 2026 10:00:00"


def test_map_for_ui_returns_empty_strings_when_nothing_present() -> None:
    service = ExifService()

    mapped = service.map_for_ui({})

    assert mapped.title == ""
    assert mapped.camera == ""
    assert mapped.gps_latitude == ""
    assert mapped.art_filter_token == ""


def test_keywords_text_joins_list_values_with_comma() -> None:
    service = ExifService()
    metadata = {"XMP:Subject": ["beach", "sunset", "family"]}

    mapped = service.map_for_ui(metadata)

    assert mapped.keywords == "beach, sunset, family"


def test_keywords_text_falls_back_through_candidates_when_list_is_empty() -> None:
    service = ExifService()
    metadata = {"XMP:Subject": [], "IPTC:Keywords": "beach, sunset"}

    mapped = service.map_for_ui(metadata)

    assert mapped.keywords == "beach, sunset"


def test_gps_coordinate_parses_plain_decimal_value() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "45.5"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_latitude == "45.5000000"


def test_gps_coordinate_parses_dms_text_with_hemisphere_suffix() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "45 deg 30' 0.00\" S"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_latitude == "-45.5000000"


def test_gps_coordinate_uses_ref_key_when_dms_text_has_no_hemisphere() -> None:
    service = ExifService()
    metadata = {
        "Composite:GPSLongitude": "122 deg 15' 0.00\"",
        "GPS:GPSLongitudeRef": "W",
    }

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_longitude == "-122.2500000"


def test_gps_coordinate_rejects_out_of_range_latitude() -> None:
    service = ExifService()
    metadata = {"Composite:GPSLatitude": "95 deg 0' 0.00\" N"}

    mapped = service.map_for_ui(metadata)

    # 95 is out of latitude range, so parsing fails and the raw text passes through.
    assert mapped.gps_latitude == "95 deg 0' 0.00\" N"


def test_gps_altitude_formats_plain_numeric_value() -> None:
    service = ExifService()
    metadata = {"Composite:GPSAltitude": "123.456"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_altitude == "123.46"


def test_gps_altitude_extracts_number_from_unit_suffixed_text() -> None:
    service = ExifService()
    metadata = {"Composite:GPSAltitude": "123.4 m Above Sea Level"}

    mapped = service.map_for_ui(metadata)

    assert mapped.gps_altitude == "123.4"


def test_art_filter_token_prefers_active_art_filter_effect() -> None:
    service = ExifService()
    metadata = {"Olympus:ArtFilterEffect": "Dramatic Tone; Yes; 0"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Dramatic Tone"


def test_art_filter_token_ignores_off_art_filter_effect() -> None:
    service = ExifService()
    metadata = {"Olympus:ArtFilterEffect": "Off"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == ""


def test_art_filter_token_falls_back_to_picture_mode_profile() -> None:
    service = ExifService()
    metadata = {"Olympus:PictureMode": "Color Profile 1"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Color Profile 1"


def test_art_filter_token_falls_back_to_stacked_image_state() -> None:
    service = ExifService()
    metadata = {"Olympus:StackedImage": "Live Composite"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "Live Composite"


def test_art_filter_token_falls_back_to_multiple_exposure_mode() -> None:
    service = ExifService()
    metadata = {"Olympus:MultipleExposureMode": "On (2 Shots)"}

    mapped = service.map_for_ui(metadata)

    assert mapped.art_filter_token == "MultipleExposure"


def test_format_aperture_handles_integer_and_fractional_values() -> None:
    service = ExifService()

    assert service._format_aperture("4") == "f/4"
    assert service._format_aperture("2.8") == "f/2.8"
    assert service._format_aperture("f/5.6") == "f/5.6"
    assert service._format_aperture("") == ""


def test_read_full_metadata_returns_first_object_from_exiftool_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        exif_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(stdout='[{"SourceFile": "a.jpg", "EXIF:Make": "OM Digital"}]'),
    )
    service = ExifService()

    metadata = service.read_full_metadata(Path("a.jpg"))

    assert metadata == {"SourceFile": "a.jpg", "EXIF:Make": "OM Digital"}


def test_read_full_metadata_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        exif_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="File not found"),
    )
    service = ExifService()

    with pytest.raises(ExifToolReadError, match="File not found"):
        service.read_full_metadata(Path("missing.jpg"))


def test_read_full_metadata_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        exif_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(stdout="not json"),
    )
    service = ExifService()

    with pytest.raises(ExifToolReadError, match="Invalid JSON"):
        service.read_full_metadata(Path("a.jpg"))


def test_read_full_metadata_raises_when_exiftool_returns_no_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        exif_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(stdout="[]"),
    )
    service = ExifService()

    with pytest.raises(ExifToolReadError, match="No metadata returned"):
        service.read_full_metadata(Path("a.jpg"))


def test_read_full_metadata_for_paths_batches_into_one_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return _completed(
            stdout=(
                '[{"SourceFile": "a.jpg", "EXIF:Make": "OM"}, '
                '{"SourceFile": "b.jpg", "EXIF:Make": "Canon"}]'
            )
        )

    monkeypatch.setattr(exif_service_module.subprocess, "run", fake_run)
    service = ExifService()

    result = service.read_full_metadata_for_paths([Path("a.jpg"), Path("b.jpg")])

    assert len(calls) == 1
    assert result[Path("a.jpg")] == {"SourceFile": "a.jpg", "EXIF:Make": "OM"}
    assert result[Path("b.jpg")] == {"SourceFile": "b.jpg", "EXIF:Make": "Canon"}


def test_read_full_metadata_for_paths_falls_back_per_file_when_missing_from_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Batch call: exiftool only managed to read one of the two files.
            return _completed(stdout='[{"SourceFile": "a.jpg", "EXIF:Make": "OM"}]')
        path = command[-1]
        return _completed(stdout=f'[{{"SourceFile": "{path}", "EXIF:Make": "Fallback"}}]')

    monkeypatch.setattr(exif_service_module.subprocess, "run", fake_run)
    service = ExifService()

    result = service.read_full_metadata_for_paths([Path("a.jpg"), Path("b.jpg")])

    assert call_count == 2
    assert result[Path("a.jpg")] == {"SourceFile": "a.jpg", "EXIF:Make": "OM"}
    assert result[Path("b.jpg")] == {"SourceFile": "b.jpg", "EXIF:Make": "Fallback"}


def test_read_full_metadata_for_paths_falls_back_on_batch_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise subprocess.TimeoutExpired(cmd=command, timeout=1)
        path = command[-1]
        return _completed(stdout=f'[{{"SourceFile": "{path}", "EXIF:Make": "Retry"}}]')

    monkeypatch.setattr(exif_service_module.subprocess, "run", fake_run)
    service = ExifService()

    result = service.read_full_metadata_for_paths([Path("a.jpg"), Path("b.jpg")])

    assert call_count == 3  # 1 batch timeout + 2 per-file fallback
    assert result[Path("a.jpg")] == {"SourceFile": "a.jpg", "EXIF:Make": "Retry"}
    assert result[Path("b.jpg")] == {"SourceFile": "b.jpg", "EXIF:Make": "Retry"}


def test_read_full_metadata_for_paths_captures_individual_failure_as_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        exif_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="File not found"),
    )
    service = ExifService()

    result = service.read_full_metadata_for_paths([Path("missing.jpg")])

    outcome = result[Path("missing.jpg")]
    assert isinstance(outcome, ExifToolReadError)
    assert "File not found" in str(outcome)


def test_read_full_metadata_for_paths_chunks_large_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        requested = command[len(exif_service_module.EXIFTOOL_READ_COMMAND) :]
        entries = ", ".join(f'{{"SourceFile": "{path}"}}' for path in requested)
        return _completed(stdout=f"[{entries}]")

    monkeypatch.setattr(exif_service_module.subprocess, "run", fake_run)
    service = ExifService()
    paths = [Path(f"{i}.jpg") for i in range(exif_service_module.EXIFTOOL_READ_CHUNK_SIZE + 5)]

    result = service.read_full_metadata_for_paths(paths)

    assert len(calls) == 2
    assert len(result) == len(paths)
