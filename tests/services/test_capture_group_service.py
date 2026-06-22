from pathlib import Path

from phototags.services.capture_group_service import CaptureGroupService, batch_image_paths


def _meta(captured_at: str) -> dict:
    return {"DateTimeOriginal": captured_at}


def test_build_groups_buckets_by_same_second_timestamp() -> None:
    service = CaptureGroupService()
    paths = [Path("P1010001.JPG"), Path("P1010001.ORF"), Path("P1010002.JPG")]
    metadata = {
        paths[0]: _meta("2026:06:21 10:00:00"),
        paths[1]: _meta("2026:06:21 10:00:00"),
        paths[2]: _meta("2026:06:21 10:05:00"),
    }

    result = service.build_groups_from_metadata(paths, metadata)

    assert len(result.groups) == 2
    burst = next(g for g in result.groups if len(g.members) == 2)
    assert set(burst.members) == {paths[0], paths[1]}
    assert result.by_path[paths[0]] is burst
    assert result.by_path[paths[1]] is burst


def test_representative_prefers_jpeg_over_orf_by_filename() -> None:
    service = CaptureGroupService()
    paths = [Path("P1010001.ORF"), Path("P1010001.JPG")]
    metadata = {p: _meta("2026:06:21 10:00:00") for p in paths}

    result = service.build_groups_from_metadata(paths, metadata)

    assert len(result.groups) == 1
    assert result.groups[0].representative_path == Path("P1010001.JPG")


def test_representative_picks_first_jpeg_by_filename_in_multi_jpeg_burst() -> None:
    """Art Filter Bracket bursts: multiple JPEG renders share one timestamp.

    Filename order is meant to match capture order (plain render first), but
    this is filename-driven, not content-aware -- it can still pick a heavily
    filtered render if that one happens to sort first. AI source selection
    compensates for this separately (see `selection_scope.pick_ai_source_path`).
    """
    service = CaptureGroupService()
    paths = [
        Path("P1010001_3_mono.JPG"),
        Path("P1010001_1_plain.JPG"),
        Path("P1010001.ORF"),
    ]
    metadata = {p: _meta("2026:06:21 10:00:00") for p in paths}

    result = service.build_groups_from_metadata(paths, metadata)

    assert len(result.groups) == 1
    assert result.groups[0].representative_path == Path("P1010001_1_plain.JPG")


def test_no_jpeg_falls_back_to_first_file_by_filename() -> None:
    service = CaptureGroupService()
    paths = [Path("P1010002.ORF"), Path("P1010001.ORF")]
    metadata = {p: _meta("2026:06:21 10:00:00") for p in paths}

    result = service.build_groups_from_metadata(paths, metadata)

    assert result.groups[0].representative_path == Path("P1010001.ORF")


def test_missing_datetime_becomes_its_own_singleton_group() -> None:
    service = CaptureGroupService()
    paths = [Path("P1010001.JPG"), Path("P1010002.JPG")]
    metadata = {paths[0]: _meta("2026:06:21 10:00:00"), paths[1]: {}}

    result = service.build_groups_from_metadata(paths, metadata)

    assert len(result.groups) == 2
    singleton = result.by_path[paths[1]]
    assert singleton.members == (paths[1],)


def test_batch_image_paths_does_not_split_same_stem_pair_across_batches() -> None:
    paths = [Path(f"P{i:04d}.JPG") for i in range(1, 6)] + [Path("P0003.ORF")]

    batches = batch_image_paths(paths, batch_size=3)

    for batch in batches:
        stems = [p.stem for p in batch]
        # If P0003.JPG is in a batch, P0003.ORF must be too (and vice versa).
        if "P0003" in stems:
            assert stems.count("P0003") == 2
