# Test Suite

## Running tests

```
uv run pytest
```

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["."]`, so this
works from the repo root with no extra setup. `pytest` is a `dev` dependency
group (`uv add --dev pytest`), not a runtime dependency.

## Philosophy

This suite only tests **pure logic** — functions that take plain values in
and return plain values out, with no `subprocess` (exiftool), network
(`urllib`), filesystem, Qt, or background-thread dependency. That's a
deliberate scope limit, not an oversight:

- Pure functions are where regressions are cheapest to introduce and easiest
  to verify (see "Why this batch" below) — every bug fixed in this app so far
  has been an off-by-one, a wrong dedupe, or a wrong selection rule, not a
  faulty exiftool invocation.
- They run in milliseconds with no fixtures, no `exiftool` binary required,
  and no `QApplication` event loop.
- Testing the I/O-shelled and Qt-bound code (the other ~half of `services/`,
  all of `workers/`, all of `ui/`) is real, valuable work, but it's a
  different *kind* of test (integration-style, needs mocking or fixtures) —
  see "Future test batches" below for how to approach it without dragging in
  a flaky, slow suite.

### Architectural side effect: logic lives in `services/`, not `ui/`

`CLAUDE.md` already says the UI layer should delegate logic to `services/`
and stay wiring-only. Writing this batch surfaced two places where
`main_window.py` and `source_panel.py` held pure decision logic directly as
private methods, which made it untestable without instantiating a
`QMainWindow`/`QWidget`. Both were extracted into new service modules with no
behavior change, specifically so they're unit-testable:

- `phototags/services/selection_scope.py` — `expand_to_capture_groups()` and
  `pick_ai_source_path()`, used by `main_window.py` for AI/GPS/save/process
  scope resolution.
- `phototags/services/grid_navigation.py` — `next_selection_after_removal()`,
  used by `source_panel.py` to pick focus after a skip.

If you add a new private method to `main_window.py` or a widget that's pure
decision logic (no `self.<qt_widget>` reads/writes, no signal emission), pull
it into a service module the same way and add it to this suite — don't leave
it embedded where it can only be tested by driving the whole UI.

## What's covered (initial batch)

`tests/services/`, one file per service module:

| File | Covers | Why it mattered |
|---|---|---|
| `test_auto_metadata.py` | `auto_metadata.py`: keyword parsing/merging/dedup, `sooc` token rule, art-filter description note | Runs on every save/process; a dedup or string-formatting bug silently corrupts metadata written to disk. |
| `test_capture_group_service.py` | `capture_group_service.py`: same-second bucketing, representative selection (JPEG-over-ORF, filename order), missing-datetime singleton handling, `batch_image_paths` same-stem boundary protection | Capture grouping decides what "Save Capture Set" / "Process Capture Set" / AI-apply actually touch — get this wrong and the wrong files get written or skipped. |
| `test_selection_scope.py` | `selection_scope.py`: expanding a manual multi-selection to full capture-group membership, ORF-preference for AI source image and preview default, multi-selection guard on the preview redirect, range-anchor resolution and contiguous-range selection for shift-click | Direct regression coverage for selection not expanding to full sets, monochrome JPEG sent to AI instead of the ORF, cmd-click multi-select being silently collapsed by the ORF-preview redirect, and shift-click range-select silently collapsing to one tile when the preview redirect left the range anchor on a hidden capture-set member. |
| `test_grid_navigation.py` | `grid_navigation.py`: next-tile-after-skip, including multi-tile skips and the all-removed edge case; `resolve_removal_anchor`'s mapping of a hidden capture-set member back to its visible tile for both partial-set and whole-set removal | Regression coverage for skip focus jumping back to the first tile instead of advancing, including when the active selection was a hidden ORF/JPG variant rather than the visible tile. |
| `test_rename_service.py` | `rename_service.py`: filename pattern assembly, sanitization, collision-suffixing, missing-field fallbacks | Renaming runs on every processed file; a sanitization or collision bug means silent overwrites or invalid filenames on disk. |
| `test_exif_service.py` | `exif_service.py`: `map_for_ui` field mapping, GPS DMS/decimal coordinate parsing and range validation, altitude formatting, `ArtFilterEffect`/`PictureMode`/`StackedImage`/`MultipleExposureMode` fallback chain, aperture formatting | These mapping/parsing rules feed the metadata panel and the rename/AI flows downstream; a wrong fallback or a coordinate-parsing bug shows the wrong (or no) value in the UI without erroring. |
| `test_ai_suggestion_service.py` | `ai_suggestion_service.py`: JSON extraction from code-fenced/prose-wrapped model responses, keyword normalization/dedup, keyword merging, subject-crop-refinement trigger logic, word-boundary subject matching in descriptions | Parses and validates the AI model's response and decides whether to spend a second (refinement) request; a regression here either silently drops valid suggestions or triggers unnecessary refinement passes. |

78 tests, all currently passing, ~0.07s total.

## Future test batches

Roughly in priority order — highest regression risk and lowest setup cost
first.

### 1. `subprocess`/`urllib`-backed services, via mocking the boundary

For `ExifService.read_full_metadata`, `MetadataWriteService`, and
`AiSuggestionService.suggest_for_image`/`_read_previewable_image_bytes`
(exiftool), and `ElevationLookupService`/`ReverseGeocodeService` (HTTP via
`urllib`): don't run the real binary or hit the real network in tests. Use
`monkeypatch.setattr(subprocess, "run", fake_run)` /
`monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)` to return a
canned response, then assert on the parsed result. This tests "does our code
correctly handle exiftool/the API's output shape" without testing exiftool
or the network itself. Add a `tests/services/conftest.py` fixture (e.g.
`fake_exiftool_run`) once two or more test files need the same fake.

### 2. `timeline_location_service.py`

Mostly I/O (SQLite cache, JSON parsing of the Google Timeline export) but the
matching logic is pure once you have parsed positions:
`_parse_lat_lon`, `_build_record_key`, `_parse_exif_capture_timestamp`,
`_parse_iso_timestamp`. Test these directly; for `suggest_for_capture`
end-to-end, build a temp SQLite file with `_ensure_schema` + a few inserted
rows rather than going through real Timeline JSON ingestion.

### 3. `process_move_service.py` destination routing

Routing rules (ORF vs JPEG destination subfolder, date-folder naming) look
pure from the signatures — confirm there's no direct filesystem write inside
the routing decision itself, separate that from the actual `shutil.copy` +
checksum-verify step, and test the routing decision as pure logic. Don't unit
test the actual file copy/checksum verification here — that's an integration
test (see below).

### 4. Integration-level tests (separate, slower tier)

Once the above pure-logic coverage exists, the highest-value next step is a
small number of tests that exercise real file I/O end-to-end without Qt:
build a `tmp_path` with a couple of fake JPEG/ORF files (don't need real
image bytes for metadata writes — exiftool will error on garbage image data,
so these specifically need either tiny real sample images checked into
`tests/fixtures/` or to mock at the exiftool boundary as in #1), run
`ProcessMoveService` against them, and assert the files landed at the
expected destination with the expected checksum behavior. Mark these
`@pytest.mark.integration` and keep them out of the default fast run if they
turn out to need a real `exiftool` binary on `PATH`.

### 5. UI/widget tests (last, and only if regressions start happening there)

Testing `main_window.py` or `source_panel.py` directly requires
`pytest-qt` and a `QApplication` (`QT_QPA_PLATFORM=offscreen` for CI). Given
`main_window.py`'s current size and mixed responsibilities (flagged in
`CLAUDE.md` as a refactor candidate), the better investment is usually to
keep extracting pure decision logic into `services/` (per "Architectural
side effect" above) rather than reaching for `pytest-qt` to test the
megaclass as-is. Reach for `pytest-qt` only for behavior that's inherently
about widget/signal wiring (e.g. "does clicking this button call this
slot with these args") rather than business logic.

## Conventions for new tests

- One test file per source module: `tests/services/test_<module>.py` mirrors
  `phototags/services/<module>.py`.
- Test function names describe the behavior, not the input:
  `test_falls_back_to_previous_tile_when_skipping_the_last_tile`, not
  `test_case_2`.
- Prefer multiple small, single-assertion-focused tests over one large test
  with many asserts — a failure should tell you exactly which behavior broke.
- When a test exists specifically because of a bug fix, say so in the test
  name or a one-line comment (see `test_grid_navigation.py` and
  `test_selection_scope.py`) so future readers know it's a regression guard,
  not just incidental coverage.
- Don't add a fixture or mock until two tests need it — the first test using
  a particular fake `subprocess.run`/`urlopen` response can just inline it.
