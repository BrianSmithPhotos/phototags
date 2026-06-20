"""Copy a fresher Timeline.json from Google Drive over the local export."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


DRIVE_TIMELINE_GLOB = "GoogleDrive-*/My Drive/AI/Gps/Timeline.json"


class TimelineSyncService:
    """Replaces the local Timeline.json with the Google Drive copy when it is newer."""

    def __init__(self, *, local_path: Path, drive_path: Path | None = None) -> None:
        self.local_path = local_path
        self.drive_path = drive_path if drive_path is not None else self._discover_drive_path()

    def sync_if_fresher(self) -> bool:
        """Copy the Drive Timeline.json over the local one if it is newer.

        Returns True if a copy happened.
        """
        if self.drive_path is None or not self.drive_path.is_file():
            return False
        if self.local_path.is_file() and self.local_path.stat().st_mtime >= self.drive_path.stat().st_mtime:
            return False
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.drive_path, self.local_path)
        return True

    @staticmethod
    def _discover_drive_path() -> Path | None:
        override = os.getenv("PHOTOTAGS_DRIVE_TIMELINE_PATH", "").strip()
        if override:
            return Path(override).expanduser()
        cloud_storage = Path.home() / "Library" / "CloudStorage"
        if not cloud_storage.is_dir():
            return None
        matches = sorted(cloud_storage.glob(DRIVE_TIMELINE_GLOB))
        return matches[0] if matches else None
