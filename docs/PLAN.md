## MacPhotoMaster Plan (Current)

Last updated: 2026-06-21

This document is the active implementation snapshot + next-step checklist.

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

- [x] Process scopes: `Single Image`, `Capture Set`, `Session`.
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
- [x] Manual multi-select in the left thumbnail nav (`SourcePanel`): cmd-click
  toggles a tile in/out of selection, shift-click selects a contiguous range,
  plain click resets to single-select. When 2+ tiles are manually selected,
  "Suggest Description + Keywords", "Save Capture Set" (relabeled
  "Save Selected (N)"), and GPS/altitude apply (`_gps_target_paths`) all act on
  exactly that set instead of the automatic 1-second capture group — useful
  for bursts shot seconds apart from the same spot that the timestamp-based
  grouping doesn't merge. `AiSuggestPayload.expand_to_group=False` is what
  stops a manual selection from being silently re-expanded to a
  representative's capture-group siblings on AI apply. GPS/altitude apply
  already skips any file with its own embedded GPS/altitude per-file, so it's
  safe even across a manual selection spanning different locations. Skip-set
  remains capture-group-only.
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
  - `Lookup Altitude`
  - `Auto lookup altitude when missing`
- [x] Editable `Lat`, `Lon`, `Alt (m)` fields.
- [x] Wrapped status area with additional space for long suggestions.

### Altitude policy

- [x] Existing camera EXIF GPS fields are preserved and not overwritten.
- [x] Existing EXIF altitude is preserved and lookup will not overwrite it.
- [x] Timeline altitude from non-`GPS` sources (for example `WIFI`) is still applied, but visually marked unreliable (dimmed + tooltip).
- [x] If timeline altitude is missing, optional elevation lookup can populate altitude.

### Elevation fallback

- [x] `ElevationLookupService` added (USGS EPQS endpoint).
- [x] Manual lookup supported from current editable lat/lon.
- [x] Optional automatic lookup after GPS apply when altitude is missing.

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

### Altitude reliability behavior

- [ ] Confirm `GPS` source altitude appears normal (not dimmed).
- [ ] Confirm non-`GPS` source altitude (for example `WIFI`) is dimmed and tooltip-marked unreliable.
- [ ] Confirm manual edit of altitude clears the unreliable styling.

### Elevation lookup behavior

- [ ] With missing altitude and valid lat/lon, confirm `Lookup Altitude` fills altitude.
- [ ] With auto lookup enabled and missing timeline altitude, confirm lookup auto-runs after apply.
- [ ] Validate at least one known location against expected terrain/elevation.
- [ ] Validate non-`GPS` timeline altitude samples (for example `WIFI`) against known terrain and note expected error envelope.

### Save/process output behavior

- [ ] Save single file and confirm GPS fields persist via EXIF re-read.
- [ ] Process single/capture-set/session and verify copied outputs retain metadata.
- [ ] Confirm successful process operations skip files from the active session list.

## 6. Open Work / Backlog

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

### Altitude quality guardrails

- [ ] Add optional altitude plausibility checks (for example soft warnings for extreme values and abrupt jumps within a short capture set).
- [ ] Add a confidence tier for altitude source quality (`GPS` > inferred timeline > external lookup).
- [ ] Add a "prefer lookup over unreliable timeline altitude" option for non-`GPS` source altitudes.

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

### Integration stretch goals

- Flickr upload pipeline and metadata mapping is being handled in a separate
  project, not here. Not tracked as a phototags backlog item.

## 7. Working Assumptions

- SD card workflow remains non-destructive (skip, no delete).
- Batch `Location` remains a manual session label for naming context.
- Timeline matching remains nearest-time within 30 minutes.
- For altitude, timeline data is preferred when present, but source reliability is surfaced to the user.
