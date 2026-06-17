## Part 1 - Plan

- [x] Confirm scope and constraints from `AGENTS.md` (macOS only, `uv`, PySide6, non-destructive delete, background workers).
  - Test: checklist is agreed and no unresolved blockers remain.
- [x] Create app shell with 3 panels (Source, Preview, Metadata/Actions).
  - Test: `uv run python main.py` opens a window with all three panels visible.
- [x] Define a minimal project structure for UI, metadata, file ops, and workers.
  - Test: imports resolve cleanly and app starts without runtime import errors.

## Part 2 - File handling - read SD

- [x] Implement source browser to select SD card and browse directories.
  - Test: selecting a folder updates file list for `.jpg`, `.jpeg`, `.orf`.
- [x] Implement thumbnail grid with background loading (`QThread` or `QRunnable`).
  - Test: UI remains responsive while loading 100+ files.
- [x] Implement full preview sync with selected thumbnail and zoom controls.
  - Test: thumbnail selection updates preview immediately and zoom works both directions.

### Part 2 implementation notes (completed)

- Source panel now uses `QFileSystemModel` + `QTreeView` for folder browsing and a thumbnail grid in `QScrollArea`.
- Thumbnails and center preview use background `QRunnable` tasks (`ImageLoadTask`) to avoid blocking the UI thread.
- Separate thread pools are used for thumbnails vs preview so selected image preview is not starved by large thumbnail queues.
- RAW fallback for ORF now uses `exiftool -b -PreviewImage` when Pillow cannot decode the raw file directly.
- Preview now defaults to fit-to-pane on load, keeps manual zoom (1-400%), and includes a `Fit` button.
- Worker lifetime management retains active task/signal references until completion to avoid teardown races and crashes.
- Manual verification completed against `/Volumes/OM SYSTEM/DCIM/105OMSYS` with ~3K files:
  - All thumbnails loaded.
  - JPG and ORF previews rendered.
  - Preview no longer remains stuck on "Loading...".

## Part 3 - Metadata handling - read exif

- [x] Build an `exiftool` read service wrapper (single-purpose API).
  - Test: known sample image returns expected EXIF fields.
- [x] Map EXIF into right-panel fields: title, description, keywords, camera/lens/date-time.
  - Test: selecting an image populates fields correctly, including fallback values for missing tags.

### Part 3 implementation notes (completed)

- Added `ExifService` (`phototags/services/exif_service.py`) to read full metadata and map UI fields.
- Read command used for metadata dump and field extraction:
  - `exiftool -j -G1 -a -s <file>`
- Added async EXIF loading worker (`phototags/workers/exif_loader.py`) to keep the UI responsive while selecting files.
- Added temporary full EXIF debug viewer in lower-right panel (`QPlainTextEdit`, scrollable, no-wrap).
- Debug viewer is intentionally temporary and will be removed once final metadata fields are selected for dedicated UI controls.
- Added read-only technical fields for camera (make + model), lens type, aperture, shutter speed, focal length, focus distance, and capture date-time.
- Capture date-time display is formatted in a longer human-readable style in UI, while raw EXIF date-time is retained for filename generation logic.
- Verified on `/Volumes/OM SYSTEM/DCIM/105OMSYS`:
  - EXIF fields populate from selection.
  - Full JSON EXIF dump appears in debug pane.

### ExifTool reference details used

- `-j` (JSON output) was used so full metadata can be parsed reliably into Python structures.
- `-G1` was used to include family-1 group names in keys (example: `ExifIFD:DateTimeOriginal`), reducing tag name ambiguity.
- `-a` was used to allow duplicate tags to be extracted when present.
- `-s` was used for short tag names to keep JSON keys concise and stable.
- Source docs:
  - `https://exiftool.org/ExifTool.html`
  - `https://exiftool.org/exiftool_pod2.html`

## Part 4 - Metadata handling - write back changed and new exif

- [x] Build an `exiftool` write service for edited fields.
  - Test: save action persists updates verified by immediate reread.
- [x] Support idempotent writes (no duplicate keyword growth on repeated save).
  - Test: saving same values twice produces unchanged keyword list.
- [x] Add error reporting and rollback behavior for failed writes.
  - Test: simulated failure shows clear error and leaves file unchanged.

### Part 4 implementation notes (completed for current scope)

- Current Part 4 scope is Description + Keywords only (Title remains deferred until Part 5 rename behavior is finalized).
- Added `MetadataWriteService` (`phototags/services/metadata_write_service.py`) with:
  - description writes to `IPTC:Caption-Abstract` (primary) and mirrored `XMP-dc:Description`
  - keywords writes to `IPTC:Keywords` and mirrored `XMP-dc:Subject`
- Added `Save Description + Keywords` action in the right panel and async write worker (`phototags/workers/metadata_writer.py`).
- Keyword normalization is comma-delimited with whitespace trim and case-insensitive de-duplication.
- Idempotence fix: list tags are rewritten via repeated `-Tag=value` assignments (not `+=`) after clearing.
- Rollback strategy: if exiftool write fails and `<file>_original` exists, backup is restored; on success backup is removed.
- Verified by automated temp-file tests:
  - two identical saves preserve keyword set without growth
  - IPTC/XMP description and keyword tags match expected values
  - UI status shows save success/failure messages

## Part 5 - File renaming

- [x] Implement rename pattern engine based on `examples/` defaults.
  - Test: generated name matches expected output for known EXIF fixture.
- [x] Add filename sanitization and collision handling.
  - Test: invalid path characters are removed and collisions append increment suffix.
- [x] Add preview of final filename before processing.
  - Test: preview updates when metadata/rename settings change.

### Part 5 implementation notes (completed)

- Added `RenameService` (`phototags/services/rename_service.py`) with default pattern based on example scripts:
  - `sequence_location_YYYYMMDD_HHMM_cameraModel_lensModel.ext`
- Added sanitization for invalid filename characters and whitespace normalization.
- Added collision-safe preview logic (`_1`, `_2`, ...) against names already present in the current folder.
- Added optional Location token input in metadata panel for rename generation.
- Location input is batch-level in the UI and persists across file selection until changed.
- Title behavior updated: Title field is auto-populated from the generated filename stem.
- Pattern refinement: original filename segment removed for shorter names; camera/lens tokens now use model values.
- Added conditional ArtFilter token support in rename pattern:
  - uses first `ArtFilterEffect` segment when not `Off`
  - fallback order: `PictureMode` profile -> `StackedImage` -> `MultipleExposure`
  - inserted between time and camera model in filename
- Hidden macOS resource-fork sidecar files (`._*`) are now excluded from source image list so preview/EXIF/rename operate on real image files.

## Part 6 - File handling - move to Mac storage, or deletion options

- [x] Implement `Process & Move`: copy selected file to destination structure using rename preview, verify copy, then write metadata to copied file.
  - Test: destination file exists, checksum matches source, metadata is written on copied file.
- [x] Implement `Delete/Skip` behavior for SD workflow: remove file from current app session queue only (no disk delete).
  - Test: selected image disappears from thumbnail queue and source file remains on SD card.

### Part 6 implementation notes (completed)

- Destination root is fixed to `/Users/bsmi067/Pictures/DxO`.
- Destination folders are derived from capture date:
  - month folder format: `<month-number> <MonthName>` (example: `6 June`)
  - day folder format: `DD` (example: `01`)
- File-type routing:
  - ORF files copy to `<root>/<month>/<day>/`
  - JPG/JPEG files copy to `<root>/<month>/<day>/jpg/`
- Process flow is now copy-only for SD card workflow:
  - no source deletion is performed after copy
  - copied file is verified by size and SHA-256 checksum before success is reported
  - metadata write is applied to the copied destination file
- `Delete (Cmd+Backspace)` now means "skip/don't copy" for this session; it does not move files to Trash or modify SD content.

## Phase 2

- [x] Group related ORF/JPG variants into one capture set.
  - Test: sample captures show grouped stack entries in thumbnail area.
- [x] Enable browsing inside a group (up to 10 variants) while keeping one primary preview.
  - Test: switching variant updates preview and metadata target correctly.

### Phase 2 persisted decisions (restart snapshot)

- Grouping work is prioritized before deeper AI tuning. Reason: ORF + multiple JPG renderings should share one AI pass.
- There does not appear to be a reliable direct ORF↔JPG linkage tag in current samples; grouping should use capture-time strategy first.
- Group key strategy v1:
  - Primary key: `CameraSerial + DateTimeOriginal + SubSecTimeOriginal`
  - Fallback when subseconds are missing: bucket by `DateTimeOriginal` with ±1 second tolerance plus `ExposureTime + FNumber + ISO + FocalLength` guard values.
- Planned UI behavior:
  - Main selection remains in center preview.
  - Add a variant thumbnail row below preview to switch among files in the same capture group.
  - Typical group size expected <=10, but UI must handle larger accidental time-buckets gracefully.
- Planned AI behavior once grouping is in:
  - Run one AI suggestion pass per group (not per variant).
  - Representative image preference order: largest JPG in group, otherwise ORF embedded preview.
  - Description goes directly into editable Description field.
  - Keywords remain non-destructive in suggested area until user explicitly merges.

### Phase 2 immediate implementation tasks

- [x] Add grouping debug mode to inspect computed group keys and members before final UI changes.
  - Test: debug output shows stable groups for ORF+JPG sets and flags ambiguous buckets.
- [x] Add group model + storage objects (`CaptureGroup`, representative image selection, member ordering).
  - Test: each selected file resolves to exactly one group and a deterministic representative.
- [x] Add preview-area variant strip (below main preview) and wire selection sync.
  - Test: selecting a variant updates preview/EXIF while keeping group context.

### Phase 2 grouping implementation notes (completed for current scope)

- Added `CaptureGroupService` (`phototags/services/capture_group_service.py`) with deterministic grouping output:
  - current grouping key: `DateTimeOriginal` (second-level bucket, with `CreateDate` fallback)
  - this intentionally groups same-second captures together for single-camera SD ingest and group-level AI workflows
  - representative selection: prefer largest JPG/JPEG in group, otherwise largest file
  - deterministic member ordering and reverse lookup (`path -> CaptureGroup`)
- Added async grouping worker (`phototags/workers/capture_group_loader.py`) so folder grouping does not block the UI thread.
- Source panel now annotates grouped files with set size in thumbnail captions (example: `[3 in set]`).
- Added center-panel capture variant strip below preview:
  - shows current set members
  - selecting a variant switches preview, EXIF load target, and selection state in source panel
  - variant controls now use thumbnails (with extension fallback) instead of filename text for faster visual filter/art-style comparison
- Startup wiring fix: initial folder grouping is now explicitly triggered after signal connections in `MainWindow`, so first-load folders are grouped without requiring a manual folder change.
- Added optional grouping debug output controlled by `PHOTOTAGS_GROUP_DEBUG` (`1/true/yes`):
  - prints computed group strategy, key text, and group members to stdout for inspection.
- Save/Process actions remain file-level; AI suggestion apply now runs group-level and writes editable per-file drafts.

## Ollama models - which are best for image description, segmentation, bird identification - local machine 128GB M1 Unified memory

- [ ] Benchmark candidate local models for three tasks: captioning, keywording, bird/flower ID.
  - Test: results table includes speed, memory use, and output quality on a fixed sample set.
- [ ] Define prompt templates for title/description/keywords suggestions.
  - Test: templates produce consistent JSON-like structured output for 20 sample images.
- [x] Add group-aware AI suggestion flow for Phase 2:
  - one AI pass per capture group using the representative image
  - description and keywords are directly applied to each file as editable per-image drafts
  - Test: switch between variants and verify per-file edits persist before save/process.
- [x] Add model selection and capability validation:
  - UI model input field added; default model now `qwen3.6:35b`
  - preflight check against Ollama `/api/tags` ensures selected model supports `vision`
  - Test: choosing a non-vision model returns a clear UI error before inference.
- [x] Add prompt and inference quality refinements:
  - strengthened rules for species naming in description (bird/animal/plant/flower)
  - reduced false monochrome descriptions for muted-color images
  - two-pass fallback (full image + subject-focused crops) when subject keywords are missing from description
  - Test: when fallback triggers, status line indicates `crop-refinement attempted/applied`.

### Phase 2 AI implementation notes (updated)

- Added local Ollama suggestion flow (`Suggest Description + Keywords`) using a background worker.
- AI now runs at capture-group level and applies to all group members as individual editable drafts.
- Description and keywords are both written directly into the editable fields; separate suggested-keywords UI was removed to reclaim right-panel space.
- Art filter token is auto-added to keywords (when present) before AI keyword append.
- Default Ollama model is now `qwen3.6:35b` and can still be overridden with `PHOTOTAGS_OLLAMA_MODEL`.
- Added model capability pre-check (`vision` required) to prevent silent bad outputs when text-only models are selected.
- Added two-pass fallback for difficult wildlife/botanical IDs:
  - pass 1 on representative full image
  - fallback pass on deterministic tighter crops when subject keywords are not reflected in description
  - merged result keeps keyword de-duplication and reports refinement debug status in UI.

### Suggested Ollama vision models to benchmark first (M1 Ultra 128GB)

- `gemma4:12b` (7.6GB), `gemma4:26b` (18GB), and `gemma4:31b` (20GB): top-tier current candidates for multimodal quality on local Apple Silicon; benchmark against Qwen for caption + ID quality.
- `qwen2.5vl:7b` (6.0GB) and `qwen2.5vl:32b` (21GB): strong vision-language generalists, good primary candidates for photo description + keywording.
- `qwen2.5vl:72b` (49GB): high-quality option for harder fine-grained reasoning/identification if latency is acceptable.
- `gemma3:12b` (8.1GB) and `gemma3:27b` (17GB): strong multimodal alternatives with long context and good practical throughput.
- `minicpm-v:8b` (5.5GB): efficient model with good OCR/multi-image behavior; strong fast-pass candidate.
- `llava:13b` (8.0GB) and `llava:34b` (20GB): useful baseline and compatibility fallback.
- `moondream:1.8b` (1.7GB): very fast lightweight baseline for quick triage; expect lower fine-detail reliability.

### Suggested image sizing plan for AI benchmarking

- Global scene description + keywords: start with long edge `1280` (current code uses `1600`; evaluate both).
- Localization/segmentation prompt pass: long edge `1536` to `2048`.
- Fine bird/flower ID on cropped regions: crop from source, then run long edge `768` to `1024`.
- Record quality/latency tradeoff by task before locking defaults.

### Model availability references

- Ollama vision capability docs: `https://docs.ollama.com/capabilities/vision`
- Gemma 4 library page: `https://ollama.com/library/gemma4`
- Qwen2.5-VL library page: `https://ollama.com/library/qwen2.5vl`
- Gemma 3 library page: `https://ollama.com/library/gemma3`
- MiniCPM-V library page: `https://ollama.com/library/minicpm-v`
- LLaVA library page: `https://ollama.com/library/llava`
- Moondream library page: `https://ollama.com/library/moondream`

## Handling sets of images - as described in AGENTS.md - jpg variants of the original RAW files.

- [ ] Confirm final grouping key after field test batches (including multi-exposure and stacked images).
  - Test: grouping key correctly merges expected ORF/JPG pairs on sample media with low false merges.
- [x] Add UI indicator of grouped set size and selected variant.
  - Test: grouped entries display count and selected item clearly.

### Set UI refinements (completed)

- Capture-set thumbnail strip in preview panel was increased in height to avoid bottom clipping of variant thumbnails/buttons.
- Variant controls were nudged upward by tightening local panel spacing.

## Location Enrichment (Planning Only) - Timeline.json

- [ ] Define a location ingestion contract from `gps/Timeline.json`.
  - Test: parser extracts normalized points + visits + activities with UTC timestamps and lat/lon floats.
- [ ] Define photo-to-location matching strategy.
  - Test: known photo capture times resolve to nearest timeline point/visit with confidence labels.
- [ ] Decide cache/persistence approach for timeline data.
  - Test: repeat runs avoid full 78MB reparsing unless source file changed.
- [ ] Define UI integration for location suggestions (non-destructive).
  - Test: location suggestion can prefill batch `Location` field and remain user-editable.

### Timeline.json observations (current sample)

- File size: ~78.6MB (`gps/Timeline.json`).
- Segment count: `34,892` semantic segments.
- Segment composition:
  - `timelinePath`: `12,885` segments (`167,704` path points total)
  - `visit`: `10,962` segments
  - `activity`: `10,936` segments
- Coordinates are encoded as strings with degree symbols (example: `"47.5554554°, -122.0495129°"`), so parsing/normalization is required.
- Time fields are ISO timestamps with offsets; some segments also include explicit `TimezoneUtcOffsetMinutes`.

### Proposed consumption pipeline (no code yet)

- Step 1: Parse + normalize
  - Read `semanticSegments` and flatten into normalized records.
  - Normalize timestamps to UTC epoch for fast matching.
  - Parse coordinate strings into `(lat, lon)` floats.
- Step 2: Build matchable timeline index
  - `timelinePath` points become precise time-location samples.
  - `visit` segments provide stationary place candidates (`placeId`, semantic type, probability).
  - `activity` segments provide start/end movement anchors when path points are sparse.
- Step 3: Match photos
  - Use `DateTimeOriginal` (or `CreateDate` fallback) from EXIF.
  - Find nearest point within configurable tolerance window (for example ±5 to ±15 minutes).
  - Assign confidence tiers:
    - high: direct nearby `timelinePath` hit
    - medium: inside `visit` interval
    - low: interpolated from activity start/end only
- Step 4: UI usage
  - Show suggested location as non-destructive helper text/action.
  - Allow one-click apply to batch `Location` field, then manual edit.

### Pre-processing and DB recommendation

- V1 recommendation: no DB yet.
  - Preprocess `Timeline.json` once into a compact cached normalized file (for example JSONL) keyed by source file mtime/hash.
  - Load/cache this index at app start or first use; reuse for the session.
- When to add SQLite:
  - multiple timeline files/users, incremental updates, very large histories, or advanced querying (spatial/time filters, reverse geocode cache).
  - Suggested schema if needed later:
    - `timeline_points(ts_utc, lat, lon, source_type, segment_id, confidence, place_id, semantic_type)`
    - index on `ts_utc`; optional index on `(lat, lon)` or geohash.

## Stretch goal - integration with Photolab 9.0 locally

- [ ] Investigate practical integration path (folder/watch workflow and sidecar compatibility).
  - Test: documented workflow proof validated with one round-trip file.

## Stretch goal 2 - upload to Flickr

- [ ] Define export/upload pipeline and required metadata mapping.
  - Test: one manual upload verifies title, description, and tags appear correctly.

## To Do - Field Test Set

- [ ] Capture a targeted test batch with varied camera settings to validate rename/token behavior:
  - Include ArtFilter on/off cases and profile-based PictureMode cases.
  - Include StackedImage variants (for example HDR/stacked outputs).
  - Include MultipleExposure on/off examples.
  - Include mixed JPG + ORF captures from the same scenes.
  - Verify filename tokens, metadata display, and save behavior for all variants.
