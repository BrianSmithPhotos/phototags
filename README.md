# phototags (MacPhotoMaster)

Local macOS desktop app for SD-card photo ingest, metadata editing, filename generation, AI-assisted tagging, GPS enrichment from Google Timeline exports, and verified copy to local storage.

## Current Scope

The app is a single-window PySide6 workflow with three panels:

1. Source Browser (left)
- Folder tree + thumbnail grid
- Supports `.jpg`, `.jpeg`, `.orf`
- Groups related files into capture sets
- Skip behavior hides files from the current session only (no disk delete)

2. Image Preview (center)
- Large preview with zoom and fit controls
- Capture-set variant strip for switching among grouped files
- Cmd+Backspace shortcut maps to session skip (not file deletion)

3. Metadata & Actions (right)
- Editable: Title, Description, Keywords
- Read-only technical fields: camera, lens, aperture, shutter, focal length, focus distance, capture time, ISO
- AI Suggestions (local Ollama): description + keywords
- GPS Enrichment: timeline lookup/apply, altitude lookup, and reliability signaling
- Rename preview with batch `Location` label
- Save and Process actions at single / capture-set / session scopes

## Implemented Features

- Responsive background workers for thumbnail/preview/EXIF/AI/GPS/save/process tasks
- EXIF read via `exiftool`
- Metadata write via `exiftool`:
  - Title (`IPTC:ObjectName`, `XMP-dc:Title`)
  - Description (`IPTC:Caption-Abstract`, `XMP-dc:Description`)
  - Keywords (`IPTC:Keywords`, `XMP-dc:Subject`)
  - GPS (`GPSLatitude`, `GPSLongitude`, `GPSAltitude`) when provided
- Idempotent keyword writes and rollback on write failures
- Rename engine with sanitization and collision handling
- Capture grouping (currently based on capture time at second precision)
- Process & Move copy flow with verification:
  - Destination root: `/Users/bsmi067/Pictures/DxO`
  - ORF -> month/day folder
  - JPG/JPEG -> month/day/`jpg` folder
  - Size + SHA-256 verification before success
- Local Ollama integration with vision capability check and crop-refinement fallback
- Timeline GPS enrichment:
  - Parses `rawSignals.position` + `semanticSegments.timelinePath`
  - Caches normalized records in SQLite
  - Nearest timestamp match with strict 60-minute window
  - Preserves existing EXIF GPS fields (does not overwrite camera-provided GPS)
- Elevation fallback via USGS EPQS when altitude is missing
- Non-GPS timeline altitude handling:
  - Applies value when present
  - Marks altitude as unreliable in UI (dimmed + tooltip)

## Requirements

- macOS
- Python 3.12+
- `uv`
- `exiftool` installed and available on PATH
- Optional for AI features: Ollama running locally (`http://127.0.0.1:11434`)

## Setup

```bash
uv sync
```

## Run

```bash
uv run python main.py
```

Optional source override:

```bash
uv run python main.py --source "/Volumes/OM SYSTEM/DCIM/105OMSYS"
```

Optional smoke test (auto-exit after N ms):

```bash
uv run python main.py --smoke-test-ms 2000
```

## Environment Variables

- `PHOTOTAGS_OLLAMA_MODEL`
  - Default AI model name (default in code: `qwen3.6:35b`)
- `PHOTOTAGS_TIMELINE_PATH`
  - Override default timeline JSON path
- `PHOTOTAGS_GROUP_DEBUG`
  - `1/true/yes` enables grouping debug output in terminal

## Timeline + GPS Data Paths

- Default timeline JSON path: `gps/Timeline.json`
- Timeline cache DB: `~/Library/Application Support/phototags/timeline_cache.sqlite3`

Repository privacy protection is in place:
- `gps/Timeline*.json` ignored
- `*.sqlite`, `*.sqlite3` artifacts ignored

## Notes and Limitations

- Destination root is currently hardcoded in code (`DESTINATION_ROOT` in `phototags/ui/main_window.py`).
- Skip/delete is intentionally non-destructive for SD-card workflow.
- Grouping is deterministic but intentionally simple for now (same captured second).
- AI quality depends on local model and hardware.

## Documentation

- Current implementation status and test checklist: `docs/PLAN.md`
