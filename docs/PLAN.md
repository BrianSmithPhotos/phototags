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

- [ ] Group related ORF/JPG variants into one capture set.
  - Test: sample captures show grouped stack entries in thumbnail area.
- [ ] Enable browsing inside a group (up to 10 variants) while keeping one primary preview.
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

- [ ] Add grouping debug mode to inspect computed group keys and members before final UI changes.
  - Test: debug output shows stable groups for ORF+JPG sets and flags ambiguous buckets.
- [ ] Add group model + storage objects (`CaptureGroup`, representative image selection, member ordering).
  - Test: each selected file resolves to exactly one group and a deterministic representative.
- [ ] Add preview-area variant strip (below main preview) and wire selection sync.
  - Test: selecting a variant updates preview/EXIF while keeping group context.

## Ollama models - which are best for image description, segmentation, bird identification - local machine 128GB M1 Unified memory

- [ ] Benchmark candidate local models for three tasks: captioning, keywording, bird/flower ID.
  - Test: results table includes speed, memory use, and output quality on a fixed sample set.
- [ ] Define prompt templates for title/description/keywords suggestions.
  - Test: templates produce consistent JSON-like structured output for 20 sample images.
- [x] Add optional suggestion panel for AI-assisted review:
  - description is populated directly into Description for in-place editing
  - keywords are shown in a separate suggested box and only merged into Keywords when user clicks apply
  - Test: user can iterate AI suggestions, edit description manually, and selectively merge keyword suggestions.

### Phase 2 initial implementation notes (in progress)

- Added local Ollama suggestion flow (`Suggest Description + Keywords`) using a background worker.
- Added read-only "suggested keywords" panel plus `Add Suggested -> Keywords` merge action.
- Description suggestions are written directly into the editable Description field, matching current workflow preference.
- Default Ollama model is `llava` and can be overridden with `PHOTOTAGS_OLLAMA_MODEL`.

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
- [ ] Add UI indicator of grouped set size and selected variant.
  - Test: grouped entries display count and selected item clearly.

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
