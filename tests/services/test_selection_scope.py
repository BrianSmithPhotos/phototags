from pathlib import Path

from phototags.services.capture_group_service import CaptureGroup
from phototags.services.selection_scope import expand_to_capture_groups, pick_ai_source_path


def _group(group_id: str, members: tuple[Path, ...]) -> CaptureGroup:
    return CaptureGroup(
        group_id=group_id,
        representative_path=members[0],
        members=members,
        strategy="datetime-second",
        key_text="dt=2026:06:21 10:00:00",
    )


def test_expand_to_capture_groups_pulls_in_unselected_siblings() -> None:
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    set_b = _group("grp-0002", (Path("b1.JPG"), Path("b1.ORF"), Path("b2.JPG")))
    group_by_path = {p: set_a for p in set_a.members} | {p: set_b for p in set_b.members}

    # Selecting just the two stacked-view representatives...
    expanded = expand_to_capture_groups((Path("a1.JPG"), Path("b1.JPG")), group_by_path)

    # ...should pull in every member of both sets.
    assert set(expanded) == {
        Path("a1.JPG"),
        Path("a1.ORF"),
        Path("b1.JPG"),
        Path("b1.ORF"),
        Path("b2.JPG"),
    }


def test_expand_to_capture_groups_path_with_no_group_expands_to_itself() -> None:
    standalone = Path("standalone.JPG")

    expanded = expand_to_capture_groups((standalone,), {})

    assert expanded == (standalone,)


def test_expand_to_capture_groups_dedupes_and_preserves_first_seen_order() -> None:
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    group_by_path = {p: set_a for p in set_a.members}

    expanded = expand_to_capture_groups((Path("a1.JPG"), Path("a1.ORF")), group_by_path)

    assert expanded == (Path("a1.JPG"), Path("a1.ORF"))


def test_pick_ai_source_path_prefers_orf_over_jpeg_representative() -> None:
    representative = Path("P1010001_mono.JPG")
    targets = (representative, Path("P1010001_plain.JPG"), Path("P1010001.ORF"))

    assert pick_ai_source_path(representative, targets) == Path("P1010001.ORF")


def test_pick_ai_source_path_falls_back_to_representative_when_no_orf() -> None:
    representative = Path("P1010001_mono.JPG")
    targets = (representative, Path("P1010001_plain.JPG"))

    assert pick_ai_source_path(representative, targets) == representative


def test_pick_ai_source_path_picks_lowest_filename_when_multiple_orfs() -> None:
    representative = Path("rep.JPG")
    targets = (representative, Path("b.ORF"), Path("a.ORF"))

    assert pick_ai_source_path(representative, targets) == Path("a.ORF")
