## Packaging: Dock-Launchable `.app` Bundle

This covers building `MacPhotoMaster.app` via `py2app` so the app can be dragged to the Dock and
launched with one click, instead of running `uv run python main.py` from a terminal.

### Files involved

- `setup.py` — `py2app` build script (bundle name/identifier, icon wiring).
- `scripts/make_icns.sh` — converts a single 1024x1024 PNG into the multi-resolution `.icns` file
  macOS app icons require.
- `resources/AppIcon.icns` — the generated icon, built from `icons/housefinch.png`. Regenerate it
  with `scripts/make_icns.sh` if the source PNG changes; see "Changing the icon" below.

### Build

Two `py2app` modes, both invoked from the repo root:

```bash
# Alias build (recommended) — fast, symlinks into this repo's .venv.
uv run python setup.py py2app -A

# Standalone build — bundles a full frozen Python. Currently broken; see
# "Known limitation" below.
uv run python setup.py py2app
```

Either mode writes `dist/MacPhotoMaster.app`. Drag it onto the Dock to pin it; clicking it launches
the app same as `uv run python main.py`.

The alias build only works as long as this repo and its `.venv` stay where they are — it's a set of
symlinks back into the checkout, not a standalone copy. That's fine for pinning to your own Dock on
this Mac, but the bundle isn't portable to another machine or another checkout location.

`build/` and `dist/` are already gitignored; rerun the build command above any time (e.g. after
`uv sync` picks up new dependencies) — there's nothing to commit from a build.

### Known limitation: standalone build fails

The plain `py2app` (non-alias) build fails with:

```
AttributeError: module 'zlib' has no attribute '__file__'
```

`uv`'s managed CPython (from `python-build-standalone`) links `zlib` statically into the interpreter
binary rather than building it as a separate loadable extension, so it has no `__file__` for py2app
to copy into the frozen bundle. `py2app`'s standalone mode assumes every extension module is a
copyable file — an assumption this Python build breaks. Building against a different CPython
distribution (e.g. python.org's official installer, which builds zlib as a real framework dylib)
would sidestep this, but that means building outside `uv`'s toolchain, which isn't worth it just to
avoid the alias build's one caveat above.

### `install_requires` workaround

`setup.py` also works around a separate, unrelated `py2app`/`setuptools` conflict: setuptools reads
`pyproject.toml`'s `[project.dependencies]` and auto-populates `install_requires` on the
`Distribution` object, even for a plain `python setup.py py2app` invocation. `py2app` refuses to
build at all if `install_requires` is set (a frozen app bundle has no use for pip-style deps). The
`Py2AppIgnoringDependencies` command subclass in `setup.py` clears it in `finalize_options()` before
`py2app`'s own check runs. This is unrelated to the `zlib` limitation above and affects both build
modes equally — without it, neither mode would get past `running py2app`.

### Changing the icon

The icon source must be a single square PNG, at least 1024x1024 (that's the largest size macOS
embeds — `icon_512x512@2x`). Regenerate `resources/AppIcon.icns` from a new source image with:

```bash
./scripts/make_icns.sh path/to/new-icon-1024.png
```

Then rebuild the app (`uv run python setup.py py2app -A`) to pick up the new icon.
