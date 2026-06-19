"""Timeline-backed GPS enrichment with local SQLite caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading


DEFAULT_MAX_MATCH_SECONDS = 30 * 60


@dataclass(slots=True)
class GpsSuggestion:
    """Nearest timeline position match for one photo capture timestamp."""

    latitude: float
    longitude: float
    altitude_m: float | None
    source_type: str
    accuracy_m: float | None
    matched_ts_utc: int
    age_seconds: int


@dataclass(slots=True)
class _TimelinePosition:
    """Normalized timeline position row used for SQLite upsert."""

    record_key: str
    ts_utc: int
    lat: float
    lon: float
    altitude_m: float | None
    accuracy_m: float | None
    source_type: str


class TimelineLocationError(RuntimeError):
    """Raised when timeline enrichment cannot run."""


class TimelineLocationService:
    """Import timeline exports into SQLite and provide nearest-time GPS matches."""

    def __init__(
        self,
        *,
        timeline_path: Path | None = None,
        database_path: Path | None = None,
        max_match_seconds: int = DEFAULT_MAX_MATCH_SECONDS,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        timeline_override = os.getenv("PHOTOTAGS_TIMELINE_PATH", "").strip()
        default_timeline = Path(timeline_override).expanduser() if timeline_override else (project_root / "gps" / "Timeline.json")
        default_db_path = Path.home() / "Library" / "Application Support" / "phototags" / "timeline_cache.sqlite3"
        self.timeline_path = timeline_path or default_timeline
        self.database_path = database_path or default_db_path
        self.max_match_seconds = max_match_seconds
        self._lock = threading.Lock()
        self._loaded_signature: tuple[str, int, int] | None = None

    def suggest_for_capture(self, captured_at: str) -> GpsSuggestion | None:
        """Return nearest timeline GPS sample for an EXIF capture timestamp.

        The match window is strict: no sample outside `max_match_seconds` is returned.
        """
        capture_ts = self._parse_exif_capture_timestamp(captured_at)
        if capture_ts is None:
            return None

        self._ensure_cache_current()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ts_utc,
                    lat,
                    lon,
                    altitude_m,
                    source_type,
                    accuracy_m,
                    ABS(ts_utc - ?) AS age_seconds
                FROM timeline_positions
                WHERE ts_utc BETWEEN ? AND ?
                ORDER BY
                    age_seconds ASC,
                    CASE source_type
                        WHEN 'GPS' THEN 0
                        WHEN 'WIFI' THEN 1
                        WHEN 'WIFI_ONLY' THEN 2
                        WHEN 'TIMELINE_PATH' THEN 3
                        ELSE 4
                    END ASC,
                    CASE WHEN accuracy_m IS NULL THEN 1 ELSE 0 END ASC,
                    accuracy_m ASC
                LIMIT 1
                """,
                (
                    capture_ts,
                    capture_ts - self.max_match_seconds,
                    capture_ts + self.max_match_seconds,
                ),
            ).fetchone()

        if row is None:
            return None
        return GpsSuggestion(
            latitude=float(row["lat"]),
            longitude=float(row["lon"]),
            altitude_m=(float(row["altitude_m"]) if row["altitude_m"] is not None else None),
            source_type=str(row["source_type"]),
            accuracy_m=(float(row["accuracy_m"]) if row["accuracy_m"] is not None else None),
            matched_ts_utc=int(row["ts_utc"]),
            age_seconds=int(row["age_seconds"]),
        )

    def _ensure_cache_current(self) -> None:
        """Ensure local SQLite cache is initialized and imported for current timeline file."""
        if not self.timeline_path.exists():
            raise TimelineLocationError(f"Timeline file not found: {self.timeline_path}")

        stat = self.timeline_path.stat()
        source_path = str(self.timeline_path.resolve())
        signature = (source_path, int(stat.st_size), int(stat.st_mtime_ns))
        if signature == self._loaded_signature:
            return

        with self._lock:
            if signature == self._loaded_signature:
                return
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                self._ensure_schema(conn)
                if not self._is_import_needed(
                    conn=conn,
                    source_path=source_path,
                    source_size=signature[1],
                    source_mtime_ns=signature[2],
                ):
                    self._loaded_signature = signature
                    return

                source_sha256 = self._sha256(self.timeline_path)
                import_id = self._insert_import_event(
                    conn=conn,
                    source_path=source_path,
                    source_size=signature[1],
                    source_mtime_ns=signature[2],
                    source_sha256=source_sha256,
                )
                positions = self._parse_timeline_positions(self.timeline_path)
                conn.executemany(
                    """
                    INSERT INTO timeline_positions(
                        record_key,
                        ts_utc,
                        lat,
                        lon,
                        altitude_m,
                        accuracy_m,
                        source_type,
                        import_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_key) DO UPDATE SET
                        ts_utc = excluded.ts_utc,
                        lat = excluded.lat,
                        lon = excluded.lon,
                        altitude_m = excluded.altitude_m,
                        accuracy_m = excluded.accuracy_m,
                        source_type = excluded.source_type,
                        import_id = excluded.import_id
                    """,
                    [
                        (
                            position.record_key,
                            position.ts_utc,
                            position.lat,
                            position.lon,
                            position.altitude_m,
                            position.accuracy_m,
                            position.source_type,
                            import_id,
                        )
                        for position in positions
                    ],
                )
            self._loaded_signature = signature

    def _connect(self) -> sqlite3.Connection:
        """Open configured SQLite database with row access by column name."""
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create cache tables/indexes if they do not already exist."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timeline_imports (
                import_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL,
                source_size INTEGER NOT NULL,
                source_mtime_ns INTEGER NOT NULL,
                source_sha256 TEXT NOT NULL,
                imported_at_utc TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timeline_positions (
                record_key TEXT PRIMARY KEY,
                ts_utc INTEGER NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                altitude_m REAL,
                accuracy_m REAL,
                source_type TEXT NOT NULL,
                import_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timeline_positions_ts_utc
            ON timeline_positions(ts_utc)
            """
        )

    def _is_import_needed(
        self,
        *,
        conn: sqlite3.Connection,
        source_path: str,
        source_size: int,
        source_mtime_ns: int,
    ) -> bool:
        """Return True when timeline file signature has not been imported yet."""
        row = conn.execute(
            """
            SELECT import_id
            FROM timeline_imports
            WHERE source_path = ?
              AND source_size = ?
              AND source_mtime_ns = ?
            ORDER BY import_id DESC
            LIMIT 1
            """,
            (source_path, source_size, source_mtime_ns),
        ).fetchone()
        return row is None

    def _insert_import_event(
        self,
        *,
        conn: sqlite3.Connection,
        source_path: str,
        source_size: int,
        source_mtime_ns: int,
        source_sha256: str,
    ) -> int:
        """Insert one timeline import row and return the generated import id."""
        cursor = conn.execute(
            """
            INSERT INTO timeline_imports(
                source_path,
                source_size,
                source_mtime_ns,
                source_sha256,
                imported_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_path,
                source_size,
                source_mtime_ns,
                source_sha256,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)

    def _parse_timeline_positions(self, timeline_path: Path) -> list[_TimelinePosition]:
        """Parse raw timeline JSON into normalized position records.

        Returns both `rawSignals.position` records and `semanticSegments.timelinePath`
        points. The `rawSignals` set is preferred at query time because those records
        carry accuracy/source and often carry altitude.
        """
        try:
            payload = json.loads(timeline_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TimelineLocationError(f"Failed to read timeline JSON: {exc}") from exc

        positions: list[_TimelinePosition] = []
        seen: set[str] = set()

        raw_signals = payload.get("rawSignals", [])
        if isinstance(raw_signals, list):
            for raw_signal in raw_signals:
                if not isinstance(raw_signal, dict):
                    continue
                position = raw_signal.get("position")
                if not isinstance(position, dict):
                    continue
                item = self._position_from_raw_signal(position)
                if item is None or item.record_key in seen:
                    continue
                seen.add(item.record_key)
                positions.append(item)

        semantic_segments = payload.get("semanticSegments", [])
        if isinstance(semantic_segments, list):
            for segment in semantic_segments:
                if not isinstance(segment, dict):
                    continue
                timeline_path_points = segment.get("timelinePath")
                if not isinstance(timeline_path_points, list):
                    continue
                for point in timeline_path_points:
                    if not isinstance(point, dict):
                        continue
                    item = self._position_from_timeline_path(point)
                    if item is None or item.record_key in seen:
                        continue
                    seen.add(item.record_key)
                    positions.append(item)

        if not positions:
            raise TimelineLocationError("Timeline file has no position records")
        return positions

    def _position_from_raw_signal(self, raw_position: dict[str, object]) -> _TimelinePosition | None:
        """Build normalized position from one `rawSignals.position` entry."""
        coordinate_text = self._to_text(raw_position.get("LatLng"))
        timestamp_text = self._to_text(raw_position.get("timestamp"))
        if not coordinate_text or not timestamp_text:
            return None

        lat_lon = self._parse_lat_lon(coordinate_text)
        ts_utc = self._parse_iso_timestamp(timestamp_text)
        if lat_lon is None or ts_utc is None:
            return None

        altitude_m = self._optional_float(raw_position.get("altitudeMeters"))
        accuracy_m = self._optional_float(raw_position.get("accuracyMeters"))
        source_type = self._to_text(raw_position.get("source")).strip() or "UNKNOWN"
        key = self._build_record_key(
            ts_utc=ts_utc,
            lat=lat_lon[0],
            lon=lat_lon[1],
            altitude_m=altitude_m,
            source_type=source_type,
            accuracy_m=accuracy_m,
        )
        return _TimelinePosition(
            record_key=key,
            ts_utc=ts_utc,
            lat=lat_lon[0],
            lon=lat_lon[1],
            altitude_m=altitude_m,
            accuracy_m=accuracy_m,
            source_type=source_type,
        )

    def _position_from_timeline_path(self, point: dict[str, object]) -> _TimelinePosition | None:
        """Build normalized position from one semantic `timelinePath` point."""
        coordinate_text = self._to_text(point.get("point"))
        timestamp_text = self._to_text(point.get("time"))
        if not coordinate_text or not timestamp_text:
            return None
        lat_lon = self._parse_lat_lon(coordinate_text)
        ts_utc = self._parse_iso_timestamp(timestamp_text)
        if lat_lon is None or ts_utc is None:
            return None

        key = self._build_record_key(
            ts_utc=ts_utc,
            lat=lat_lon[0],
            lon=lat_lon[1],
            altitude_m=None,
            source_type="TIMELINE_PATH",
            accuracy_m=None,
        )
        return _TimelinePosition(
            record_key=key,
            ts_utc=ts_utc,
            lat=lat_lon[0],
            lon=lat_lon[1],
            altitude_m=None,
            accuracy_m=None,
            source_type="TIMELINE_PATH",
        )

    def _build_record_key(
        self,
        *,
        ts_utc: int,
        lat: float,
        lon: float,
        altitude_m: float | None,
        source_type: str,
        accuracy_m: float | None,
    ) -> str:
        """Build deterministic hash key for one normalized position record."""
        raw_key = (
            f"{ts_utc}|{lat:.7f}|{lon:.7f}|"
            f"{'' if altitude_m is None else f'{altitude_m:.3f}'}|"
            f"{source_type}|"
            f"{'' if accuracy_m is None else f'{accuracy_m:.3f}'}"
        )
        return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()

    def _parse_exif_capture_timestamp(self, captured_at: str) -> int | None:
        """Parse EXIF capture timestamp into UTC epoch seconds.

        EXIF timestamps often omit timezone. When offset is missing, local macOS
        timezone is assumed so matching aligns with timeline export local offsets.
        """
        text = captured_at.strip()
        if not text:
            return None

        for fmt in ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                local_tz = datetime.now().astimezone().tzinfo
                parsed = parsed.replace(tzinfo=local_tz)
            return int(parsed.timestamp())
        return None

    def _parse_iso_timestamp(self, timestamp_text: str) -> int | None:
        """Parse Timeline JSON timestamp text into UTC epoch seconds."""
        text = timestamp_text.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())

    def _parse_lat_lon(self, coordinate_text: str) -> tuple[float, float] | None:
        """Parse coordinate string in `<lat>°, <lon>°` form into float tuple."""
        cleaned = coordinate_text.replace("°", "").strip()
        parts = [part.strip() for part in cleaned.split(",")]
        if len(parts) != 2:
            return None
        try:
            lat = float(parts[0])
            lon = float(parts[1])
        except ValueError:
            return None
        return lat, lon

    def _optional_float(self, value: object) -> float | None:
        """Convert value to float when possible, else return None."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_text(self, value: object) -> str:
        """Return text representation for known scalar values."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        return ""

    def _sha256(self, path: Path) -> str:
        """Return SHA-256 digest for one file."""
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
        except OSError as exc:
            raise TimelineLocationError(f"Unable to hash timeline file: {exc}") from exc
        return digest.hexdigest()
