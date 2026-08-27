"""Proveedor de geocodificación con Google Maps (requiere API key con facturación habilitada).

Alternativa de pago a `src/geocoding/nominatim_client.py`. La lógica de negocio compartida
(RF-07 a RF-10) vive en `src/geocoding/service.py`.
"""
from __future__ import annotations

import googlemaps
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.geocoding.base import GeocodingProvider


class GeocodingClient(GeocodingProvider):
    def __init__(self) -> None:
        if not settings.google_maps_api_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY no está configurada. Define la variable de entorno en tu archivo .env."
            )
        self._client = googlemaps.Client(key=settings.google_maps_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def geocode(self, address: str) -> tuple[float, float] | None:
        results = self._client.geocode(address)
        if not results:
            return None
        location = results[0]["geometry"]["location"]
        return location["lat"], location["lng"]
