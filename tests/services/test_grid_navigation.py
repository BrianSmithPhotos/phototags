from pathlib import Path

from phototags.services.grid_navigation import (
    next_selection_after_removal,
    resolve_removal_anchor,
)


def test_advances_to_next_remaining_tile_after_skipping_a_middle_tile() -> None:
    paths = [Path(f"{i}.JPG") for i in range(5)]
    removed = {str(paths[2])}

    result = next_selection_after_removal(paths, selected_index=2, removed_keys=removed)

    assert result == paths[3]


def test_falls_back_to_previous_tile_when_skipping_the_last_tile() -> None:
    paths = [Path(f"{i}.JPG") for i in range(5)]
    removed = {str(paths[4])}

    result = next_selection_after_removal(paths, selected_index=4, removed_keys=removed)

    assert result == paths[3]


def test_skips_over_multiple_removed_tiles_in_a_row() -> None:
    """Mirrors mark_skipped_many: a whole capture set removed at once."""
    paths = [Path(f"{i}.JPG") for i in range(5)]
    removed = {str(paths[2]), str(paths[3])}

    result = next_selection_after_removal(paths, selected_index=2, removed_keys=removed)

    assert result == paths[4]


def test_returns_none_when_every_other_tile_was_also_removed() -> None:
    paths = [Path("0.JPG"), Path("1.JPG")]
    removed = {str(paths[0]), str(paths[1])}

    result = next_selection_after_removal(paths, selected_index=0, removed_keys=removed)

    assert result is None


def test_single_remaining_tile_after_removal_is_returned() -> None:
    paths = [Path("0.JPG"), Path("1.JPG")]
    removed = {str(paths[1])}

    result = next_selection_after_removal(paths, selected_index=1, removed_keys=removed)

    assert result == paths[0]


def test_anchor_stays_on_visible_tile_when_only_a_hidden_member_is_skipped() -> None:
    """Skipping the ORF variant of a stacked JPG+ORF set must not move focus off the JPG tile."""
    visible = [Path("0.JPG"), Path("set1.JPG"), Path("2.JPG")]
    orf_member = Path("set1.ORF")
    removed = {str(orf_member)}

    result = resolve_removal_anchor(
        selected_path=orf_member,
        previous_visible_paths=visible,
        removed_keys=removed,
        member_to_visible_path={orf_member: visible[1]},
    )

    assert result == visible[1]


def test_anchor_advances_past_set_when_whole_set_is_skipped_via_hidden_member_selection() -> None:
    """Regression for bug #3: skipping a whole set while its ORF variant was previewed must
    advance to the next set, not fall back to the first tile in the column."""
    visible = [Path("0.JPG"), Path("set1.JPG"), Path("2.JPG")]
    orf_member = Path("set1.ORF")
    removed = {str(visible[1]), str(orf_member)}

    result = resolve_removal_anchor(
        selected_path=orf_member,
        previous_visible_paths=visible,
        removed_keys=removed,
        member_to_visible_path={orf_member: visible[1]},
    )

    assert result == visible[2]


def test_anchor_returns_none_when_selection_has_no_visible_mapping() -> None:
    result = resolve_removal_anchor(
        selected_path=Path("orphan.ORF"),
        previous_visible_paths=[Path("0.JPG")],
        removed_keys={str(Path("orphan.ORF"))},
        member_to_visible_path={},
    )

    assert result is None
