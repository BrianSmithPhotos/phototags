# phototags (MacPhotoMaster)

Local macOS desktop app for SD-card photo ingest, metadata editing, filename generation, AI-assisted tagging, GPS enrichment from Google Timeline exports, and verified copy to local storage.

## Current Scope

The app is a single-window PySide6 workflow with three panels:

1. Source Browser (left)
- Folder tree + thumbnail grid
- Supports `.jpg`, `.jpeg`, `.orf`
- Groups related files into capture sets (1-second capture-time grouping)
- Cmd-click / shift-click multi-select to apply description, keywords, and
  GPS/altitude across a manually-chosen set of photos instead of (or as well
  as) the automatic capture-set grouping
- "Stacked?" checkbox collapses each capture set to one representative tile
- "Dark Mode" checkbox (restart to apply)
- Skip behavior hides files from the current session only (no disk delete)

2. Image Preview (center)
- Large preview with zoom and fit controls
- Capture-set variant strip for switching among grouped files
- Cmd+Backspace shortcut maps to session skip (not file deletion)

3. Metadata & Actions (right)
- Editable: Title, Description, Keywords
- Read-only technical fields: camera, lens, aperture, shutter, focal length, focus distance, capture time, ISO
- AI Suggestions: editable model dropdown (local Ollama and OpenRouter models, ordered by the
  `eval/RESULTS.md` model bake-off; defaults to local `qwen3.6:35b`) generates description + keywords
- GPS Enrichment: timeline lookup/apply, altitude lookup, and reliability signaling
- Rename preview with batch `Location` label
- Save and Process actions at single / capture-set / multi-selected / session scopes

## Implemented Features

- Responsive background workers for thumbnail/preview/EXIF/AI/GPS/save/process tasks
- EXIF read via `exiftool`
- Metadata write via `exiftool`:
  - Title (`IPTC:ObjectName`, `XMP-dc:Title`)
  - Description (`IPTC:Caption-Abstract`, `XMP-dc:Description`)
  - Keywords (`IPTC:Keywords`, `XMP-dc:Subject`)
  - GPS (`GPSLatitude`, `GPSLongitude`, `GPSAltitude`) when provided
- Idempotent keyword writes and rollback on write failures
- Auto metadata rules applied at save/process time (`phototags/services/auto_metadata.py`):
  - Every JPEG gets a `sooc` (straight out of camera) keyword
  - Files with an in-camera art filter (EXIF `art_filter_token`) get
    `In camera effect <filter>.` appended to the description
- Rename engine with sanitization and collision handling
- Capture grouping (currently based on capture time at second precision), plus manual cmd-click/
  shift-click multi-select as an alternative scope for AI suggest, save, and GPS/altitude apply
- Process & Move copy flow with verification:
  - Destination root: `/Users/bsmi067/Pictures/DxO`
  - ORF -> month/day folder
  - JPG/JPEG -> month/day/`jpg` folder
  - Size + SHA-256 verification before success
- AI suggestions via a provider abstraction (`AiProvider`): local Ollama (default) or OpenRouter,
  selectable per-request through the model dropdown's `ollama:`/`openrouter:` prefix; vision
  capability check, timeout-aware center-crop retry, and crop-refinement fallback apply to either
  provider. See `eval/RESULTS.md` for a 15-model accuracy/cost/speed comparison and
  `eval/run_candidates.py`/`eval/run_judge.py` for the (standalone, not part of the app) eval harness.
- Dark mode option (restart-to-apply), `phototags/ui/styles.py`
- Timeline GPS enrichment:
  - Parses `rawSignals.position` + `semanticSegments.timelinePath`
  - Caches normalized records in SQLite
  - Nearest timestamp match with strict 30-minute window
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
- Optional for local AI features: Ollama running locally (`http://127.0.0.1:11434`)
- Optional for cloud AI features: an OpenRouter account + `OPENROUTER_API_KEY` exported in the
  process environment (not auto-loaded from `.env`; see `eval/run_candidates.py` for the pattern of
  sourcing it before running)

## Setup

```bash
uv sync
```

## Run

```bash
uv run python main.py
```

By default, the source folder is auto-detected as the lowest-numbered
`DCIM/<NNN>OMSYS` folder on a mounted OM System SD card (e.g. `105OMSYS`;
cameras roll over to a new folder every 10,000 images), falling back to
`/Volumes` for manual browsing when no such card is mounted
(`phototags/app.py`, `detect_default_source_dir`).

Optional source override:

```bash
uv run python main.py --source "/Volumes/OM SYSTEM/DCIM/105OMSYS"
```

Optional smoke test (auto-exit after N ms):

```bash
uv run python main.py --smoke-test-ms 2000
```

## Environment Variables

- `PHOTOTAGS_AI_PROVIDER`
  - Default AI provider when the model dropdown has no `ollama:`/`openrouter:` prefix
    (`ollama` default, or `openrouter`)
- `PHOTOTAGS_OLLAMA_MODEL`
  - Default Ollama model name (default in code: `qwen3.6:35b`)
- `PHOTOTAGS_OLLAMA_TIMEOUT_SECONDS`
  - Request timeout in seconds for Ollama chat/tags calls (default: `180`)
- `PHOTOTAGS_OLLAMA_KEEP_ALIVE`
  - Ollama keep-alive hint to reduce cold-start delays (default: `15m`)
- `PHOTOTAGS_OLLAMA_MAX_PREDICT`
  - Optional maximum generated tokens per AI request (default: unset; uses model default)
- `PHOTOTAGS_OPENROUTER_MODEL`
  - Default OpenRouter model name (default in code: `google/gemini-2.5-flash`)
- `PHOTOTAGS_OPENROUTER_TIMEOUT_SECONDS`
  - Request timeout in seconds for OpenRouter chat/models calls (default: `120`)
- `PHOTOTAGS_OPENROUTER_APP_URL` / `PHOTOTAGS_OPENROUTER_APP_NAME`
  - App-attribution headers sent to OpenRouter so usage shows up under this app's name in their
    dashboard instead of "Unknown" (defaults already point at this repo/app name)
- `OPENROUTER_API_KEY`
  - Required for any `openrouter:<model>` request; must be exported in the process
    environment (not auto-loaded from `.env`)
- `PHOTOTAGS_TIMELINE_PATH`
  - Override default timeline JSON path
- `PHOTOTAGS_GROUP_DEBUG`
  - `1/true/yes` enables grouping debug output in terminal

## Timeline + GPS Data Paths

- Default timeline JSON path: `gps/Timeline.json`
- Timeline cache DB: `~/Library/Application Support/phototags/timeline_cache.sqlite3`

## Android 16: Export `Timeline.json` From Phone

As of June 17, 2026, Google’s Timeline export flow for Android users is documented in Google Maps Help under **Manage your Google Maps Timeline (Android)**.

Prerequisites:
- Google Maps app updated (Google documents Timeline availability on Maps app `11.106+`)
- Timeline enabled for your account/device

Export steps on Android 16:
1. Open Android `Settings`.
2. Go to `Location` -> `Location services` -> `Timeline`.
3. Under `Timeline`, tap `Export Timeline data`.
4. Tap `Continue`.
5. Choose a storage location.
6. Tap `Save` and wait for the `Export complete` message.

Move and ingest in `phototags`:
1. Copy the exported file from the phone to your Mac.
2. Place it in this repository as `gps/Timeline.json`.
3. Launch the app and use GPS Suggest/Apply; ingestion is automatic.

Notes:
- If the exported filename is not exactly `Timeline.json`, rename it to `Timeline.json` after copying into `gps/`, or set `PHOTOTAGS_TIMELINE_PATH` to the file path you want to use.
- Replacing `gps/Timeline.json` with a fresh export is sufficient; the app detects the new file signature and updates the local SQLite cache.

Repository privacy protection is in place:
- `gps/Timeline*.json` ignored
- `*.sqlite`, `*.sqlite3` artifacts ignored

## Notes and Limitations

- Destination root is currently hardcoded in code (`DESTINATION_ROOT` in `phototags/ui/main_window.py`).
- Skip/delete is intentionally non-destructive for SD-card workflow.
- Grouping is deterministic but intentionally simple for now (same captured second); manual
  cmd-click/shift-click multi-select is available when a broader/different set is needed.
- AI quality/cost/speed varies by model and provider — see `eval/RESULTS.md` for measured comparisons.
- Dark mode requires an app restart to apply; there is no live theme switch.
- Flickr upload is out of scope for this project; that work is being handled separately.

## Documentation

- Current implementation status and test checklist: `docs/PLAN.md`
- AI model comparison (accuracy/cost/speed across 15 models) and eval harness: `eval/RESULTS.md`
- Building a Dock-launchable `.app` bundle (`py2app`) and setting a custom icon: `docs/PACKAGING.md`
