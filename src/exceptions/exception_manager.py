"""Módulo de Excepciones (sección 7 y 10 del documento técnico) — RF-09, RF-10.

Centraliza los pasajeros cuya dirección no pudo geolocalizarse, para que el operador
logístico los revise y corrija manualmente sin necesidad de reprocesar el archivo completo.
"""
from __future__ import annotations

from src.geocoding.base import GeocodingProvider
from src.geocoding.service import retry_single_address
from src.models.schemas import EstadoGeocodificacion, Pasajero


def list_exceptions(passengers: list[Pasajero]) -> list[Pasajero]:
    """Listado de excepciones visible para el operador logístico (RF-09)."""
    return [p for p in passengers if p.estado == EstadoGeocodificacion.EXCEPCION]


def resolve_exception(pasajero: Pasajero, corrected_address: str, provider: GeocodingProvider) -> Pasajero:
    """Corrige manualmente una dirección y reintenta su geocodificación (RF-10)."""
    return retry_single_address(pasajero, corrected_address, provider)
