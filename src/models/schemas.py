"""Entidades del dominio, alineadas con la sección 6 (Actores) y 7 (Arquitectura) del documento técnico."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EstadoGeocodificacion(str, Enum):
    PENDIENTE = "pendiente"
    NORMALIZADA = "normalizada"
    GEOCODIFICADA = "geocodificada"
    EXCEPCION = "excepcion"  # RF-09: no logró ser geolocalizada


class SentidoRuta(str, Enum):
    ENTRADA = "entrada"  # recogida
    SALIDA = "salida"  # distribución


@dataclass
class Pasajero:
    """Entidad de datos (sección 6). No interactúa con el sistema, pero estructura la información."""

    identificador: str
    nombre: str
    direccion_original: str
    turno: Optional[str] = None
    barrio: Optional[str] = None  # ayuda a distinguir calles con el mismo nombre en distintos sectores

    direccion_normalizada: Optional[str] = None  # RF-05
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    estado: EstadoGeocodificacion = EstadoGeocodificacion.PENDIENTE
    error_detalle: Optional[str] = None  # motivo de excepción, para revisión manual (RF-10)
    nota_precision: Optional[str] = None  # se llena cuando la coincidencia es a nivel de calle/barrio, no del predio exacto

    def tiene_coordenadas(self) -> bool:
        return self.latitud is not None and self.longitud is not None


@dataclass
class ParadaRuta:
    orden: int
    pasajero: Pasajero
    distancia_desde_anterior_m: Optional[float] = None
    duracion_desde_anterior_s: Optional[float] = None


@dataclass
class RutaOptimizada:
    sentido: SentidoRuta
    origen: str
    paradas: list[ParadaRuta] = field(default_factory=list)
    distancia_total_m: float = 0.0
    duracion_total_s: float = 0.0
    excepciones: list[Pasajero] = field(default_factory=list)  # RF-09
    id: Optional[int] = None  # asignado al persistir (RF-17)
