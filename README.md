# phototags

Local macOS photo workflow app (PySide6) for SD card ingest, preview, metadata editing, renaming, and safe transfer.

## Run

```bash
uv run python main.py
```

Optional source override:

```bash
uv run python main.py --source "/Volumes/OM SYSTEM/DCIM/105OMSYS"
```

Current status:
- Part 1 complete: app shell and project structure.
- Part 2 complete: SD folder browsing, thumbnail loading, preview with fit-to-pane and zoom, ORF preview fallback.
- Part 3 complete: EXIF read service, mapped metadata fields, and temporary full EXIF debug dump panel.
