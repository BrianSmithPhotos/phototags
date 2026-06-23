import json

import pytest

from phototags.services import reverse_geocode_service as reverse_geocode_service_module
from phototags.services.reverse_geocode_service import ReverseGeocodeError, ReverseGeocodeService


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
    monkeypatch.setattr(reverse_geocode_service_module.request, "urlopen", fake_urlopen)


def test_lookup_location_extracts_city_county_state(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"address": {"city": "Portland", "county": "Multnomah County", "state": "Oregon"}}
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    service = ReverseGeocodeService()

    result = service.lookup_location(latitude=45.5, longitude=-122.6)

    assert result.city == "Portland"
    assert result.county == "Multnomah County"
    assert result.state == "Oregon"
    assert result.keyword_tokens() == ["Portland", "Multnomah County", "Oregon"]
    assert result.context_text() == "city=Portland; county=Multnomah County; state=Oregon"


def test_lookup_location_falls_back_through_city_field_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"address": {"hamlet": "Tiny Hamlet", "state_district": "Some District"}}
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    service = ReverseGeocodeService()

    result = service.lookup_location(latitude=45.5, longitude=-122.6)

    assert result.city == "Tiny Hamlet"
    assert result.county == "Some District"
    assert result.state == ""


def test_lookup_location_raises_when_address_has_no_usable_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"address": {"country": "USA"}}
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    service = ReverseGeocodeService()

    with pytest.raises(ReverseGeocodeError, match="no usable city/county/state"):
        service.lookup_location(latitude=45.5, longitude=-122.6)


def test_lookup_location_raises_when_response_has_no_address_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_urlopen(monkeypatch, lambda *a, **k: _FakeResponse({}))
    service = ReverseGeocodeService()

    with pytest.raises(ReverseGeocodeError, match="no usable city/county/state"):
        service.lookup_location(latitude=45.5, longitude=-122.6)


def test_lookup_location_raises_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*a: object, **k: object) -> None:
        raise reverse_geocode_service_module.error.URLError("network unreachable")

    _patch_urlopen(monkeypatch, _raise_url_error)
    service = ReverseGeocodeService()

    with pytest.raises(ReverseGeocodeError, match="Reverse geocode request failed"):
        service.lookup_location(latitude=45.5, longitude=-122.6)
