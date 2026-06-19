## MacPhotoMaster Plan (Current)

Last updated: 2026-06-19

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
  - largest JPG/JPEG preferred; else largest file.
- [x] Variant strip in preview panel and selection sync with source panel.
- [x] Group size indicator in source thumbnails.

### AI metadata suggestions (Ollama)

- [x] Provider abstraction: `AiSuggestionService` (`ai_suggestion_service.py`) holds
  only prompting, JSON parsing, and crop-refinement logic. All Ollama HTTP/response
  details live behind an `AiProvider` interface (`ai_provider.py`) in `OllamaProvider`
  (`ollama_provider.py`), the default provider. Groundwork for an OpenRouter provider
  and a standalone model-comparison eval harness that calls providers directly
  without going through Qt.
- [x] Group-aware AI apply (one pass on representative, apply editable drafts to all set members).
- [x] Local model input field in UI.
- [x] Vision capability pre-check via Ollama tags API.
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

## 3. Location Enrichment Completed

### Timeline ingest + cache

- [x] `TimelineLocationService` implemented.
- [x] Default timeline source: `gps/Timeline.json`.
- [x] Optional override: `PHOTOTAGS_TIMELINE_PATH`.
- [x] Local SQLite cache at:
  - `~/Library/Application Support/phototags/timeline_cache.sqlite3`
- [x] Idempotent import/upsert by normalized record key.
- [x] Import signature tracks source path + size + mtime; import row stores SHA-256.

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

- [ ] Validate whether second-level grouping causes false merges in dense bursts.
- [ ] Evaluate stronger grouping keys (camera serial + subseconds + exposure guards) only if needed after field testing.

### Altitude quality guardrails

- [ ] Add optional altitude plausibility checks (for example soft warnings for extreme values and abrupt jumps within a short capture set).
- [ ] Add a confidence tier for altitude source quality (`GPS` > inferred timeline > external lookup).
- [ ] Add a "prefer lookup over unreliable timeline altitude" option for non-`GPS` source altitudes.

### AI model quality and specialization

- [ ] Run a model bake-off on representative wildlife/plant/location samples:
  - Precision for bird/flower/animal identification
  - Scientific-name usefulness
  - Response consistency and latency
- [ ] Compare at least one strong general vision model against one or more biology-focused/specialized candidates.
- [ ] Define per-subject model recommendations (for example: default general model + optional specialist model for flora/fauna workflows).
- [ ] Tune prompts for difficult bird/flower species and low-light scenes.

### AI provider expansion

- [ ] Implement an `OpenRouterProvider` (implements `AiProvider` in `ai_provider.py`)
  as an alternative to `OllamaProvider`; add provider selection (env var or UI
  dropdown) and an `OPENROUTER_API_KEY` slot in env config.
- [ ] Build a standalone eval harness script (not part of the app) that runs a set
  of sample images + expected-keyword answers through the `AiProvider` interface
  to compare models/providers (keyword-overlap scoring, not LLM-graded).

### Integration stretch goals

- [ ] Investigate practical DxO PhotoLab integration path.
- [ ] Define Flickr upload pipeline and metadata mapping.

## 7. Working Assumptions

- SD card workflow remains non-destructive (skip, no delete).
- Batch `Location` remains a manual session label for naming context.
- Timeline matching remains nearest-time within 30 minutes.
- For altitude, timeline data is preferred when present, but source reliability is surfaced to the user.
