"""Contrato del proveedor de geocodificación (RNF-09: módulos desacoplados, RNF-10: interoperabilidad).

Permite intercambiar el proveedor (Nominatim/OSM, Google Maps, etc.) sin tocar el resto del flujo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ResultadoGeocodificacion:
    """Coordenadas + qué tan precisa es la coincidencia.

    `nota_precision` es None cuando el punto corresponde a la dirección buscada con la máxima
    precisión que el proveedor puede dar; si no, describe el nivel de aproximación (calle,
    barrio, municipio) para que el operador sepa qué revisar.
    """

    lat: float
    lon: float
    nota_precision: str | None = None

    @property
    def coords(self) -> tuple[float, float]:
        return self.lat, self.lon


class GeocodingProvider(ABC):
    @abstractmethod
    def geocode(self, address: str) -> tuple[float, float] | None:
        """Devuelve (lat, lng) o None si la dirección no pudo geolocalizarse (RF-07, RF-08)."""
        raise NotImplementedError

    def geocode_detallado(
        self,
        address: str,
        *,
        via: str | None = None,
        barrio: str | None = None,
        municipio: str | None = None,
    ) -> ResultadoGeocodificacion | None:
        """Geocodifica usando los componentes estructurados (vía/barrio/municipio) si el
        proveedor sabe aprovecharlos para elegir mejor entre varios candidatos.

        Implementación por defecto: delega en `geocode()` y no añade nota de precisión.
        """
        coords = self.geocode(address)
        if coords is None:
            return None
        return ResultadoGeocodificacion(coords[0], coords[1], None)
