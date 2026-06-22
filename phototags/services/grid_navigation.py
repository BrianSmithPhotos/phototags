"""Pure helpers for picking the next focused tile after removing tiles from a grid.

Extracted out of `source_panel.py` so the focus-advancement logic behind skip
actions can be unit tested without a `QApplication`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


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
