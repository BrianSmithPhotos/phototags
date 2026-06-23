import json
from pathlib import Path

from phototags.services.timeline_location_service import TimelineLocationError, TimelineLocationService

_SERVICE = TimelineLocationService()


def test_parse_lat_lon_parses_degree_symbol_and_comma() -> None:
    assert _SERVICE._parse_lat_lon("45.5°, -122.25°") == (45.5, -122.25)


def test_parse_lat_lon_parses_plain_comma_separated_values() -> None:
    assert _SERVICE._parse_lat_lon("45.5, -122.25") == (45.5, -122.25)


def test_parse_lat_lon_returns_none_for_malformed_text() -> None:
    assert _SERVICE._parse_lat_lon("not-a-coordinate") is None
    assert _SERVICE._parse_lat_lon("45.5") is None


def test_parse_exif_capture_timestamp_with_explicit_offset() -> None:
    ts = _SERVICE._parse_exif_capture_timestamp("2026:06:21 10:00:00+00:00")

    assert ts == 1782036000


def test_parse_exif_capture_timestamp_assumes_local_tz_when_missing() -> None:
    # No timezone info: result should be consistent with the local offset, not None.
    ts = _SERVICE._parse_exif_capture_timestamp("2026:06:21 10:00:00")

    assert ts is not None


def test_parse_exif_capture_timestamp_returns_none_for_blank_or_invalid() -> None:
    assert _SERVICE._parse_exif_capture_timestamp("") is None
    assert _SERVICE._parse_exif_capture_timestamp("not a timestamp") is None


def test_parse_iso_timestamp_handles_z_suffix() -> None:
    assert _SERVICE._parse_iso_timestamp("2026-06-21T10:00:00Z") == 1782036000


def test_parse_iso_timestamp_handles_explicit_offset() -> None:
    assert _SERVICE._parse_iso_timestamp("2026-06-21T10:00:00-07:00") == 1782061200


def test_parse_iso_timestamp_assumes_utc_when_offset_missing() -> None:
    assert _SERVICE._parse_iso_timestamp("2026-06-21T10:00:00") == 1782036000


def test_parse_iso_timestamp_returns_none_for_blank_or_invalid() -> None:
    assert _SERVICE._parse_iso_timestamp("") is None
    assert _SERVICE._parse_iso_timestamp("not a timestamp") is None


def test_build_record_key_is_deterministic_for_identical_inputs() -> None:
    key_a = _SERVICE._build_record_key(
        ts_utc=100, lat=45.5, lon=-122.25, altitude_m=10.0, source_type="GPS", accuracy_m=5.0
    )
    key_b = _SERVICE._build_record_key(
        ts_utc=100, lat=45.5, lon=-122.25, altitude_m=10.0, source_type="GPS", accuracy_m=5.0
    )

    assert key_a == key_b


def test_build_record_key_differs_when_any_field_differs() -> None:
    base = dict(ts_utc=100, lat=45.5, lon=-122.25, altitude_m=10.0, source_type="GPS", accuracy_m=5.0)

    base_key = _SERVICE._build_record_key(**base)
    altitude_none_key = _SERVICE._build_record_key(**{**base, "altitude_m": None})
    different_source_key = _SERVICE._build_record_key(**{**base, "source_type": "WIFI"})

    assert base_key != altitude_none_key
    assert base_key != different_source_key


def test_position_from_raw_signal_builds_position_with_altitude_and_accuracy() -> None:
    raw_position = {
        "LatLng": "45.5°, -122.25°",
        "timestamp": "2026-06-21T10:00:00Z",
        "altitudeMeters": 123.4,
        "accuracyMeters": 8,
        "source": "GPS",
    }

    position = _SERVICE._position_from_raw_signal(raw_position)

    assert position is not None
    assert position.lat == 45.5
    assert position.lon == -122.25
    assert position.altitude_m == 123.4
    assert position.accuracy_m == 8.0
    assert position.source_type == "GPS"


def test_position_from_raw_signal_returns_none_when_coordinate_missing() -> None:
    raw_position = {"timestamp": "2026-06-21T10:00:00Z"}

    assert _SERVICE._position_from_raw_signal(raw_position) is None


def test_position_from_raw_signal_returns_none_when_timestamp_unparseable() -> None:
    raw_position = {"LatLng": "45.5°, -122.25°", "timestamp": "not a timestamp"}

    assert _SERVICE._position_from_raw_signal(raw_position) is None


def test_position_from_raw_signal_defaults_source_to_unknown() -> None:
    raw_position = {"LatLng": "45.5°, -122.25°", "timestamp": "2026-06-21T10:00:00Z"}

    position = _SERVICE._position_from_raw_signal(raw_position)

    assert position is not None
    assert position.source_type == "UNKNOWN"
    assert position.altitude_m is None


def test_position_from_timeline_path_has_no_altitude_or_accuracy() -> None:
    point = {"point": "45.5°, -122.25°", "time": "2026-06-21T10:00:00Z"}

    position = _SERVICE._position_from_timeline_path(point)

    assert position is not None
    assert position.lat == 45.5
    assert position.lon == -122.25
    assert position.altitude_m is None
    assert position.accuracy_m is None
    assert position.source_type == "TIMELINE_PATH"


def test_position_from_timeline_path_returns_none_when_point_missing() -> None:
    point = {"time": "2026-06-21T10:00:00Z"}

    assert _SERVICE._position_from_timeline_path(point) is None


def test_parse_timeline_positions_reads_raw_signals_and_semantic_segments(tmp_path: Path) -> None:
    payload = {
        "rawSignals": [
            {
                "position": {
                    "LatLng": "45.5°, -122.25°",
                    "timestamp": "2026-06-21T10:00:00Z",
                    "source": "GPS",
                }
            }
        ],
        "semanticSegments": [
            {
                "timelinePath": [
                    {"point": "45.6°, -122.30°", "time": "2026-06-21T11:00:00Z"},
                ]
            }
        ],
    }
    timeline_path = tmp_path / "Timeline.json"
    timeline_path.write_text(json.dumps(payload), encoding="utf-8")

    positions = _SERVICE._parse_timeline_positions(timeline_path)

    sources = {position.source_type for position in positions}
    assert sources == {"GPS", "TIMELINE_PATH"}


def test_parse_timeline_positions_dedupes_identical_records(tmp_path: Path) -> None:
    raw_signal = {
        "position": {
            "LatLng": "45.5°, -122.25°",
            "timestamp": "2026-06-21T10:00:00Z",
            "source": "GPS",
        }
    }
    payload = {"rawSignals": [raw_signal, raw_signal]}
    timeline_path = tmp_path / "Timeline.json"
    timeline_path.write_text(json.dumps(payload), encoding="utf-8")

    positions = _SERVICE._parse_timeline_positions(timeline_path)

    assert len(positions) == 1


def test_parse_timeline_positions_raises_when_no_position_records(tmp_path: Path) -> None:
    timeline_path = tmp_path / "Timeline.json"
    timeline_path.write_text(json.dumps({"rawSignals": [], "semanticSegments": []}), encoding="utf-8")

    try:
        _SERVICE._parse_timeline_positions(timeline_path)
        assert False, "expected TimelineLocationError"
    except TimelineLocationError as exc:
        assert "no position records" in str(exc)


def test_parse_timeline_positions_raises_on_invalid_json(tmp_path: Path) -> None:
    timeline_path = tmp_path / "Timeline.json"
    timeline_path.write_text("not json", encoding="utf-8")

    try:
        _SERVICE._parse_timeline_positions(timeline_path)
        assert False, "expected TimelineLocationError"
    except TimelineLocationError as exc:
        assert "Failed to read timeline JSON" in str(exc)


def _build_service_with_timeline(tmp_path: Path, raw_positions: list[dict]) -> TimelineLocationService:
    timeline_path = tmp_path / "Timeline.json"
    timeline_path.write_text(json.dumps({"rawSignals": raw_positions}), encoding="utf-8")
    return TimelineLocationService(
        timeline_path=timeline_path,
        database_path=tmp_path / "cache.sqlite3",
    )


def _raw_position(*, lat: float, lon: float, timestamp: str, source: str = "GPS") -> dict:
    return {"position": {"LatLng": f"{lat}°, {lon}°", "timestamp": timestamp, "source": source}}


def test_suggest_for_capture_returns_nearest_match_within_window(tmp_path: Path) -> None:
    service = _build_service_with_timeline(
        tmp_path,
        [
            _raw_position(lat=45.5, lon=-122.25, timestamp="2026-06-21T10:00:00Z"),
            _raw_position(lat=45.6, lon=-122.30, timestamp="2026-06-21T10:20:00Z"),
        ],
    )

    suggestion = service.suggest_for_capture("2026:06:21 10:05:00+00:00")

    assert suggestion is not None
    assert suggestion.latitude == 45.5
    assert suggestion.longitude == -122.25
    assert suggestion.age_seconds == 300


def test_suggest_for_capture_returns_none_outside_match_window(tmp_path: Path) -> None:
    service = _build_service_with_timeline(
        tmp_path,
        [_raw_position(lat=45.5, lon=-122.25, timestamp="2026-06-21T10:00:00Z")],
    )

    suggestion = service.suggest_for_capture("2026:06:21 11:00:00+00:00")

    assert suggestion is None


def test_suggest_for_capture_returns_none_for_unparseable_captured_at(tmp_path: Path) -> None:
    service = _build_service_with_timeline(
        tmp_path,
        [_raw_position(lat=45.5, lon=-122.25, timestamp="2026-06-21T10:00:00Z")],
    )

    assert service.suggest_for_capture("not a timestamp") is None


def test_suggest_for_capture_prefers_gps_source_on_equal_age(tmp_path: Path) -> None:
    service = _build_service_with_timeline(
        tmp_path,
        [
            _raw_position(lat=45.5, lon=-122.25, timestamp="2026-06-21T10:00:00Z", source="WIFI"),
            _raw_position(lat=45.6, lon=-122.30, timestamp="2026-06-21T10:00:00Z", source="GPS"),
        ],
    )

    suggestion = service.suggest_for_capture("2026:06:21 10:00:00+00:00")

    assert suggestion is not None
    assert suggestion.source_type == "GPS"
    assert suggestion.latitude == 45.6


def test_suggest_for_capture_raises_when_timeline_file_missing(tmp_path: Path) -> None:
    service = TimelineLocationService(
        timeline_path=tmp_path / "missing.json",
        database_path=tmp_path / "cache.sqlite3",
    )

    try:
        service.suggest_for_capture("2026:06:21 10:00:00+00:00")
        assert False, "expected TimelineLocationError"
    except TimelineLocationError as exc:
        assert "Timeline file not found" in str(exc)
