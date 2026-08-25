## Packaging: Dock-Launchable `.app` Bundle

This covers building `MacPhotoMaster.app` via `py2app` so the app can be dragged to the Dock and
launched with one click, instead of running `uv run python main.py` from a terminal.

### Files involved

- `setup.py` — `py2app` build script (bundle name/identifier, icon wiring).
- `Tools/IconGen/` — a small Swift package that *draws* the icon. See "The icon" below.
- `scripts/make_icns.sh` — converts a single 1024x1024 PNG into the multi-resolution `.icns` file
  macOS app icons require.
- `icons/AppIcon-1024.png` — the drawn icon, and the input to `make_icns.sh`.
- `resources/AppIcon.icns` — what the bundle uses, sipped down from that PNG.
- `resources/AppIcon.png` — the same image, handed to Qt by `phototags/app.py` so a plain
  `uv run python main.py` gets a Dock icon too (no bundle means no `Info.plist` to name an
  `.icns`).

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

### The icon

The icon is drawn in code, not stored as a PNG nobody can adjust. `Tools/IconGen` is a Swift
package that renders it; the tile it draws on — the teal, the continuous-corner squircle, the light
from above, the shadow, the 824/1024 grid every Dock icon sits on — comes from
[IconForge](https://github.com/BrianSmithPhotos/IconForge), which the sibling
MacPhotoMaster-Swift app draws its icon with too. Only the mark is ours: the iris is the same one
that app uses, and the Py set into the cut is what says this is the Python one.

That is why there is a Swift toolchain in a Python repo, and it is the point of it — the shared
tile is what makes the two apps read as a family, and a redrawn-in-Pillow copy would drift.
Nothing at runtime touches it; it is a generator run by hand, and its output is committed.

To change the icon, edit `Tools/IconGen/Sources/IconGen/PyMark.swift` (or `Aperture.swift`), then:

```bash
# Draw it: writes icons/AppIcon-1024.png and resources/AppIcon.png
swift run --package-path Tools/IconGen IconGen .

# Sip that down into the multi-resolution .icns the bundle needs
./scripts/make_icns.sh icons/AppIcon-1024.png

# Pick it up
uv run python setup.py py2app -A
```

Judge the result at the sizes it will actually be seen at, not just at 1024:

```bash
swift run --package-path Tools/IconGen IconGen . --sheet   # icons/contact-sheet.png
```

which renders the icon with 64, 32 and 16 under it. The sheet is gitignored — it is a thing to
look at, not an input. More on the mark itself, including which bits of it are load-bearing, in
`Tools/IconGen/README.md`.

macOS caches Dock icons aggressively; if a rebuilt bundle still shows the old one, move it to the
Trash and rebuild, or log out and back in.

The `make_icns.sh` step works with any square PNG of at least 1024x1024 (that's the largest size
macOS embeds — `icon_512x512@2x`), so it is still the way in if you ever want to use an image
rather than a drawn icon.
