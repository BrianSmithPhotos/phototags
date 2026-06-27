"""Import-chain smoke tests.

These catch missing or renamed exports that only surface at startup — the kind
of error that won't be caught by service-layer unit tests because those tests
never import the UI modules.
"""

from pathlib import Path


def test_app_entry_point_imports_cleanly() -> None:
    """Regression guard: any export removed from a shared module (e.g. styles.py)
    that another module still imports will surface here, not silently at runtime.
    """
    # This exercises the full chain:
    #   app -> main_window -> source_panel -> styles
    # An ImportError (e.g. SETTINGS_APPLICATION removed from styles but still
    # imported by source_panel) will fail this test immediately.
    import phototags.app  # noqa: F401


def test_thumbnail_tile_calls_no_deleted_methods() -> None:
    """Regression guard: ThumbnailTile._build_ui must not reference _apply_selected_style.

    When that method was renamed to _apply_tile_style the call-site in _build_ui
    was not updated, causing an AttributeError at startup that only surfaced
    when the first tile was constructed (not catchable by the import smoke test).
    """
    source = (
        Path(__file__).parent.parent
        / "phototags"
        / "ui"
        / "widgets"
        / "source_panel.py"
    ).read_text()
    assert "_apply_selected_style" not in source, (
        "source_panel.py still references the deleted _apply_selected_style method; "
        "update all callers to use _apply_tile_style instead"
    )
