# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

MacPhotoMaster (`phototags`): a macOS desktop app for ingesting photos from an SD card, editing
EXIF/IPTC/XMP metadata, AI-assisted tagging, GPS enrichment from a Google Timeline export, renaming,
and copying files into local storage.

Current status, completed scope, and open backlog live in `docs/PLAN.md` — read it before starting
work and keep it updated as work completes.

Test suite (`tests/`, run with `uv run pytest`) and what's covered vs. not yet covered: `docs/TESTING.md`.
When extracting or adding pure decision logic (no Qt/subprocess/network), add it to `services/` and
cover it there per that doc's conventions.

## Stack & Tooling

- macOS only. Native look and feel, standard Cmd-based shortcuts.
- Environment/dependency manager: `uv`. Use `uv run` / `uv add`. Favor `uv` for running scripts,
  tests, and one-off Python commands too (e.g. `uv run python -m py_compile ...`) — fall back to a
  plain `python3`/activated venv only when `uv` genuinely can't do the job.
- UI: PySide6 (Qt for Python). Do not introduce PyQt5 or Tkinter.
- Image handling: Pillow, for thumbnails/preview only.
- Metadata engine: `exiftool` (external binary, invoked via `subprocess`). All metadata read/write
  goes through it — do not hand-roll EXIF/IPTC/XMP parsing.
- Background work (thumbnails, EXIF reads, AI requests, GPS lookups, metadata writes, file moves)
  must run on `QThreadPool`/`QRunnable` workers, never on the Qt main thread.
- App icon: drawn in code by `Tools/IconGen`, a Swift package built on
  [IconForge](https://github.com/BrianSmithPhotos/IconForge) — shared with the sibling
  MacPhotoMaster-Swift app so the two read as a family. It is a generator run by hand, not part of
  the app; nothing at runtime links against it. Regeneration steps: `docs/PACKAGING.md`.

## Architecture

- `phototags/ui/` — widgets and the main window. UI wiring and state only; delegate real logic to
  `services/`.
- `phototags/services/` — stateless-ish business logic (EXIF mapping, metadata writes, renaming,
  capture grouping, timeline/elevation/geocode lookups, AI suggestions).
- `phototags/workers/` — `QRunnable` wrappers that call into `services/` off the main thread and
  emit Qt signals back to the UI.

When adding a feature, put the logic in a service, wrap it in a worker if it does I/O or is slow,
and keep the UI layer to wiring/state only. `main_window.py` is still the largest file and has
several distinct responsibilities (capture-group orchestration, AI-apply, GPS/geocode/altitude
orchestration, save, process/move) wired into one class — when touching it, prefer extracting a
focused coordinator class for the piece you're changing rather than adding another method to the
existing class.

AI suggestions follow a provider pattern: `ai_suggestion_service.py` owns prompting, response
parsing, and crop-refinement logic and is backend-agnostic. The actual backend implements the
`AiProvider` interface in `ai_provider.py` — `OllamaProvider` (`ollama_provider.py`) and
`OpenRouterProvider` (`openrouter_provider.py`) are the two implementations today, selected via the
model dropdown's `ollama:`/`openrouter:` prefix (see `RECOMMENDED_MODELS` in
`ai_suggestion_service.py`, ordered by the `eval/RESULTS.md` model bake-off). Adding another
backend means writing one new `AiProvider` implementation, not touching `ai_suggestion_service.py`.

## Coding Style

- Python 3.10+, type hints mandatory on all functions.
- Keep functions small and single-purpose.
- Docstrings only where the *why* isn't obvious from the signature — not on every function.
- No over-engineering: no speculative abstractions, no defensive code for cases that can't happen,
  no feature flags for hypothetical futures. Three similar lines beat a premature helper.
- No emojis, anywhere, ever.
- When debugging, find the root cause before changing code — don't guess-and-check.

## File Safety

- Deleting an image must move it to `~/.Trash/` (or use the macOS trash API), never `os.remove()`.
- When moving files off the SD card, verify the destination write (size + checksum) before treating
  the source as safe to skip/remove from the session view. Never delete from the SD card automatically.

## Secrets & Privacy

- `gps/Timeline*.json` and `*.sqlite*` are gitignored — never remove that ignore or commit timeline
  exports or the location cache.
- This repo's root contains a `.env` with API keys for mostly-unrelated tooling (LangSmith, SendGrid,
  etc.); it is gitignored. phototags itself does not auto-load `.env` — `OPENROUTER_API_KEY` must be
  exported into the process environment for `OpenRouterProvider` to work (in practice this often
  means `set -a && source .env && set +a` before running the app/eval scripts, since that key
  happens to live in this same file). Don't add new phototags-specific secrets into this file; it's
  shared with unrelated tooling.

## Color Scheme

Light mode (default):
- Accent Cyan: `#20d6d3` — accent lines, highlights
- Orange Primary: `#d68220` — links, key sections
- Salmon Secondary: `#d6755f` — submit buttons, important actions
- Dark Teal: `#385756` — main headings
- Brown Text: `#574938` — supporting text, labels

A dark mode option also exists (`phototags/ui/styles.py`'s `Palette`
dataclass, toggled via the "Dark Mode" checkbox in the source panel,
restart-to-apply). When adding any new color to a widget's stylesheet,
add it as a named field on both `LIGHT_PALETTE` and `DARK_PALETTE` in
`styles.py` rather than hardcoding a hex literal in the widget file — that's
the only way dark mode can pick it up.
