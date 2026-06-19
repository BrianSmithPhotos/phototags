# Agent Instructions: Mac Photo Manager (MacPhotoMaster)

Stack, architecture, and coding-style guidance now lives in `CLAUDE.md` — read that first. This
file is kept for tools that look for `AGENTS.md` specifically; the Phase 2 feature notes below are
historical context for scope that has since been implemented (see `docs/PLAN.md` for current status).

You are an expert Python desktop application developer specializing in macOS, PySide6, and modern Python tooling (`uv`). Your task is to help build a local Mac application that reads photos from an SD card, edits EXIF data, renames files, and moves them to local Mac storage.

## 1. Project Context & Stack
*   **Target OS:** macOS (Native desktop look and feel, standard shortcuts).
*   **Environment Manager:** `uv` (Use `uv pip` or `uv run`. Do not use standard `pip` or `venv`).
*   **UI Framework:** PySide6 (Qt for Python). Do not use PyQt5 or Tkinter.
*   **Image Processing:** Pillow (for UI thumbnails and image loading).
*   **Metadata Engine:** `exiftool` would likely be needed and available installed
*   **File System:** Python `pathlib` and `shutil` for moving/copying files safely.

## 2. Core Application Features
The app is a single-window interface divided into three functional zones:
1.  **Source Browser (Left Panel):** A directory tree/list showing the SD card. Includes a thumbnail grid view of images in the selected folder.
2.  **Image Preview (Center Panel):** A large view of the selected photo with zoom capabilities and a visible "Delete" button (moves file to Mac Trash, not immediate permanent deletion).
3.  **Metadata & Actions (Right Panel):** 
    *   Form fields to view/edit EXIF data (Title, Description, Keywords/Tags).  Full list to be defined - could include camera, lens, exposure etc.
    *   Form fields for File Renaming patterns.  A default renaming can be found in the code in the examples/ directory, where extracted exif data is used to construct a new name
    *   A prominent "Process & Move" button to save metadata, rename, and transfer the file to local Mac storage.

## 3. Critical Code & Architecture Guidelines

### Tooling & Commands
*   Always assume a `uv` workflow. If generating setup instructions, use:
    ```bash
    uv init
    uv add PySide6 Pillow piexif
    ```

### UI & UX (PySide6)
*   **Responsiveness:** Image loading and file moving must happen on a background thread using `QThread` or `QRunnable`. Never block the main GUI thread while reading large images or writing to storage.
*   **macOS Conventions:** Use standard macOS keyboard shortcuts where applicable (e.g., `Cmd+Backspace` to delete a photo).
*   **Layouts:** Use `QHBoxLayout` and `QVBoxLayout` with proper spacing. Use `QScrollArea` for the thumbnail grid.

### File Operations & Safety
*   **Non-Destructive Deletion:** Deleting an image must use macOS native APIs or move the file to `~/.Trash/` rather than a destructive `os.remove()`, protecting the user from accidental data loss.
*   **Safe Moving:** When moving files from the SD card to Mac storage, always verify the write was successful before deleting the source file from the SD card.

### Color Scheme

- Accent Cyan: `#20d6d3` - accent lines, highlights
- Orange Primary: `#d68220` - links, key sections
- Salmon Secondary: `#d6755f` - submit buttons, important actions
- Dark Teal: `#385756` - main headings
- Brown Text: `#574938` - supporting text, labels

## 4. Coding Style Preferences
*   Use modern Python 3.10+ syntax (type hinting is mandatory for all functions).
*   Prefer object-oriented structure for PySide6 components (separate classes for widgets like `ImagePreviewWidget`, `MetadataPanel`).
*   Keep functions small, modular, and single-purpose.
*   Include docstrings explaining the inputs and outputs of complex metadata operations.
*   Use latest versions of libraries and idiomatic approaches as of today
*   Keep it simple - NEVER over-engineer, ALWAYS simplify, NO unnecessary defensive programming. No extra features - focus on simplicity.
*   Be concise. Keep README minimal. IMPORTANT: no emojis ever
*   When hitting issues, always identify root cause before trying a fix. Do not guess. Prove with evidence, then fix the root cause.

## 5. Phase 2 developments to take into account
*   The SD card will contain both native OM System file formats (ORF), as well as in-camera produced jpg versions of the same file.  Some of these are rendered using in-camera art effects.
*   Although these will have different file names, I wish to stack or group them as the equivalent image.  Possibly using exact time of exposure, or if there is some other unique identifier in exif
*   Ideally these (up to 10) images would be shown in thumbnail with the selected on in the full viewer
*   I would want to use a local model (ollama) to both generate a guideline title and description for the image, as well as suggested keywords to add.
*   If birds, flowers, animals or known locations are identified then these should also be suggested as keywords to add, including latin names for birds flowers

## Working documentation

All documents for planning and executing this project will be in the docs/ directory.
Please review the docs/PLAN.md document before proceeding.

