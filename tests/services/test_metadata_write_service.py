from pathlib import Path
import subprocess

import pytest

from phototags.services import metadata_write_service as metadata_write_service_module
from phototags.services.metadata_write_service import MetadataWriteError, MetadataWriteService


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_write_description_keywords_returns_normalized_result_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_write_service_module.subprocess, "run", lambda *a, **k: _completed())
    service = MetadataWriteService()

    result = service.write_description_keywords(
        Path("a.jpg"),
        title="My Title",
        description="A scenic overlook",
        keywords_text="beach, sunset, beach",
    )

    assert result.title == "My Title"
    assert result.description == "A scenic overlook"
    assert result.keywords == ["beach", "sunset"]


def test_write_description_keywords_includes_gps_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        captured_command.extend(command)
        return _completed()

    monkeypatch.setattr(metadata_write_service_module.subprocess, "run", fake_run)
    service = MetadataWriteService()

    service.write_description_keywords(
        Path("a.jpg"),
        description="desc",
        keywords_text="k1",
        gps_latitude="45.5",
        gps_longitude="-122.25",
        gps_altitude="-10",
    )

    assert "-GPSLatitude=45.5" in captured_command
    assert "-GPSLatitudeRef=N" in captured_command
    assert "-GPSLongitude=-122.25" in captured_command
    assert "-GPSLongitudeRef=W" in captured_command
    assert "-GPSAltitude=-10.0" in captured_command
    assert "-GPSAltitudeRef=1" in captured_command


def test_write_description_keywords_raises_on_exiftool_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        metadata_write_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="Permission denied"),
    )
    service = MetadataWriteService()

    with pytest.raises(MetadataWriteError, match="Permission denied"):
        service.write_description_keywords(Path("a.jpg"), description="desc", keywords_text="k1")


def test_write_description_keywords_restores_backup_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "a.jpg"
    backup_path = tmp_path / "a.jpg_original"
    image_path.write_bytes(b"corrupted-partial-write")
    backup_path.write_bytes(b"original-bytes")

    monkeypatch.setattr(
        metadata_write_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="exiftool error"),
    )
    service = MetadataWriteService()

    with pytest.raises(MetadataWriteError):
        service.write_description_keywords(image_path, description="desc", keywords_text="k1")

    assert image_path.read_bytes() == b"original-bytes"
    assert not backup_path.exists()


def test_write_description_keywords_rejects_latitude_without_longitude() -> None:
    service = MetadataWriteService()

    with pytest.raises(MetadataWriteError, match="must both be provided"):
        service.write_description_keywords(
            Path("a.jpg"), description="desc", keywords_text="k1", gps_latitude="45.5"
        )


def test_write_description_keywords_rejects_out_of_range_latitude() -> None:
    service = MetadataWriteService()

    with pytest.raises(MetadataWriteError, match="between -90 and 90"):
        service.write_description_keywords(
            Path("a.jpg"),
            description="desc",
            keywords_text="k1",
            gps_latitude="95",
            gps_longitude="0",
        )


def test_write_description_keywords_for_paths_batches_into_one_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return _completed()

    monkeypatch.setattr(metadata_write_service_module.subprocess, "run", fake_run)
    service = MetadataWriteService()

    result = service.write_description_keywords_for_paths(
        [Path("a.jpg"), Path("b.jpg")],
        description="A scenic overlook",
        keywords_text="beach, sunset, beach",
    )

    assert len(calls) == 1
    assert calls[0][-2:] == ["a.jpg", "b.jpg"]
    for image_path in (Path("a.jpg"), Path("b.jpg")):
        written = result[image_path]
        assert written.description == "A scenic overlook"
        assert written.keywords == ["beach", "sunset"]


def test_write_description_keywords_for_paths_falls_back_per_file_on_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _completed(returncode=1, stderr="exiftool group error")
        return _completed()

    monkeypatch.setattr(metadata_write_service_module.subprocess, "run", fake_run)
    service = MetadataWriteService()

    result = service.write_description_keywords_for_paths(
        [Path("a.jpg"), Path("b.jpg")],
        description="desc",
        keywords_text="k1",
    )

    assert call_count == 3  # 1 batch failure + 2 per-file fallback
    assert result[Path("a.jpg")].description == "desc"
    assert result[Path("b.jpg")].description == "desc"


def test_write_description_keywords_for_paths_captures_individual_fallback_failure_as_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        metadata_write_service_module.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=1, stderr="Permission denied"),
    )
    service = MetadataWriteService()

    result = service.write_description_keywords_for_paths(
        [Path("a.jpg")], description="desc", keywords_text="k1"
    )

    outcome = result[Path("a.jpg")]
    assert isinstance(outcome, MetadataWriteError)
    assert "Permission denied" in str(outcome)


def test_write_description_keywords_for_paths_restores_backups_before_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "a.jpg"
    backup_path = tmp_path / "a.jpg_original"
    image_path.write_bytes(b"corrupted-partial-write")
    backup_path.write_bytes(b"original-bytes")

    call_count = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _completed(returncode=1, stderr="exiftool group error")
        # Per-file fallback succeeds; exiftool would have re-created its own
        # backup, which write_description_keywords then cleans up on success.
        return _completed()

    monkeypatch.setattr(metadata_write_service_module.subprocess, "run", fake_run)
    service = MetadataWriteService()

    result = service.write_description_keywords_for_paths(
        [image_path], description="desc", keywords_text="k1"
    )

    assert image_path.read_bytes() == b"original-bytes"
    assert not backup_path.exists()
    assert result[image_path].description == "desc"
