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
- Added read-only technical fields for camera (make + model), lens type, aperture, focal length, focus distance, and capture date-time.
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

- [ ] Build an `exiftool` write service for edited fields.
  - Test: save action persists updates verified by immediate reread.
- [ ] Support idempotent writes (no duplicate keyword growth on repeated save).
  - Test: saving same values twice produces unchanged keyword list.
- [ ] Add error reporting and rollback behavior for failed writes.
  - Test: simulated failure shows clear error and leaves file unchanged.

## Part 5 - File renaming

- [ ] Implement rename pattern engine based on `examples/` defaults.
  - Test: generated name matches expected output for known EXIF fixture.
- [ ] Add filename sanitization and collision handling.
  - Test: invalid path characters are removed and collisions append increment suffix.
- [ ] Add preview of final filename before processing.
  - Test: preview updates when metadata/rename settings change.

## Part 6 - File handling - move to Mac storage, or deletion options

- [ ] Implement `Process & Move`: write metadata, rename, copy to destination, verify success, then remove source.
  - Test: destination file exists and is verified before source is removed.
- [ ] Implement non-destructive delete to macOS Trash (`Cmd+Backspace` shortcut).
  - Test: selected image moves to `~/.Trash/` and is removed from app view.

## Phase 2

- [ ] Group related ORF/JPG variants into one capture set.
  - Test: sample captures show grouped stack entries in thumbnail area.
- [ ] Enable browsing inside a group (up to 10 variants) while keeping one primary preview.
  - Test: switching variant updates preview and metadata target correctly.

## Ollama models - which are best for image description, segmentation, bird identification - local machine 128GB M1 Unified memory

- [ ] Benchmark candidate local models for three tasks: captioning, keywording, bird/flower ID.
  - Test: results table includes speed, memory use, and output quality on a fixed sample set.
- [ ] Define prompt templates for title/description/keywords suggestions.
  - Test: templates produce consistent JSON-like structured output for 20 sample images.
- [ ] Add optional suggestion panel that never overwrites user text without confirmation.
  - Test: user can accept/reject per field and manual edits are preserved.

## Handling sets of images - as described in AGENTS.md - jpg variants of the original RAW files.

- [ ] Determine grouping key strategy (capture timestamp + camera serial + lens + exposure sequence where present).
  - Test: grouping key correctly merges expected ORF/JPG pairs on sample media.
- [ ] Add UI indicator of grouped set size and selected variant.
  - Test: grouped entries display count and selected item clearly.

## Stretch goal - integration with Photolab 9.0 locally

- [ ] Investigate practical integration path (folder/watch workflow and sidecar compatibility).
  - Test: documented workflow proof validated with one round-trip file.

## Stretch goal 2 - upload to Flickr

- [ ] Define export/upload pipeline and required metadata mapping.
  - Test: one manual upload verifies title, description, and tags appear correctly.
