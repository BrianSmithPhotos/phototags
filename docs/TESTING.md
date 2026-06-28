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
| `test_exif_service.py` | `exif_service.py`: `map_for_ui` field mapping, GPS DMS/decimal coordinate parsing and range validation, altitude formatting, `ArtFilterEffect`/`PictureMode`/`StackedImage`/`MultipleExposureMode` fallback chain, aperture formatting, `read_full_metadata` against a mocked `subprocess.run` (success, nonzero exit, invalid JSON, empty result) | These mapping/parsing rules feed the metadata panel and the rename/AI flows downstream; a wrong fallback or a coordinate-parsing bug shows the wrong (or no) value in the UI without erroring. |
| `test_ai_suggestion_service.py` | `ai_suggestion_service.py`: JSON extraction from code-fenced/prose-wrapped model responses, keyword normalization/dedup, keyword merging, subject-crop-refinement trigger logic, word-boundary subject matching in descriptions, `suggest_for_image` end-to-end against a fake `AiProvider` (primary success, timeout-then-center-crop-retry, retry-also-empty failure), `_read_previewable_image_bytes` (direct JPEG read vs. mocked-`subprocess` ORF preview extraction, including the no-preview-found failure) | Parses and validates the AI model's response and decides whether to spend a second (refinement) request; a regression here either silently drops valid suggestions, triggers unnecessary refinement passes, or sends the wrong bytes (or none) to the model. |
| `test_metadata_write_service.py` | `metadata_write_service.py`: `write_description_keywords` against a mocked `subprocess.run` (success, exiftool-command GPS argument construction, write failure restoring the `_original` backup file), GPS validation error paths (missing longitude, out-of-range latitude) | Metadata writes are the one operation that mutates files on disk; a wrong command argument or a skipped backup-restore on failure means silent data loss or corruption. |
| `test_elevation_lookup_service.py` | `elevation_lookup_service.py`: USGS EPQS response parsing (direct `value` field, nested `Elevation_Query` shape), no-usable-value/invalid-JSON/network-error failure paths, in-memory cache hit on repeated nearby coordinates and no-cache-on-failure, via a mocked `urllib.request.urlopen` | Feeds GPS altitude on every apply now (timeline altitude is no longer trusted — see `docs/PLAN.md`'s Altitude policy); a parsing regression silently fills no altitude, and a caching regression would either serve stale data or hammer the USGS endpoint on every apply. |
| `test_reverse_geocode_service.py` | `reverse_geocode_service.py`: Nominatim response parsing (city/county/state field fallback chains, `keyword_tokens`/`context_text` formatting), no-address/no-usable-fields/network-error failure paths, via a mocked `urllib.request.urlopen` | Feeds location keywords and AI prompt context; a parsing regression silently drops location data instead of raising. |
| `test_timeline_location_service.py` | `timeline_location_service.py`: coordinate/timestamp parsing (`_parse_lat_lon`, `_parse_exif_capture_timestamp`, `_parse_iso_timestamp`), record-key determinism (`_build_record_key`), `rawSignals`/`semanticSegments` position extraction and dedup (`_position_from_raw_signal`, `_position_from_timeline_path`, `_parse_timeline_positions`), and `suggest_for_capture` end-to-end against a real temp SQLite cache + Timeline JSON fixture (nearest-match-in-window, outside-window, source-type tie-break, missing timeline file) | This is the GPS-suggestion matching logic; a parsing or ordering regression here silently applies the wrong coordinates (or none) to a photo's GPS fields. |
| `test_process_move_service.py` | `process_move_service.py`: `_destination_directory` routing (ORF vs JPEG `jpg` subfolder, case-insensitive suffix match, zero-padded day folder, fallback to file mtime when `captured_at` is unparseable), `_parse_captured_datetime` | Decides where a processed file lands on disk; a routing bug silently files images under the wrong date or skips the `jpg` subfolder split. Deliberately does not cover `process_and_copy`'s actual `shutil.copy`/checksum-verify step — that's integration-test territory (see below). |
| `test_ollama_provider.py` | `ollama_provider.py`: `_extract_message_content` 7-branch fallback chain (message dict/string, response/output/text keys, choices list), empty-response retry budget logic (`done_reason=length` doubling, floor of 1024), timeout detection heuristics (`_is_timeout_network_error`/`_is_timeout_text`), `ensure_vision_capable` capability list parsing and per-model cache, `chat` empty-response retry end-to-end (mocked `_ollama_chat`), and `_ollama_chat` network paths (success, URLError timeout, URLError non-timeout, TimeoutError, invalid JSON, error field) via mocked `urlopen`. | The response-content extraction fallback chain is the most likely source of silent failures (wrong field name → empty → no suggestion); the retry budget doubling on `done_reason=length` is a subtle stateful decision with no visible failure mode short of infinite-budget spirals. |
| `test_openrouter_provider.py` | `openrouter_provider.py`: `_extract_message_content` choices-path extraction, `_error_message_from_body` JSON extraction from HTTP error bodies, timeout detection (same heuristics as Ollama), `_usage_from_response` including `reasoning_tokens` from nested `completion_tokens_details`, `ensure_vision_capable` with `architecture.input_modalities` parsing and caching, and `_openrouter_chat` network paths (missing API key, success, HTTPError with parsed body, URLError timeout, TimeoutError, invalid JSON, error-dict in response, timeout text in error) via mocked `urlopen`. | The `HTTPError` path (unique to OpenRouter among the two providers) carries an error body that must be parsed separately from the response; a regression there silently loses the "Invalid API key" message and surfaces a generic fallback instead. |

237 tests, all currently passing, ~0.5s total.

## Future test batches

Roughly in priority order — highest regression risk and lowest setup cost
first.

### 1. Integration-level tests (separate, slower tier)

Once the above pure-logic coverage exists, the highest-value next step is a
small number of tests that exercise real file I/O end-to-end without Qt:
build a `tmp_path` with a couple of fake JPEG/ORF files (don't need real
image bytes for metadata writes — exiftool will error on garbage image data,
so these specifically need either tiny real sample images checked into
`tests/fixtures/` or to mock at the exiftool boundary, as the existing
`test_metadata_write_service.py`/`test_exif_service.py` do), run
`ProcessMoveService` against them, and assert the files landed at the
expected destination with the expected checksum behavior. Mark these
`@pytest.mark.integration` and keep them out of the default fast run if they
turn out to need a real `exiftool` binary on `PATH`.

### 2. UI/widget tests (last, and only if regressions start happening there)

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
