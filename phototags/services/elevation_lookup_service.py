"""Elevation lookup helpers for filling missing GPS altitude."""

from __future__ import annotations

import json
from urllib import error, parse, request


USGS_EPQS_URL = "https://epqs.nationalmap.gov/v1/json"


class ElevationLookupError(RuntimeError):
    """Raised when elevation lookup fails."""


class ElevationLookupService:
    """Lookup elevation in meters for one coordinate pair."""

    def lookup_altitude_m(self, *, latitude: float, longitude: float) -> float:
        """Return altitude in meters from USGS EPQS for one lat/lon."""
        query = parse.urlencode(
            {
                "x": f"{longitude:.7f}",
                "y": f"{latitude:.7f}",
                "units": "Meters",
                "wkid": 4326,
                "includeDate": "false",
            }
        )
        url = f"{USGS_EPQS_URL}?{query}"
        try:
            with request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ElevationLookupError(f"Elevation lookup request failed: {exc}") from exc

        value = self._extract_value(payload)
        if value is None:
            raise ElevationLookupError("Elevation lookup returned no usable altitude")
        return value

    def _extract_value(self, payload: object) -> float | None:
        """Extract numeric elevation value from known EPQS response formats."""
        if not isinstance(payload, dict):
            return None

        direct = self._to_float(payload.get("value"))
        if direct is not None:
            return direct

        if "USGS_Elevation_Point_Query_Service" in payload:
            nested = payload.get("USGS_Elevation_Point_Query_Service")
            if isinstance(nested, dict):
                elevation_query = nested.get("Elevation_Query")
                if isinstance(elevation_query, dict):
                    return self._to_float(elevation_query.get("Elevation"))

        if "elevation" in payload:
            return self._to_float(payload.get("elevation"))

        return None

    def _to_float(self, value: object) -> float | None:
        """Convert scalar value to float if possible."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
