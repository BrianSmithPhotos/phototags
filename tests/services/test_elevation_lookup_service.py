import json

import pytest

from phototags.services import elevation_lookup_service as elevation_lookup_service_module
from phototags.services.elevation_lookup_service import ElevationLookupError, ElevationLookupService


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, fake_urlopen) -> None:
    monkeypatch.setattr(elevation_lookup_service_module.request, "urlopen", fake_urlopen)


def test_lookup_altitude_m_reads_direct_value_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse({"value": "123.4"}))
    service = ElevationLookupService()

    assert service.lookup_altitude_m(latitude=45.5, longitude=-122.25) == 123.4


def test_lookup_altitude_m_reads_nested_usgs_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "USGS_Elevation_Point_Query_Service": {
            "Elevation_Query": {"Elevation": 250.7},
        }
    }
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    service = ElevationLookupService()

    assert service.lookup_altitude_m(latitude=45.5, longitude=-122.25) == 250.7


def test_lookup_altitude_m_raises_when_no_usable_value_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse({"unrelated": "field"}))
    service = ElevationLookupService()

    with pytest.raises(ElevationLookupError, match="no usable altitude"):
        service.lookup_altitude_m(latitude=45.5, longitude=-122.25)


def test_lookup_altitude_m_raises_when_response_is_not_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadResponse:
        def read(self) -> bytes:
            return b"not json"

        def __enter__(self) -> "_BadResponse":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    _patch_urlopen(monkeypatch, lambda *a, **k: _BadResponse())
    service = ElevationLookupService()

    with pytest.raises(ElevationLookupError, match="Elevation lookup request failed"):
        service.lookup_altitude_m(latitude=45.5, longitude=-122.25)


def test_lookup_altitude_m_caches_repeated_lookups_at_the_same_coordinate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def fake_urlopen(*a: object, **k: object) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        return _FakeResponse({"value": "100.0"})

    _patch_urlopen(monkeypatch, fake_urlopen)
    service = ElevationLookupService()

    first = service.lookup_altitude_m(latitude=45.5, longitude=-122.25)
    # Coordinates within the cache's rounding precision should hit the cache.
    second = service.lookup_altitude_m(latitude=45.50001, longitude=-122.25001)

    assert first == second == 100.0
    assert call_count == 1


def test_lookup_altitude_m_does_not_cache_a_failed_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def fake_urlopen(*a: object, **k: object) -> _FakeResponse:
        nonlocal call_count
        call_count += 1
        raise elevation_lookup_service_module.error.URLError("network unreachable")

    _patch_urlopen(monkeypatch, fake_urlopen)
    service = ElevationLookupService()

    for _ in range(2):
        with pytest.raises(ElevationLookupError):
            service.lookup_altitude_m(latitude=45.5, longitude=-122.25)

    assert call_count == 2


def test_lookup_altitude_m_raises_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*a: object, **k: object) -> None:
        raise elevation_lookup_service_module.error.URLError("network unreachable")

    _patch_urlopen(monkeypatch, _raise_url_error)
    service = ElevationLookupService()

    with pytest.raises(ElevationLookupError, match="Elevation lookup request failed"):
        service.lookup_altitude_m(latitude=45.5, longitude=-122.25)
