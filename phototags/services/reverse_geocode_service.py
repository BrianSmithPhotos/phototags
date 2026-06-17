"""Reverse geocoding helpers for deriving city/county/state from GPS."""

from __future__ import annotations

from dataclasses import dataclass
import json
from urllib import error, parse, request


NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "phototags/0.1 (local desktop photo workflow)"


@dataclass(slots=True)
class ReverseGeocodeResult:
    """Normalized location fields extracted from reverse geocode response."""

    city: str
    county: str
    state: str

    def keyword_tokens(self) -> list[str]:
        """Return non-empty location components for keyword insertion."""
        values = [self.city.strip(), self.county.strip(), self.state.strip()]
        return [value for value in values if value]

    def context_text(self) -> str:
        """Return compact text context for AI prompt enrichment."""
        parts: list[str] = []
        if self.city:
            parts.append(f"city={self.city}")
        if self.county:
            parts.append(f"county={self.county}")
        if self.state:
            parts.append(f"state={self.state}")
        return "; ".join(parts)


class ReverseGeocodeError(RuntimeError):
    """Raised when reverse geocoding fails."""


class ReverseGeocodeService:
    """Lookup city/county/state from one latitude/longitude pair."""

    def lookup_location(self, *, latitude: float, longitude: float) -> ReverseGeocodeResult:
        """Return reverse geocoded city/county/state fields for coordinates."""
        query = parse.urlencode(
            {
                "lat": f"{latitude:.7f}",
                "lon": f"{longitude:.7f}",
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 10,
            }
        )
        url = f"{NOMINATIM_REVERSE_URL}?{query}"
        geocode_request = request.Request(
            url,
            headers={
                "User-Agent": NOMINATIM_USER_AGENT,
                "Accept-Language": "en",
            },
            method="GET",
        )
        try:
            with request.urlopen(geocode_request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReverseGeocodeError(f"Reverse geocode request failed: {exc}") from exc

        result = self._extract_result(payload)
        if result is None:
            raise ReverseGeocodeError("Reverse geocode returned no usable city/county/state fields")
        return result

    def _extract_result(self, payload: object) -> ReverseGeocodeResult | None:
        """Extract city/county/state values from known Nominatim response shape."""
        if not isinstance(payload, dict):
            return None
        address = payload.get("address")
        if not isinstance(address, dict):
            return None

        city = self._first_non_empty(
            address,
            (
                "city",
                "town",
                "village",
                "hamlet",
                "municipality",
                "locality",
                "suburb",
            ),
        )
        county = self._first_non_empty(address, ("county", "state_district"))
        state = self._first_non_empty(address, ("state", "region"))

        if not (city or county or state):
            return None
        return ReverseGeocodeResult(city=city, county=county, state=state)

    def _first_non_empty(self, payload: dict[str, object], keys: tuple[str, ...]) -> str:
        """Return first non-empty text value from dictionary keys."""
        for key in keys:
            value = payload.get(key)
            text = self._to_text(value).strip()
            if text:
                return text
        return ""

    def _to_text(self, value: object) -> str:
        """Convert scalar value to text for downstream normalization."""
        if value is None:
            return ""
        return str(value)
