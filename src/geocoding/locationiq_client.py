"""Proveedor de geocodificación: LocationIQ (https://locationiq.com).

API compatible con Nominatim, alojada por Unwired Labs, con nivel gratuito generoso (~5,000
solicitudes/día) sin pedir tarjeta de crédito — solo requiere registrarse y obtener una API key.

ADVERTENCIA (hallazgo real, ver README): en pruebas con 20 direcciones del Atlántico,
LocationIQ reportó 100% de éxito sin marcar ninguna como aproximada, pero varias coordenadas
resultaron a decenas de kilómetros del municipio correcto (un caso a 44 km, en Sabanalarga en
vez de Barranquilla) — su interpolación de numeración de placa no respeta de forma confiable
la ciudad indicada en la consulta. NO se recomienda como proveedor por defecto sin verificación
cruzada adicional; Nominatim + la cascada de reintentos de `service.py` resultó más confiable.
"""
from __future__ import annotations

import logging
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.geocoding.base import GeocodingProvider

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 0.5  # nivel gratuito: ~2 solicitudes/segundo


class LocationIQGeocodingProvider(GeocodingProvider):
    def __init__(self) -> None:
        if not settings.locationiq_api_key:
            raise RuntimeError(
                "LOCATIONIQ_API_KEY no está configurada. Obtén una key gratuita en "
                "https://locationiq.com (no pide tarjeta) y agrégala a tu archivo .env."
            )
        self._last_request_ts = 0.0

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def geocode(self, address: str) -> tuple[float, float] | None:
        self._respect_rate_limit()
        params = {
            "key": settings.locationiq_api_key,
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": settings.nominatim_countrycodes,
            "viewbox": settings.nominatim_viewbox,
            "bounded": "1" if settings.nominatim_bounded else "0",
        }
        response = requests.get(settings.locationiq_url, params=params, timeout=10)
        self._last_request_ts = time.monotonic()

        if response.status_code == 404:  # LocationIQ devuelve 404 cuando no hay resultados
            return None
        response.raise_for_status()

        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
