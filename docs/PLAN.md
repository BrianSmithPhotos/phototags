## MacPhotoMaster Plan (Current)

Last updated: 2026-06-30

This document is the active implementation snapshot + next-step checklist.

See `docs/TESTING.md` for the automated test suite (`uv run pytest`) and what's covered vs. open.

## 1. Completed Core Scope

### Part 1 - App shell and architecture

- [x] Confirmed scope from `AGENTS.md` (macOS + `uv` + PySide6 + background workers).
- [x] Built single-window 3-panel layout.
- [x] Split app into UI widgets, services, and workers.

### Part 2 - Source browse + preview

- [x] Source browser with folder tree and thumbnail grid.
- [x] Supported file types in UI listing: `.jpg`, `.jpeg`, `.orf`.
- [x] Background image loading for thumbnails and full preview.
- [x] ORF preview fallback via `exiftool -b -PreviewImage` when needed.
- [x] Preview zoom + fit behavior; zoom keeps the same image-space point centered in
  the viewport across zoom level changes (no drift toward a corner).
- [x] Skip (single image, capture set, or auto-skip after successful process) removes
  just the affected tile(s) from the grid in place; it no longer reloads the whole
  folder or re-decodes thumbnails that are already loaded.
- [x] Skipping the selected tile advances focus to the next remaining tile in
  column order (falling back to the previous remaining tile if the skip removed
  the tail of the list) instead of always jumping back to the first tile
  (`grid_navigation.next_selection_after_removal`). Extended to anchor correctly
  when the active selection is a hidden capture-set member rather than the
  visible tile itself (`grid_navigation.resolve_removal_anchor`) — see below.
- [x] Source panel directory tree is sized to a small default (no large wasted blank
  area between the tree and the thumbnail grid); thumbnail grid gets remaining
  vertical space via splitter stretch factors.
- [x] "Stacked?" checkbox (default on) in the source panel: when a folder's capture
  groups are known, shows only one representative tile per capture set in a single
  column instead of every member in the 2-column grid. The full set remains
  reachable via the preview panel's existing variant strip. If a visible
  representative is skipped individually, a remaining sibling is promoted rather
  than the whole set disappearing. Toggling re-flows already-loaded tiles only; no
  re-decoding.
- [x] Source panel width is capped to fit exactly the visible column count (one
  column when stacked, two when not), computed from tile width + scrollbar extent
  + panel margins. `QSplitter` gives any extra dragged-in width to the middle
  preview panel instead of widening the source column past that cap. The cap
  recomputes on "Stacked?" toggle. Also fixes a flash of the 2-column grid before
  capture-set grouping resolves, since column count now depends only on the
  "Stacked?" state, not on whether grouping data has arrived yet.
- [x] Default source folder at startup (`phototags/app.py`,
  `detect_default_source_dir`): scans the mounted OM System SD card's
  `DCIM/` for the lowest-numbered `<NNN>OMSYS` folder (e.g. `105OMSYS`) —
  cameras roll over to a new one every 10,000 images, and on the rare
  occasion two coexist the lower number is the one still being imported
  from. Falls back to `/Volumes` (browsable, not auto-populated) when no SD
  card with that structure is mounted.
- [x] Fixed: app window never appeared on large folders (~1800 photos). Root
  cause in `source_panel.py`'s `_relayout_grid` — every `ThumbnailTile` is
  constructed with no parent, and the method called `setVisible(True)` on
  tiles before `addWidget` reparented them into the grid, so Qt promoted each
  one to its own top-level native `NSWindow`; AppKit's window-ordering insert
  cost scales with existing window count, making the whole pass O(n^2) and
  the window never reached `show()`. Fixed by reordering so `addWidget` runs
  before `setVisible`. Two related smaller fixes landed alongside it: the
  "Stacked?" grid no longer forces a single, all-photos column before capture
  grouping has resolved anything to hide (it now matches the un-stacked
  2-column grid until there's actually something to collapse), and
  `main_window._on_groups_loaded` throttles the per-batch grid re-flow
  (`GROUP_UI_APPLY_MIN_INTERVAL_S`) so a folder with dozens of EXIF batches
  doesn't re-layout every tile on every batch — the final batch always
  applies regardless, so the end result is unaffected. Confirmed via a
  `sample`-based stack trace on the real (non-offscreen) app pointing
  straight at `NSWindow initWithContentRect:`/window-ordering calls; verified
  fix by timing `show()` against a real 1778-file SD card folder (window now
  appears in ~3s, vs. never appearing after 30+ seconds before).
- [x] Preview default for a freshly selected capture set prefers its ORF member
  over the JPEG representative (`main_window._default_preview_path`, reusing
  `selection_scope.pick_ai_source_path`'s ORF preference), matching the
  existing AI-source preference. Only applies on fresh entry into a set (tile
  click, or once grouping resolves for the first file opened at folder load);
  an explicit click on a variant-strip thumbnail always shows exactly that
  file.
- [x] Fixed: clicking a different variant under the preview (e.g. the ORF of a
  stacked JPG+ORF pair) used to clear the left column's highlighted tile,
  because the panel tracked selection by the literal active file rather than
  the group's one visible tile. `SourcePanel` now keeps a
  `member_to_visible_path` map (from `main_window._non_representative_paths_for_current_groups`)
  and resolves highlighting and skip-focus through it
  (`source_panel._apply_multi_selection_style`).
- [x] Fixed: skipping a capture set while a non-representative variant was the
  active preview selection used to reset focus to the first tile in the
  entire column instead of advancing to a neighboring set — the removal logic
  looked up the literal (hidden) selected path's index in the visible-tile
  list and failed. Now resolved via `grid_navigation.resolve_removal_anchor`,
  which maps a hidden member back to its group's visible tile before
  computing the next focus target.
- [x] "Skip Set" stays enabled for a single-image capture set (it falls back to
  skipping just that file, same as `_on_skip_set_selected` already did
  internally) instead of requiring "Skip" for sets of one.
- [x] Skipped files persist across sessions per source folder (`QSettings`,
  keyed by folder path), so re-opening the same SD card/folder keeps
  previously skipped files out of the grid instead of forgetting on restart.

### Part 3 - EXIF read and mapping

- [x] EXIF read service via `exiftool -j -G1 -a -s`.
- [x] Right-panel mapping for editable + technical fields.
- [x] GPS parsing into editable decimal lat/lon/alt fields.
- [x] Capture-time formatting for display.

Implementation note:
- Full EXIF JSON dump is still captured internally for diagnostics, but no dedicated dump viewer is currently shown in the UI.

### Part 4 - Metadata write-back

- [x] Metadata write service with rollback on exiftool failure.
- [x] Idempotent keyword writes (no duplicate growth).
- [x] Save scopes: `Save Single`, `Save Capture Set`.
- [x] Current write targets:
  - Title -> `IPTC:ObjectName`, `XMP-dc:Title`
  - Description -> `IPTC:Caption-Abstract`, `XMP-dc:Description`
  - Keywords -> `IPTC:Keywords`, `XMP-dc:Subject`
  - GPS -> `GPSLatitude`/`GPSLatitudeRef`, `GPSLongitude`/`GPSLongitudeRef`, optional
    `GPSAltitude`/`GPSAltitudeRef` (Ref tags derived from value sign so southern/western
    coordinates read back with the correct hemisphere)

### Part 5 - Rename flow

- [x] Rename generation with deterministic pattern:
  - `sequence_location_YYYYMMDD_HHMM_[artfilter]_camera_lens.ext`
- [x] Sanitization and collision-safe naming.
- [x] Batch `Location` remains a manual session label (not GPS-driven).
- [x] Title auto-populates from filename stem.

### Part 6 - Process & move

- [x] Process scopes: `Single Image`, `Capture Set`, `Current Selection`, `Session`.
  `Current Selection` (`MetadataPanel.process_selection_button`,
  `_on_process_selection_clicked`) processes the active manual multi-selection,
  expanded to each selected file's full capture-group membership (same
  expansion as Save/AI/GPS below) — only enabled while a manual multi-selection
  is active.
- [x] Copy-first workflow (no SD-card deletion).
- [x] Destination routing:
  - ORF -> `/Users/bsmi067/Pictures/DxO/<M Month>/<DD>/`
  - JPG/JPEG -> `/Users/bsmi067/Pictures/DxO/<M Month>/<DD>/jpg/`
- [x] Copy verification by size + SHA-256 checksum.
- [x] Successful files auto-skipped from current session view.

## 2. Phase 2 Completed

### Capture set grouping and browsing

- [x] Grouping service in place.
- [x] Current grouping strategy: capture timestamp at second precision (`DateTimeOriginal` with `CreateDate` fallback).
- [x] Deterministic representative selection:
  - first JPG/JPEG by filename (capture order) preferred; else first file. Switched
    from "largest file" after observing OM System Art Filter Bracket bursts pick a
    heavily-processed (e.g. monochrome/grainy) render as representative, since those
    often compress larger than the plain render of the same shot.
  - Filename order is not a reliable proxy for "plain render first" in every burst
    (a heavily-filtered, e.g. monochrome, JPEG can still sort first alphabetically),
    so this representative is still used for thumbnail/preview/save ordering but
    *not* for AI analysis — see `_ai_source_path_for` below.
- [x] Variant strip in preview panel and selection sync with source panel.
- [x] Group size indicator in source thumbnails.
- [x] Capture grouping reads EXIF in filename-ordered batches (`batch_image_paths`)
  so early files in a folder stack as soon as their batch resolves, instead of
  waiting on the whole folder's EXIF reads. The grouping computation itself
  (`CaptureGroupService.build_groups_from_metadata`) is recomputed over the full
  accumulated metadata after every batch — not per batch in isolation — so a
  same-timestamp set is never split just because its files landed in different
  batches; see the "Grouping quality refinement" fix below for the bug this
  closed.

### AI metadata suggestions

- [x] Provider abstraction: `AiSuggestionService` (`ai_suggestion_service.py`) holds
  only prompting, JSON parsing, and crop-refinement logic. All HTTP/response
  details live behind an `AiProvider` interface (`ai_provider.py`), implemented by
  `OllamaProvider` (`ollama_provider.py`, the default) and `OpenRouterProvider`
  (`openrouter_provider.py`); see "AI provider expansion" below for provider
  selection. Standalone model-comparison eval harness (`eval/run_candidates.py`,
  `eval/run_judge.py`, `eval/summarize.py`) calls providers directly without
  going through Qt — see `eval/RESULTS.md` for the 15-model bake-off this
  produced.
- [x] Group-aware AI apply (one pass on representative, apply editable drafts to all set members).
- [x] AI image-source selection prefers an ORF over the JPEG representative when one
  is present in the target set (`main_window._ai_source_path_for`). The
  representative JPEG can be a heavily-filtered render (monochrome, grainy film,
  etc.) from an Art Filter Bracket burst sharing one unfiltered RAW capture;
  sending that JPEG to the AI skewed the description/keywords toward the filter
  instead of the actual scene. This only changes which file's preview is sent to
  the AI — capture-group `representative_path` (thumbnail/preview/save ordering)
  is untouched.
- [x] Manual multi-select in the left thumbnail nav (`SourcePanel`): cmd-click
  toggles a tile in/out of selection, shift-click selects a contiguous range,
  plain click resets to single-select. When 2+ tiles are manually selected,
  "Suggest Description + Keywords", "Save Capture Set" (relabeled
  "Save Selected (N)"), "Process & Move" -> "Current Selection", and
  GPS/altitude apply (`_gps_target_paths`) all act on the selected files
  *expanded to each one's full capture-group membership*
  (`_expand_to_capture_groups`) rather than the bare selected paths — needed
  because stacked view only shows one representative tile per capture set, so
  selecting representatives of several sets previously applied AI/GPS/save
  results only to those representative files and silently skipped the other
  set members (e.g. the ORF). A path with no capture group (true standalone
  selection, e.g. a same-spot burst the timestamp grouping didn't merge) still
  expands to just itself, so that original ad hoc use case is unchanged.
  `AiSuggestPayload.expand_to_group=False` still applies (no *additional*
  expansion via the AI payload's representative-group lookup), since the
  manual-selection paths passed in are already fully expanded up front.
  GPS/altitude apply already skips any file with its own embedded
  GPS/altitude per-file, so it's safe even across a selection spanning
  different locations. Skip-set remains capture-group-only.
- [x] Model picker in UI: editable `QComboBox` (`MetadataPanel.ai_model_edit`),
  defaulting to `ollama:qwen3.6:35b`, pre-populated with `RECOMMENDED_MODELS`
  (`ai_suggestion_service.py`) ordered by the `eval/RESULTS.md` bake-off. Still
  accepts a typed `provider:model` override for anything not in the list.
- [x] Auto-keyword/description rules, applied at save/process time only (not
  live in the editable UI fields) via `phototags/services/auto_metadata.py`:
  every JPEG gets a `sooc` (straight out of camera) keyword, and any file with
  an in-camera art filter (EXIF `art_filter_token`, same source that already
  powers renaming) gets `In camera effect <filter>.` appended to its
  description. Single shared module used by both `MetadataBatchSaveTask`
  (`metadata_writer.py`) and `ProcessBatchTask` (`process_batch_mover.py`) —
  previously these two had independent, near-duplicate copies of the
  keyword-merging logic; this consolidation fixed that while adding the new
  rules, rather than adding a third copy.
- [x] Vision capability pre-check before any suggestion request: Ollama via
  `/api/tags` capabilities list, OpenRouter via `/api/v1/models`
  `architecture.input_modalities` (see AI provider expansion below).
- [x] Prompt rules for subject specificity + scientific names where possible.
- [x] Crop-refinement fallback when subject specificity likely missing.
- [x] AI status reporting for refinement attempted/applied.
- [x] Timeout-aware fallback chain:
  - Primary request (full quality: model default reasoning/"thinking" left on)
  - Retry with 50% center crop **and thinking disabled** on timeout/empty response
    (measured ~4x latency overhead from reasoning tokens on `qwen3.6:35b`; the
    timeout-retry is a salvage path, not a quality path, so it trades reasoning
    for speed). `AiProvider.chat(..., think: bool)` is the hook; providers that
    don't support a reasoning toggle ignore it.
  - Request timing + payload-size logging for diagnostics
- [x] Empty-response hardening:
  - Broad response-content extraction fallbacks
  - One automatic retry for empty-content responses
  - Clearer user-facing failure path when content remains empty
- [x] Capture-set apply robustness:
  - AI apply now expands to full capture set when grouping finishes after AI request starts

### UI theming

- [x] Dark mode option, restart-to-apply (not a live switch). `phototags/ui/
  styles.py` exports a `Palette` dataclass with light/dark variants for every
  color; the active palette is chosen once at module-import time from a
  persisted `QSettings` preference (`ui/dark_mode`) and re-exported as the
  same flat string constants every widget already imports, so no widget code
  needed to change to consume the active theme — only a handful of previously
  inline hex literals across `source_panel.py`/`metadata_panel.py`/
  `image_preview_widget.py` were promoted to named constants so dark mode
  could actually override them. Dark background is dark grey
  (`PANEL_BACKGROUND`/`WINDOW_BACKGROUND`) per request; other colors are
  lightened/brightened (not simply inverted) from their light-mode values for
  WCAG-reasonable contrast. Toggle lives as a "Dark Mode" checkbox next to
  "Stacked?" in the source panel.
- [x] Fixed: the "Dark Mode" checkbox label itself was unreadable in dark
  mode (no color rule targeted `QCheckBox`, so its text used the real macOS
  appearance's native color while sitting on the custom-painted, always-dark
  panel background). `QCheckBox` is transparent with no opaque background of
  its own, so its text must track the active custom palette like the rest of
  the panel's labels — added it to the existing `BROWN_TEXT` rule in both
  `source_panel.py` (fixes "Dark Mode"/"Stacked?") and `metadata_panel.py`
  (fixes "Auto lookup altitude when missing"). The folder tree (`QTreeView`)
  went the other way: removed its custom text-color override entirely, since
  it paints its own opaque native background regardless of the in-app
  toggle — leaving it fully native means its colors always match its own
  background correctly, light or dark, without tracking the in-app setting.

## 3. Location Enrichment Completed

### Timeline ingest + cache

- [x] `TimelineLocationService` implemented.
- [x] Default timeline source: `gps/Timeline.json`.
- [x] Optional override: `PHOTOTAGS_TIMELINE_PATH`.
- [x] Local SQLite cache at:
  - `~/Library/Application Support/phototags/timeline_cache.sqlite3`
- [x] Idempotent import/upsert by normalized record key.
- [x] Import signature tracks source path + size + mtime; import row stores SHA-256.

### Startup sync from Google Drive

- [x] `TimelineSyncService` checks `~/Library/CloudStorage/GoogleDrive-*/My Drive/AI/Gps/Timeline.json` on
  startup and copies it over the local `gps/Timeline.json` if it is newer (by mtime).
- [x] Runs as a background `TimelineSyncTask` so app launch is never blocked.
- [x] Optional override: `PHOTOTAGS_DRIVE_TIMELINE_PATH` (skips Drive auto-discovery).
- [x] Result surfaced via the existing GPS status label (no copy / copied / error).

### Matching behavior

- [x] Nearest timestamp lookup with strict `<= 30 minutes` window (tightened from 60; cached timeline data shows 98%+ of consecutive recent points are within 30 minutes of each other, so little real coverage is lost).
- [x] No match in window -> GPS remains blank.
- [x] Match ordering prefers better source/accuracy when ties occur.

### GPS UI integration

- [x] Right-panel actions:
  - `Suggest GPS From Timeline`
  - `Apply Suggested GPS`
  - `Lookup Altitude For Set`
- [x] Editable `Lat`, `Lon`, `Alt (m)` fields.
- [x] Wrapped status area with additional space for long suggestions.

### Altitude policy

- [x] Existing camera EXIF GPS fields are preserved and not overwritten.
- [x] Existing EXIF altitude is preserved and lookup will not overwrite it.
- [x] Fixed: many timeline `altitudeMeters` readings are implausible (checked
  `gps/Timeline.json` directly — 61% of raw signal positions with altitude are
  negative, down to -159m, including ~37% of `GPS`-source-tagged points, not
  just `WIFI`/`CELL`). Phone GPS chips have much worse vertical than horizontal
  accuracy, and WIFI-based altitude is a coarse estimate with no real
  altimetry, so source-type alone (the old "unreliable" dimmed-field flag) was
  not a reliable enough signal. Timeline `altitudeMeters` is no longer applied
  at all: `Apply Suggested GPS` now always leaves altitude blank and
  unconditionally triggers `ElevationLookupService` (USGS ground elevation)
  for the applied capture set instead. Removed: the "Auto lookup altitude when
  missing" checkbox (lookup is no longer conditional), `set_gps_altitude_unreliable`
  dimmed-field styling, and the `_gps_altitude_unreliable_by_path`/
  `_gps_altitude_source_by_path` tracking in `main_window.py`.

### Elevation fallback

- [x] `ElevationLookupService` added (USGS EPQS endpoint).
- [x] Manual lookup supported from current editable lat/lon
  (`Lookup Altitude For Set`, for backfilling sets that still have no altitude).
- [x] Automatic lookup now runs unconditionally after every `Apply Suggested GPS`
  (see Altitude policy above), not just when timeline altitude was missing.
- [x] In-memory cache keyed by lat/lon rounded to 4 decimal places (~11m), since
  altitude lookup now runs on every GPS apply rather than only as a manual
  fallback — avoids re-querying USGS for repeat capture sets at the same
  shooting location within one session. Failed lookups are not cached.

## 4. Privacy and Repo Hygiene

- [x] Timeline exports are ignored by Git:
  - `gps/Timeline*.json`
- [x] SQLite artifacts are ignored by Git:
  - `*.sqlite`, `*.sqlite3`, and related sidecars
- [x] Previously committed timeline files were removed from repository history.

## 5. Fresh Timeline Manual Test Checklist

Use this when importing a new full-history timeline export.

### Setup

- [ ] Place fresh export at `gps/Timeline.json` (or set `PHOTOTAGS_TIMELINE_PATH`).
- [ ] Launch app and open folder with known captures.
- [ ] Confirm app remains responsive while first timeline import occurs.

### GPS suggestion behavior

- [ ] For files without EXIF GPS, confirm nearest timeline match appears.
- [ ] Confirm status shows match age/source and wraps cleanly.
- [ ] Confirm no suggestion is applied when nearest point is more than 30 minutes away.
- [ ] Confirm `Apply Suggested GPS` writes editable lat/lon/alt fields.

### Preservation behavior

- [ ] For files with existing EXIF lat/lon, confirm timeline apply is disabled/skipped.
- [ ] For files with existing EXIF altitude, confirm lookup does not overwrite altitude.

### Elevation lookup behavior

- [ ] Confirm `Apply Suggested GPS` always leaves altitude blank initially, then
  fills it from the USGS elevation lookup shortly after (no timeline altitude
  is ever applied).
- [ ] Validate at least one known location against expected terrain/elevation.
- [ ] Confirm repeated `Apply Suggested GPS` at the same shooting location within
  one session does not re-hit the network (cache hit).
- [ ] With missing altitude and valid lat/lon, confirm `Lookup Altitude For Set`
  manually fills altitude for sets that still have none.

### Save/process output behavior

- [ ] Save single file and confirm GPS fields persist via EXIF re-read.
- [ ] Process single/capture-set/session and verify copied outputs retain metadata.
- [ ] Confirm successful process operations skip files from the active session list.

## 6. Open Work / Backlog

### Automated test coverage

- [x] Pytest suite (246 tests, `tests/services/`) covering pure logic
  (`auto_metadata`, `capture_group_service`, `rename_service`,
  `exif_service` field-mapping/GPS-parsing/art-filter-fallback,
  `ai_suggestion_service` JSON-extraction/keyword-normalize/refinement
  decision, `process_move_service` destination routing, and two service
  modules extracted from `main_window.py`/`source_panel.py` for
  testability: `selection_scope.py` and `grid_navigation.py`),
  `subprocess`/`urllib`-boundary-mocked tests for
  `ExifService.read_full_metadata`, `MetadataWriteService`,
  `AiSuggestionService.suggest_for_image`/`_read_previewable_image_bytes`,
  `ElevationLookupService` (including the altitude-lookup cache),
  `ReverseGeocodeService`, `timeline_location_service.py` coordinate/
  timestamp parsing and `suggest_for_capture` end-to-end against a real
  temp SQLite cache, and both AI provider implementations
  (`OllamaProvider`, `OpenRouterProvider`) covering response-extraction
  fallback chains, retry budget logic, timeout detection, capability
  checking, and all network error paths.
  See `docs/TESTING.md` for what's covered and the prioritized list of what
  to add next (integration tests, then `pytest-qt` widget tests only if
  needed).

### Grouping quality refinement

- [x] Fixed: batched EXIF grouping (added for incremental UI feedback) was
  splitting same-timestamp sets (e.g. Art Filter Bracket renders of one shot)
  whenever their files landed in different batches, since each batch called
  `build_groups()` in isolation. `CaptureGroupService.build_groups_from_metadata`
  now separates the I/O (batched, for responsiveness) from the grouping
  computation, which `CaptureGroupLoadTask` recomputes over the full accumulated
  metadata after every batch (cheap, no extra exiftool calls) — so a set is never
  split by an arbitrary batch boundary. `main_window._on_groups_loaded` now
  replaces `_capture_groups`/`_group_by_path` per emission instead of
  concatenating, since each emission is already the full cumulative result.
- [ ] Validate whether second-level grouping causes false merges in dense bursts.
- [ ] Evaluate stronger grouping keys (camera serial + subseconds + exposure guards) only if needed after field testing.


### Performance

- [x] Batched exiftool reads/writes for multi-file operations. exiftool's
  per-invocation cost is dominated by its own process/Perl-interpreter
  startup, so one file at a time was ~15x slower than batching (measured on a
  20-file sample). `ExifService.read_full_metadata_for_paths` and
  `MetadataWriteService.write_description_keywords_for_paths` batch multiple
  files into one exiftool call (chunked via `EXIFTOOL_READ_CHUNK_SIZE`),
  falling back to the existing per-file methods for any path that fails or
  times out in the batch, so per-file error granularity and rollback
  semantics are unchanged. `MetadataBatchSaveTask` (Save Capture Set/Save
  Selected) now batch-reads and groups writes by identical
  description/keywords/GPS values; `ProcessBatchTask` (Process & Move)
  batch-reads only, since each destination file gets a unique
  rename-derived title and so can't share a write batch. The same
  batched-read pattern (multi-file-per-invocation, `SourceFile`-keyed JSON,
  per-file fallback) is documented for the Swift rewrite in
  `MacPhotoMaster-Swift/docs/ARCHITECTURE.md` and implemented in
  `ExifToolClient.readMetadata(at: [URL])`.

### AI model quality and specialization

- [x] Run a model bake-off on representative wildlife/plant/location samples:
  15 vision models (5 local Ollama, 10 OpenRouter) scored against hand-written
  ground truth by an image-grounded LLM judge — see `eval/RESULTS.md` for the
  full table, methodology, and findings (e.g. `gpt-5.5` reasoning by default
  made it ~12x pricier than `gpt-5.1` for a lower score; local models trail the
  strongest cloud models on both quality and speed for this task).
- [ ] Compare at least one strong general vision model against one or more biology-focused/specialized candidates.
- [ ] Define per-subject model recommendations (for example: default general model + optional specialist model for flora/fauna workflows).
- [ ] Tune prompts for difficult bird/flower species and low-light scenes.

### AI provider expansion

- [x] Implement `OpenRouterProvider` (`openrouter_provider.py`), implementing
  `AiProvider`. Auth via `OPENROUTER_API_KEY` env var (must be exported in the
  process environment — this project does not auto-load `.env`). Vision capability
  is checked against `architecture.input_modalities` from `GET /api/v1/models`.
  `think=False` maps to `reasoning: {"effort": "none", "exclude": true}` (a no-op
  hint for models that don't support it).
- [x] Provider selection via `PHOTOTAGS_AI_PROVIDER` env var (`ollama` default,
  `openrouter` to switch). `AiSuggestionService` picks the provider and its
  matching default model (`DEFAULT_PROVIDER_MODEL`) at import time. The model
  dropdown (see "AI metadata suggestions" above) already lists models with
  explicit provider prefixes, so it works the same regardless of this env var.
  Optional override: `PHOTOTAGS_OPENROUTER_MODEL` (default
  `google/gemini-2.5-flash` — cheap/fast, large context, vision-capable, and
  the #2 pinned entry in the model dropdown based on `eval/RESULTS.md`).
- [x] Per-request provider override via model-field prefix: typing or selecting
  `openrouter:<model>` or `ollama:<model>` in the model dropdown routes that one
  request to the named provider regardless of `PHOTOTAGS_AI_PROVIDER`, stripping
  the prefix before it reaches the provider. No prefix falls back to the
  env-var-selected default provider. Provider instances are created lazily per
  prefix and reused (`AiSuggestionService._resolve_provider_and_model`).

### Packaging

- [x] `py2app` build (`setup.py`) producing a Dock-launchable `MacPhotoMaster.app`, with a custom
  icon (`resources/AppIcon.icns`, generated via `scripts/make_icns.sh`). Alias build
  (`py2app -A`) works; standalone build is blocked by a `zlib` incompatibility in `uv`'s
  managed CPython. Full details, rebuild steps, and the icon-regeneration workflow: see
  `docs/PACKAGING.md`.

### Integration stretch goals

- Flickr upload pipeline and metadata mapping is being handled in a separate
  project, not here. Not tracked as a phototags backlog item.

## 8. GitHub Issues — Planned Work

Open as of 2026-06-25. Grouped into clusters by implementation proximity.

### Cluster A — ORF Preview Orientation (Issue #6)

**Problem:** Portrait ORF files display rotated 90° in the preview panel and are also sent to the
AI in the wrong orientation. The image loader (`workers/image_loader.py`) calls
`ImageOps.exif_transpose` on the extracted preview JPEG at lines 68 and 86, but OM System's
embedded preview JPEGs do not carry an `Orientation` tag of their own — the rotation metadata lives
only in the outer ORF EXIF. So `exif_transpose` is a no-op on those previews and the image remains
landscape-rotated.

**Planned fix:**
- `workers/image_loader.py` — `_load_with_exiftool_preview`: after extracting the preview bytes,
  also read the ORF's `Orientation#` value via `exiftool -j -Orientation# <path>` (bundle into a
  single `-j -b -PreviewImage -Orientation#` call to avoid a second subprocess). Map the EXIF
  Orientation integer to the appropriate `Image.Transpose` operation and apply it manually before
  returning, since `exif_transpose` cannot see the outer RAW EXIF from inside the embedded preview
  stream.
- `services/ai_suggestion_service.py` — `_to_web_jpeg`: apply the same orientation correction
  (call `ImageOps.exif_transpose` after `Image.open`, or apply the manual rotation when the JPEG's
  own EXIF Orientation is absent) before calling `thumbnail()` and re-encoding. The AI path bypasses
  `image_loader.py` entirely, so this fix must be applied there independently.

### Cluster B — GPS Auto-Apply on Capture Set Focus (Issue #7)

**Problem:** The user's typical workflow is to click "Suggest GPS From Timeline" then "Apply
Suggested GPS" for every capture set in sequence. These two steps could be automated on focus since
they almost never need manual override.

**Planned fix:**
- In `main_window.py`, in the capture-set focus handler: after EXIF loads for a new set, if the set
  has no existing EXIF GPS (lat/lon blank) and a timeline match is available, automatically run the
  suggest + apply flow without user interaction. Gate with a per-session `set[str]` of "auto-GPS
  already attempted" representative paths to avoid re-triggering on re-focus or grouping updates.
- Keep the existing "Suggest GPS From Timeline" and "Apply Suggested GPS" buttons for manual
  override, force-refresh, or corrections.
- Replace the standalone "Lookup Altitude For Set" button with a compact `QToolButton` refresh icon
  inlined at the trailing edge of the `Alt (m)` field to reclaim vertical space. The GPS status
  label below it already surfaces error details, so the button only needs to be a compact trigger.

### Cluster C — Smart Save After AI Apply / Manual Edit Propagation (Issues #8 and #10)

**Problem (Issue #8):** After the AI returns description + keywords and Apply is clicked, a separate
"Save Capture Set" click is still required. The user wants AI results to auto-save to the capture
set immediately and the save buttons to stay disabled until a subsequent manual change is made.

**Problem (Issue #10):** Manual edits to description or keywords after AI apply are not clearly
tracked as "dirty", which means the user must remember to click Save to propagate them to the full
set. The issue is closely linked to #8: both are about the save button's enabled/disabled state and
when changes flow to group members.

**Planned fix:**
- After `_on_ai_result` applies AI suggestions to the editable fields, automatically trigger the
  Save Capture Set code path (same as the button, not a duplicate write) rather than leaving save
  to the user. Show a brief GPS/AI status message "AI suggestions saved to capture set." Disable
  both Save buttons after the auto-save completes.
- Introduce a per-capture-set "fields dirty since last save" boolean in `main_window.py`. Any
  manual keypress in the description or keywords field sets it; any save (auto or manual) clears it.
  Save buttons are enabled only while dirty is true.
- Verify that "Save Capture Set" already reads from the live editable fields and writes them to
  every group member via `MetadataBatchSaveTask`. If it does, Issue #10 is resolved by the
  dirty-tracking improvement above (manual edit → dirty → Save Capture Set → all members updated).
  Add a test in `tests/` to confirm full-set propagation of manually-edited fields.

### Cluster D — Variant Strip Selection UX (Issue #11)

**Problem:** The variant strip below the main preview (showing JPG / ORF thumbnails for a capture
set) conflates "preview focus" with "metadata selection". Clicking a variant to preview it resets
selection to that single item. The "9/9" counter text implies all are selected but the visual
highlight only marks the last-clicked one. The user wants to browse previews within a set without
unintentionally narrowing which variants receive metadata saves.

**Planned fix:**
- Separate two distinct states in the variant strip widgets:
  - **Selection** (which variants are metadata targets for Save/AI/GPS apply): shown by the
    existing accent-outline border. Defaults to **all members** of the capture set on load.
  - **Preview focus** (which variant is shown in the main preview): shown by a lighter inner
    highlight or a filled dot indicator, distinct from the selection ring.
- Plain click on a strip thumbnail: changes preview focus only. Selection is untouched.
- Cmd-click on a strip thumbnail: toggles that variant in/out of selection (for deliberately
  applying metadata to a subset).
- The source panel's tile highlight must not change when preview focus changes within the strip;
  strip focus-change signals must not propagate to `main_window`'s single-selection handler.
- Replace the "N/N" counter with a partial-selection hint shown only when selection is a proper
  subset (e.g. "3 of 9 selected"), keeping the strip uncluttered when all are selected.

### Cluster E — AI Model Dropdown Label (Issue #9)

**Problem:** `phototags/ui/widgets/metadata_panel.py` line 83 has
`QLabel("AI Suggestions (Ollama)")`. The hard-coded provider name is wrong now that OpenRouter is
also a valid backend.

**Planned fix:** Change to `QLabel("AI Suggestions")`. One-line change.

---

### Implementation order

1. **Cluster E** — trivial, standalone, no risk. Do first.
2. **Cluster A** — self-contained bug fix in two files, covered by existing preview + AI test paths.
3. **Cluster B** — GPS auto-apply + altitude UI compaction. Needs care around re-trigger guards and
   not breaking the manual-override buttons.
4. **Cluster D** — variant strip UX redesign. Requires UI changes to the strip widget, selection
   signal routing, and visual style updates; do after B since the two touch different areas.
5. **Cluster C** — auto-save + dirty tracking. Most behaviour change risk; should come last so A–D
   are stable and can be tested independently.

## 7. Working Assumptions

- SD card workflow remains non-destructive (skip, no delete).
- Batch `Location` remains a manual session label for naming context.
- Timeline matching remains nearest-time within 30 minutes.
- For altitude, timeline data is never used; USGS elevation lookup is the sole source, applied automatically on every GPS apply.
