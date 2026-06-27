from pathlib import Path

from phototags.services.capture_group_service import CaptureGroup
from phototags.services.selection_scope import (
    expand_to_capture_groups,
    pick_ai_source_path,
    range_between,
    resolve_preview_redirect,
    resolve_range_anchor,
    save_set_scope,
)


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


def test_resolve_preview_redirect_prefers_orf_for_a_fresh_representative_click() -> None:
    representative = Path("P1010001_mono.JPG")
    group = _group("grp-0001", (representative, Path("P1010001.ORF")))
    group_by_path = {p: group for p in group.members}

    redirected = resolve_preview_redirect(representative, group_by_path, has_multi_selection=False)

    assert redirected == Path("P1010001.ORF")


def test_resolve_preview_redirect_leaves_an_explicit_variant_click_untouched() -> None:
    representative = Path("P1010001_mono.JPG")
    orf = Path("P1010001.ORF")
    group = _group("grp-0001", (representative, orf))
    group_by_path = {p: group for p in group.members}

    # The user clicked the ORF directly via the variant strip; it's not the
    # group's representative, so it must not be redirected back to itself
    # or anywhere else.
    redirected = resolve_preview_redirect(orf, group_by_path, has_multi_selection=False)

    assert redirected == orf


def test_resolve_preview_redirect_skips_redirect_during_a_multi_selection() -> None:
    """Regression guard: a cmd/shift-click multi-select must survive a tile click.

    Before this guard, clicking a capture-set representative as part of a
    cmd/shift-click multi-selection still triggered the ORF-preview redirect,
    which re-selected a single path in the UI layer and silently collapsed
    the multi-selection the user had just built.
    """
    representative = Path("P1010001_mono.JPG")
    group = _group("grp-0001", (representative, Path("P1010001.ORF")))
    group_by_path = {p: group for p in group.members}

    redirected = resolve_preview_redirect(representative, group_by_path, has_multi_selection=True)

    assert redirected == representative


def test_resolve_range_anchor_passes_through_a_visible_path_unchanged() -> None:
    visible = Path("P1010001_mono.JPG")

    assert resolve_range_anchor(visible, {}) == visible


def test_resolve_range_anchor_maps_a_hidden_member_to_its_visible_tile() -> None:
    representative = Path("P1010001_mono.JPG")
    orf = Path("P1010001.ORF")
    member_to_visible_path = {orf: representative}

    assert resolve_range_anchor(orf, member_to_visible_path) == representative


def test_range_between_selects_the_contiguous_span_regardless_of_click_order() -> None:
    visible = [Path("a.JPG"), Path("b.JPG"), Path("c.JPG"), Path("d.JPG")]

    forward = range_between(visible[1], visible[3], visible)
    backward = range_between(visible[3], visible[1], visible)

    assert forward == {visible[1], visible[2], visible[3]}
    assert backward == {visible[1], visible[2], visible[3]}


def test_range_between_falls_back_to_single_path_when_anchor_is_not_visible() -> None:
    visible = [Path("a.JPG"), Path("b.JPG")]
    stale_anchor = Path("removed.JPG")

    assert range_between(stale_anchor, visible[1], visible) == {visible[1]}


def test_range_between_falls_back_to_single_path_when_target_is_not_visible() -> None:
    visible = [Path("a.JPG"), Path("b.JPG")]
    hidden_target = Path("hidden.ORF")

    assert range_between(visible[0], hidden_target, visible) == {hidden_target}


def test_shift_click_ranges_correctly_after_a_redirect_left_the_anchor_on_a_hidden_path() -> None:
    """Regression guard: shift-click after clicking an ORF-redirected representative.

    Before `resolve_range_anchor` was applied in `_set_selected_path`, the
    ORF-preview-default redirect (see `resolve_preview_redirect`) left the
    range anchor pointing at the hidden ORF sibling instead of the visible
    JPEG tile. `range_between` then failed its "anchor is visible" check on
    the very next shift-click and silently collapsed to a single-tile
    selection instead of ranging.
    """
    representative = Path("a.JPG")
    orf = Path("a.ORF")
    visible = [representative, Path("b.JPG"), Path("c.JPG")]
    member_to_visible_path = {orf: representative}

    # Simulates `_set_selected_path(orf)` being called by the preview redirect
    # after the user's plain click on `representative`.
    anchor = resolve_range_anchor(orf, member_to_visible_path)

    # The user then shift-clicks the third visible tile.
    selection = range_between(anchor, visible[2], visible)

    assert selection == {visible[0], visible[1], visible[2]}


# --- save_set_scope ---


def test_save_set_scope_single_selection_returns_current_group_only() -> None:
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    set_b = _group("grp-0002", (Path("b1.JPG"), Path("b1.ORF")))
    group_by_path = {p: set_a for p in set_a.members} | {p: set_b for p in set_b.members}

    # Only one capture set selected — scope is that group only, not set_b.
    scope = save_set_scope(Path("a1.JPG"), (Path("a1.JPG"),), group_by_path)

    assert set(scope) == {Path("a1.JPG"), Path("a1.ORF")}
    assert not any(p in scope for p in set_b.members)


def test_save_set_scope_single_path_no_group_returns_only_that_path() -> None:
    standalone = Path("standalone.JPG")

    scope = save_set_scope(standalone, (standalone,), {})

    assert scope == (standalone,)


def test_save_set_scope_multi_selection_expands_all_selected_groups() -> None:
    """Regression guard: Save Capture Set(s) with multiple sets selected must write all of them.

    Before this fix, `_on_save_set_clicked` only looked at the currently
    displayed image's capture group, so images in the other selected sets were
    silently skipped even when the user had cmd-clicked multiple capture sets.
    """
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    set_b = _group("grp-0002", (Path("b1.JPG"), Path("b1.ORF")))
    group_by_path = {p: set_a for p in set_a.members} | {p: set_b for p in set_b.members}

    # Both representatives are in the multi-selection.
    scope = save_set_scope(
        Path("a1.JPG"),
        (Path("a1.JPG"), Path("b1.JPG")),
        group_by_path,
    )

    assert set(scope) == {Path("a1.JPG"), Path("a1.ORF"), Path("b1.JPG"), Path("b1.ORF")}


def test_save_set_scope_variant_strip_must_include_members_of_all_selected_groups() -> None:
    """Regression guard: variant strip was only showing the focused image's own group.

    _refresh_variant_strip previously called group_by_path.get(selected_path) directly
    and passed only that group's members to set_variants — silently hiding the other
    selected group's files even when two capture sets were cmd-clicked. It now
    delegates to save_set_scope so both groups appear. The old call would have
    returned only {a1.JPG, a1.ORF} here; the correct result includes set_b's files too.
    """
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    set_b = _group("grp-0002", (Path("b1.JPG"), Path("b1.ORF")))
    group_by_path = {p: set_a for p in set_a.members} | {p: set_b for p in set_b.members}

    scope = save_set_scope(
        Path("a1.JPG"),
        (Path("a1.JPG"), Path("b1.JPG")),
        group_by_path,
    )

    # Both groups' members must be present — not just a1.JPG + a1.ORF.
    assert set(scope) == {Path("a1.JPG"), Path("a1.ORF"), Path("b1.JPG"), Path("b1.ORF")}


def test_save_set_scope_multi_selection_does_not_include_unselected_group() -> None:
    set_a = _group("grp-0001", (Path("a1.JPG"), Path("a1.ORF")))
    set_b = _group("grp-0002", (Path("b1.JPG"), Path("b1.ORF")))
    set_c = _group("grp-0003", (Path("c1.JPG"), Path("c1.ORF")))
    group_by_path = (
        {p: set_a for p in set_a.members}
        | {p: set_b for p in set_b.members}
        | {p: set_c for p in set_c.members}
    )

    # set_c is visible but not part of the multi-selection.
    scope = save_set_scope(
        Path("a1.JPG"),
        (Path("a1.JPG"), Path("b1.JPG")),
        group_by_path,
    )

    assert not any(p in scope for p in set_c.members)
