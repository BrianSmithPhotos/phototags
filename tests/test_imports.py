"""Import-chain smoke tests.

These catch missing or renamed exports that only surface at startup — the kind
of error that won't be caught by service-layer unit tests because those tests
never import the UI modules.
"""


def test_app_entry_point_imports_cleanly() -> None:
    """Regression guard: any export removed from a shared module (e.g. styles.py)
    that another module still imports will surface here, not silently at runtime.
    """
    # This exercises the full chain:
    #   app -> main_window -> source_panel -> styles
    # An ImportError (e.g. SETTINGS_APPLICATION removed from styles but still
    # imported by source_panel) will fail this test immediately.
    import phototags.app  # noqa: F401
