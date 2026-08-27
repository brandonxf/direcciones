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

from src.config import settings
from src.geocoding.base import GeocodingProvider

logger = logging.getLogger(__name__)

USER_AGENT = "SistemaOptimizacionRutas/1.0 (uso educativo/desarrollo)"
MIN_INTERVAL_SECONDS = 1.1
FALLBACK_RATE_LIMIT_SECONDS = 5.0


class RateLimitError(Exception):
    """Servicio de geocodificación limitando temporalmente la IP del usuario (HTTP 429)."""


class NominatimGeocodingProvider(GeocodingProvider):
    def __init__(self) -> None:
        self._last_request_ts = 0.0

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)

    def geocode(self, address: str) -> tuple[float, float] | None:
        # Ante un 429 (límite de tasa) no reintentamos aquí: si la IP está bloqueada, volver a
        # llamar solo satura más el servicio. Lanzamos RateLimitError para que el proveedor de
        # conmutación automática (fallback_client) cambie al respaldo sin intervención manual.
        # Solo se reintenta internamente ante timeouts puntuales (transitorios).
        self._respect_rate_limit()
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": settings.nominatim_countrycodes,
            "viewbox": settings.nominatim_viewbox,
            "bounded": "1" if settings.nominatim_bounded else "0",
        }
        for intento in range(3):
            try:
                response = requests.get(
                    settings.nominatim_url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                self._last_request_ts = time.monotonic()
                if response.status_code == 429:
                    raise RateLimitError(
                        "El servicio de geocodificación (Nominatim/OSM) está limitando esta IP "
                        "temporalmente por exceso de solicitudes. Se conmutará automáticamente "
                        "al proveedor de respaldo."
                    )
                response.raise_for_status()
                break
            except requests.exceptions.Timeout:
                if intento == 2:
                    raise
                time.sleep(2.0)

        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])


def _parse_retry_after(response) -> float:
    """Lee el header Retry-After (segundos o fecha RFC 1123) o usa un valor por defecto."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(float(raw), FALLBACK_RATE_LIMIT_SECONDS)
        except ValueError:
            # Puede venir una fecha RFC1123
            try:
                from email.utils import parsedate_to_datetime
                import datetime as _dt
                delta = (parsedate_to_datetime(raw).replace(tzinfo=_dt.timezone.utc)
                         - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
                return max(delta, FALLBACK_RATE_LIMIT_SECONDS)
            except Exception:
                return FALLBACK_RATE_LIMIT_SECONDS
    return FALLBACK_RATE_LIMIT_SECONDS
