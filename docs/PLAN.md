## Part 1 - Plan

- [ ] Confirm scope and constraints from `AGENTS.md` (macOS only, `uv`, PySide6, non-destructive delete, background workers).
  - Test: checklist is agreed and no unresolved blockers remain.
- [ ] Create app shell with 3 panels (Source, Preview, Metadata/Actions).
  - Test: `uv run python main.py` opens a window with all three panels visible.
- [ ] Define a minimal project structure for UI, metadata, file ops, and workers.
  - Test: imports resolve cleanly and app starts without runtime import errors.

## Part 2 - File handling - read SD

- [ ] Implement source browser to select SD card and browse directories.
  - Test: selecting a folder updates file list for `.jpg`, `.jpeg`, `.orf`.
- [ ] Implement thumbnail grid with background loading (`QThread` or `QRunnable`).
  - Test: UI remains responsive while loading 100+ files.
- [ ] Implement full preview sync with selected thumbnail and zoom controls.
  - Test: thumbnail selection updates preview immediately and zoom works both directions.

## Part 3 - Metadata handling - read exif

- [ ] Build an `exiftool` read service wrapper (single-purpose API).
  - Test: known sample image returns expected EXIF fields.
- [ ] Map EXIF into right-panel fields: title, description, keywords, camera/lens/date-time.
  - Test: selecting an image populates fields correctly, including fallback values for missing tags.

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
