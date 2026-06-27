"""Pure helpers for resolving multi-file action scope from a manual selection.

Extracted out of `main_window.py` so the scope-resolution logic behind
AI/GPS/save/process actions can be unit tested without a `QApplication`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from phototags.services.capture_group_service import CaptureGroup


def expand_to_capture_groups(
    paths: Sequence[Path], group_by_path: Mapping[Path, CaptureGroup]
) -> tuple[Path, ...]:
    """Expand each path to its full capture-group membership, deduped, order preserved.

    A manual multi-selection in stacked view selects one representative thumbnail
    per capture set; without this expansion, an action would only touch those
    representative files and silently skip the other members (e.g. the ORF) of
    each selected set. A path with no capture group (a true standalone
    selection, e.g. a same-spot burst the timestamp grouping didn't merge)
    expands to just itself.
    """
    expanded: list[Path] = []
    for path in paths:
        group = group_by_path.get(path)
        expanded.extend(group.members if group is not None else (path,))
    return tuple(dict.fromkeys(expanded))


def save_set_scope(
    selected_path: Path,
    multi_selected_paths: Sequence[Path],
    group_by_path: Mapping[Path, CaptureGroup],
) -> tuple[Path, ...]:
    """Paths included in a 'Save Capture Set(s)' action.

    When the selected path is part of an active manual multi-selection (more
    than one path), all selected paths are expanded to their full
    capture-group membership.  Otherwise only the selected path's own capture
    group is returned (or just the path itself when it has no group).

    This same scope is used both to determine which paths the save job writes,
    and to decide which drafts to propagate the edited description/keywords to
    in `_sync_current_draft`.
    """
    if len(multi_selected_paths) > 1 and selected_path in multi_selected_paths:
        return expand_to_capture_groups(multi_selected_paths, group_by_path)
    group = group_by_path.get(selected_path)
    return tuple(group.members) if group is not None else (selected_path,)


def pick_ai_source_path(representative_path: Path, target_paths: Sequence[Path]) -> Path:
    """Prefer an ORF in the target set over the JPEG representative.

    Capture-group representative selection prefers a JPEG (see
    `CaptureGroupService._pick_representative`) for thumbnail/listing
    purposes, but an OM System Art Filter Bracket burst shares one unfiltered
    RAW capture across several differently-filtered JPEG renders (monochrome,
    grainy film, etc.). Sending one of those JPEGs to the AI skews the
    description/keywords toward that filter instead of the actual scene, so
    prefer the ORF's embedded preview when one is present in the set. Also
    used by `resolve_preview_redirect` to apply the same preference when a
    freshly selected capture set first opens in the preview pane.
    """
    orf_candidates = sorted(
        (path for path in target_paths if path.suffix.casefold() == ".orf"),
        key=lambda path: path.name.casefold(),
    )
    return orf_candidates[0] if orf_candidates else representative_path


def resolve_preview_redirect(
    image_path: Path,
    group_by_path: Mapping[Path, CaptureGroup],
    has_multi_selection: bool,
) -> Path:
    """Return the path the preview pane should actually show for a fresh tile click.

    Mirrors `pick_ai_source_path`'s ORF preference so a freshly-selected capture
    set defaults its preview to the ORF member instead of the (possibly
    filtered) JPEG representative. Returns `image_path` unchanged whenever
    `has_multi_selection` is True: redirecting the preview path requires
    re-selecting a single tile in the UI layer, which would silently collapse
    an active cmd/shift-click multi-selection back down to one file -- a
    regression introduced when the ORF-default redirect was added without
    this guard.
    """
    if has_multi_selection:
        return image_path
    group = group_by_path.get(image_path)
    if group is None or group.representative_path != image_path:
        return image_path
    return pick_ai_source_path(image_path, group.members)


def resolve_range_anchor(image_path: Path, member_to_visible_path: Mapping[Path, Path]) -> Path:
    """Map a programmatically-set selection path onto a visible grid tile.

    `image_path` set as the shift-click range anchor must be a path that
    appears in the grid's visible tiles, since `range_between` looks the
    anchor up by position in that list. A path can be hidden when it's a
    non-representative capture-set member (e.g. the ORF-preview-default
    redirect in `main_window._on_photo_selected` re-targeting a JPEG
    representative to its hidden ORF sibling); without this mapping, the
    anchor silently fails to resolve and the next shift-click collapses to a
    single-tile selection instead of ranging.
    """
    return member_to_visible_path.get(image_path, image_path)


def range_between(
    anchor_path: Path, image_path: Path, visible_paths: Sequence[Path]
) -> set[Path]:
    """Return the contiguous set of visible paths between anchor and image_path.

    Falls back to selecting just `image_path` when either endpoint isn't in
    `visible_paths` (e.g. a stale anchor from a folder/grouping change),
    matching a plain click rather than silently selecting nothing.
    """
    if anchor_path not in visible_paths or image_path not in visible_paths:
        return {image_path}
    start = visible_paths.index(anchor_path)
    end = visible_paths.index(image_path)
    low, high = min(start, end), max(start, end)
    return set(visible_paths[low : high + 1])
