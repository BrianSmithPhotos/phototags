"""Pure helpers for picking the next focused tile after removing tiles from a grid.

Extracted out of `source_panel.py` so the focus-advancement logic behind skip
actions can be unit tested without a `QApplication`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence


def next_selection_after_removal(
    previous_visible_paths: Sequence[Path],
    selected_index: int,
    removed_keys: set[str],
) -> Path | None:
    """Pick the next remaining tile after a removal, advancing forward first.

    Falls back to the nearest remaining tile before the removed selection when
    the removal took out the tail of the list, so focus never jumps back to
    the first tile in the column. Returns `None` if every tile in
    `previous_visible_paths` was removed; the caller picks its own fallback
    (e.g. the first tile in the rebuilt list).
    """
    for path in previous_visible_paths[selected_index + 1 :]:
        if str(path) not in removed_keys:
            return path
    for path in reversed(previous_visible_paths[:selected_index]):
        if str(path) not in removed_keys:
            return path
    return None


def resolve_removal_anchor(
    selected_path: Path,
    previous_visible_paths: Sequence[Path],
    removed_keys: set[str],
    member_to_visible_path: Mapping[Path, Path],
) -> Path | None:
    """Return the tile to keep selected after a removal that took out `selected_path`.

    `selected_path` may be a hidden capture-set member rather than the visible
    tile itself (selected via the preview's variant strip, e.g. clicking the
    ORF thumbnail of a stacked JPG+ORF pair) -- such a path never appears in
    `previous_visible_paths`, so on its own `next_selection_after_removal`
    can't locate it and falls back to the first tile in the whole column.
    `member_to_visible_path` maps a hidden member to its group's visible tile
    so the anchor lookup resolves correctly either way: if that visible tile
    is untouched (only the hidden member was skipped), it stays selected; if
    it was removed too (the whole set was skipped), advancement proceeds from
    its position as normal.

    Returns None when the anchor can't be resolved in `previous_visible_paths`
    at all, or when every remaining tile around it was also removed --
    callers should fall back to their own default (e.g. the first tile in the
    rebuilt list).
    """
    anchor_path = selected_path
    if anchor_path not in previous_visible_paths:
        anchor_path = member_to_visible_path.get(anchor_path, anchor_path)
    if anchor_path not in previous_visible_paths:
        return None
    if str(anchor_path) not in removed_keys:
        return anchor_path
    selected_index = previous_visible_paths.index(anchor_path)
    return next_selection_after_removal(previous_visible_paths, selected_index, removed_keys)
