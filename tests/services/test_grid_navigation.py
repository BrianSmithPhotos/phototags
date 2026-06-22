from pathlib import Path

from phototags.services.grid_navigation import next_selection_after_removal


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
