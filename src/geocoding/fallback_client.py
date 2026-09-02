"""Proveedor de geocodificación con conmutación automática (failover).

Si el proveedor activo (p. ej. Nominatim) falla por límite de tasa (HTTP 429) o por un error
de servicio, el sistema cambia automáticamente al siguiente proveedor disponible en la lista
(p. ej. LocationIQ, Google Maps), sin intervención manual. De esta forma la geocodificación
sigue funcionando aunque un proveedor gratuito esté saturado.

La conmutación se decide por fallos consecutivos de tipo "servicio" (no por "dirección no
encontrada", que es un resultado válido y no debe cambiar de proveedor).
"""
from __future__ import annotations

import logging

import requests

from src.geocoding.base import GeocodingProvider, ResultadoGeocodificacion
from src.geocoding.nominatim_client import RateLimitError

logger = logging.getLogger(__name__)

# Fallos de servicio consecutivos antes de conmutar al siguiente proveedor.
UMBRAL_CONMUTACION = 2

# Máximo de intentos totales (entre todos los proveedores) por dirección, para evitar un
# bucle infinito si todos los proveedores fallan.
MAX_INTENTOS_TOTALES = 8


class FallbackGeocodingProvider(GeocodingProvider):
    def __init__(self, providers: list[GeocodingProvider], names: list[str]) -> None:
        if not providers:
            raise ValueError("FallbackGeocodingProvider necesita al menos un proveedor.")
        if len(providers) != len(names):
            raise ValueError("providers y names deben tener la misma longitud.")
        self._providers = list(providers)
        self._names = list(names)
        self._active_index = 0
        self._fallos_consecutivos = 0

    @property
    def active_name(self) -> str:
        return self._names[self._active_index]

    def _es_error_servicio(self, exc: Exception) -> bool:
        """Determina si la excepción es un fallo del servicio (debe conmutar) o una
        dirección simplemente no encontrada (no debe conmutar)."""
        if isinstance(exc, RateLimitError):
            return True
        # HTTPError con status 429 (límite de tasa) o 5xx (error del servidor)
        if isinstance(exc, requests.exceptions.HTTPError):
            code = exc.response.status_code if exc.response is not None else None
            return code in {429, 500, 502, 503, 504}
        # Timeout u otros errores de red
        if isinstance(exc, requests.exceptions.Timeout):
            return True
        if isinstance(exc, requests.exceptions.RequestException):
            return True
        return False

    def geocode(self, address: str) -> tuple[float, float] | None:
        return self._ejecutar(lambda p: p.geocode(address), address, MAX_INTENTOS_TOTALES)

    def geocode_detallado(
        self,
        address: str,
        *,
        via: str | None = None,
        barrio: str | None = None,
        municipio: str | None = None,
    ) -> ResultadoGeocodificacion | None:
        return self._ejecutar(
            lambda p: p.geocode_detallado(address, via=via, barrio=barrio, municipio=municipio),
            address,
            MAX_INTENTOS_TOTALES,
        )

    def _ejecutar(self, operacion, address: str, _intentos_restantes: int):
        if _intentos_restantes <= 0:
            logger.error(
                "Todos los proveedores de geocodificación fallaron para '%s'. "
                "Se devuelve sin resultado.", address,
            )
            return None

        proveedor = self._providers[self._active_index]
        nombre = self._names[self._active_index]
        try:
            resultado = operacion(proveedor)
        except Exception as exc:  # noqa: BLE001 - capturamos cualquier fallo para decidir failover
            self._fallos_consecutivos += 1
            if self._es_error_servicio(exc) and self._fallos_consecutivos >= UMBRAL_CONMUTACION:
                self._cambiar_siguiente(exc)
            else:
                logger.warning(
                    "Proveedor '%s' falló para '%s': %s (fallos consecutivos: %d)",
                    nombre, address, exc, self._fallos_consecutivos,
                )
            # Reintentamos (con el proveedor ahora activo o el mismo) hasta agotar intentos
            return self._ejecutar(operacion, address, _intentos_restantes - 1)
        else:
            # Éxito (resultado None = dirección no encontrada, es válido): reinicia el contador
            self._fallos_consecutivos = 0
            return resultado

    def _cambiar_siguiente(self, exc: Exception) -> None:
        viejo = self._names[self._active_index]
        self._active_index = (self._active_index + 1) % len(self._providers)
        nuevo = self._names[self._active_index]
        self._fallos_consecutivos = 0
        logger.warning(
            "Conmutando geocodificación de '%s' a '%s' por fallo de servicio: %s",
            viejo, nuevo, exc,
        )
