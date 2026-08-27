"""Proveedor de geocodificación gratuito: Nominatim (OpenStreetMap), sin API key ni tarjeta.

Política de uso justo de Nominatim (https://operations.osmfoundation.org/policies/nominatim/):
máx. 1 solicitud/segundo y un User-Agent que identifique la aplicación. Este cliente respeta
ambas condiciones. Para volumen alto o uso en producción, la recomendación oficial es
autohospedar Nominatim o usar un proveedor comercial (p. ej. Google Maps, ya soportado en
`src/geocoding/google_maps_client.py`).
"""
from __future__ import annotations

import logging
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.geocoding.base import GeocodingProvider

logger = logging.getLogger(__name__)

USER_AGENT = "SistemaOptimizacionRutas/1.0 (uso educativo/desarrollo)"
MIN_INTERVAL_SECONDS = 1.0


class NominatimGeocodingProvider(GeocodingProvider):
    def __init__(self) -> None:
        self._last_request_ts = 0.0

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def geocode(self, address: str) -> tuple[float, float] | None:
        self._respect_rate_limit()
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": settings.nominatim_countrycodes,
            "viewbox": settings.nominatim_viewbox,
            "bounded": "1" if settings.nominatim_bounded else "0",
        }
        response = requests.get(
            settings.nominatim_url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        self._last_request_ts = time.monotonic()
        response.raise_for_status()

        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
