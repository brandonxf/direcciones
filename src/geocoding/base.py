"""Contrato del proveedor de geocodificación (RNF-09: módulos desacoplados, RNF-10: interoperabilidad).

Permite intercambiar el proveedor (Nominatim/OSM, Google Maps, etc.) sin tocar el resto del flujo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class GeocodingProvider(ABC):
    @abstractmethod
    def geocode(self, address: str) -> tuple[float, float] | None:
        """Devuelve (lat, lng) o None si la dirección no pudo geolocalizarse (RF-07, RF-08)."""
        raise NotImplementedError
