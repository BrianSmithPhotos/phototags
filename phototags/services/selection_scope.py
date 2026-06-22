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


def pick_ai_source_path(representative_path: Path, target_paths: Sequence[Path]) -> Path:
    """Prefer an ORF in the target set over the JPEG representative for AI analysis.

    Capture-group representative selection prefers a JPEG (see
    `CaptureGroupService._pick_representative`) for thumbnail/preview purposes,
    but an OM System Art Filter Bracket burst shares one unfiltered RAW capture
    across several differently-filtered JPEG renders (monochrome, grainy film,
    etc.). Sending one of those JPEGs to the AI skews the description/keywords
    toward that filter instead of the actual scene, so prefer the ORF's
    embedded preview when one is present in the set.
    """
    orf_candidates = sorted(
        (path for path in target_paths if path.suffix.casefold() == ".orf"),
        key=lambda path: path.name.casefold(),
    )
    return orf_candidates[0] if orf_candidates else representative_path
