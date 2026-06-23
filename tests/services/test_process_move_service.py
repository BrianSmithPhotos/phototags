from pathlib import Path

from phototags.services.process_move_service import ProcessMoveService


def test_parse_captured_datetime_with_explicit_offset() -> None:
    service = ProcessMoveService()

    parsed = service._parse_captured_datetime("2026:06:21 10:00:00+00:00")

    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 6, 21)


def test_parse_captured_datetime_without_offset() -> None:
    service = ProcessMoveService()

    parsed = service._parse_captured_datetime("2026:06:21 10:00:00")

    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 6, 21)


def test_parse_captured_datetime_returns_none_for_blank_or_invalid() -> None:
    service = ProcessMoveService()

    assert service._parse_captured_datetime("") is None
    assert service._parse_captured_datetime("not a timestamp") is None


def test_destination_directory_routes_jpeg_into_jpg_subfolder() -> None:
    service = ProcessMoveService()

    destination = service._destination_directory(
        destination_root=Path("/library"),
        captured_at="2026:06:21 10:00:00",
        source_path=Path("P1010001.JPG"),
    )

    assert destination == Path("/library/6 June/21/jpg")


def test_destination_directory_routes_orf_without_jpg_subfolder() -> None:
    service = ProcessMoveService()

    destination = service._destination_directory(
        destination_root=Path("/library"),
        captured_at="2026:06:21 10:00:00",
        source_path=Path("P1010001.ORF"),
    )

    assert destination == Path("/library/6 June/21")


def test_destination_directory_jpeg_suffix_match_is_case_insensitive() -> None:
    service = ProcessMoveService()

    lower = service._destination_directory(
        destination_root=Path("/library"), captured_at="2026:06:21 10:00:00", source_path=Path("a.jpeg")
    )
    upper = service._destination_directory(
        destination_root=Path("/library"), captured_at="2026:06:21 10:00:00", source_path=Path("a.JPEG")
    )

    assert lower == upper == Path("/library/6 June/21/jpg")


def test_destination_directory_pads_day_folder_to_two_digits() -> None:
    service = ProcessMoveService()

    destination = service._destination_directory(
        destination_root=Path("/library"),
        captured_at="2026:01:05 10:00:00",
        source_path=Path("a.ORF"),
    )

    assert destination == Path("/library/1 January/05")


def test_destination_directory_falls_back_to_file_mtime_when_captured_at_unparseable(
    tmp_path: Path,
) -> None:
    service = ProcessMoveService()
    source_path = tmp_path / "a.orf"
    source_path.write_bytes(b"data")

    destination = service._destination_directory(
        destination_root=Path("/library"),
        captured_at="not a timestamp",
        source_path=source_path,
    )

    # No exception, and it still produced a "<month> <Name>/<day>" destination
    # using the real file's mtime instead of erroring or defaulting to nothing.
    assert destination.parent.parent == Path("/library")
