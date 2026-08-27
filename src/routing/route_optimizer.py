"""Fase 4: Cálculo y Optimización de la Ruta — RF-11, RF-12, RF-13, RF-14.

MVP: usa la Directions API de Google con `optimize_waypoints=True`, que reordena las paradas
para minimizar la ruta total (TSP aproximado resuelto por Google). Esta API admite hasta ~23
waypoints por solicitud.

Nota de escalabilidad (RNF-01, RNF-02): para lotes grandes (cientos de pasajeros por vehículo)
la Directions API no alcanza. El paso natural de evolución es:
  1) Agrupar pasajeros por zona/vehículo (clustering geográfico), y/o
  2) Migrar este módulo a la API dedicada "Route Optimization" de Google, o a un solver VRP
     (p. ej. Google OR-Tools) que sí soporta cientos de paradas y múltiples vehículos.
Este módulo se aisló (RNF-09) precisamente para permitir ese reemplazo sin tocar el resto del pipeline.
"""
from __future__ import annotations

import logging

import googlemaps

from src.config import settings
from src.models.schemas import ParadaRuta, Pasajero, RutaOptimizada, SentidoRuta

logger = logging.getLogger(__name__)

MAX_WAYPOINTS = 23  # límite práctico de la Directions API (25 - origen - destino)


class RoutingClient:
    def __init__(self) -> None:
        if not settings.google_maps_api_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY no está configurada. Define la variable de entorno en tu archivo .env."
            )
        self._client = googlemaps.Client(key=settings.google_maps_api_key)

    def directions(self, origin: str, destination: str, waypoints: list[str]) -> list[dict]:
        return self._client.directions(
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            optimize_waypoints=True,
            mode="driving",
        )


def optimize_route(
    origin: str,
    passengers: list[Pasajero],
    client: RoutingClient,
    sentido: SentidoRuta,
    destination: str | None = None,
) -> RutaOptimizada:
    """RF-11/RF-12/RF-13: calcula la secuencia óptima de paradas para un sentido dado.

    Solo se incluyen pasajeros ya geocodificados; las excepciones (RF-09) se listan aparte
    y no bloquean el cálculo del resto de la ruta.
    """
    geocoded = [p for p in passengers if p.tiene_coordenadas()]
    excepciones = [p for p in passengers if not p.tiene_coordenadas()]

    if not geocoded:
        raise ValueError("No hay pasajeros geocodificados para calcular la ruta.")

    if len(geocoded) > MAX_WAYPOINTS:
        raise ValueError(
            f"El lote tiene {len(geocoded)} paradas, por encima del límite de {MAX_WAYPOINTS} "
            "soportado por este optimizador basado en Directions API. Ver nota de escalabilidad "
            "en src/routing/route_optimizer.py (agrupar por vehículo o usar un solver VRP)."
        )

    destination = destination or origin
    waypoints = [f"{p.latitud},{p.longitud}" for p in geocoded]

    result = client.directions(origin=origin, destination=destination, waypoints=waypoints)
    if not result:
        raise RuntimeError("Google Directions no devolvió una ruta válida para los puntos dados.")

    route = result[0]
    order = route.get("waypoint_order", list(range(len(geocoded))))
    legs = route["legs"]

    ordered_passengers = [geocoded[i] for i in order]

    paradas: list[ParadaRuta] = []
    distancia_total = 0.0
    duracion_total = 0.0
    for idx, (pasajero, leg) in enumerate(zip(ordered_passengers, legs), start=1):
        distancia_m = leg["distance"]["value"]
        duracion_s = leg["duration"]["value"]
        distancia_total += distancia_m
        duracion_total += duracion_s
        paradas.append(
            ParadaRuta(
                orden=idx,
                pasajero=pasajero,
                distancia_desde_anterior_m=distancia_m,
                duracion_desde_anterior_s=duracion_s,
            )
        )

    logger.info(
        "Ruta (%s) calculada: %d paradas, %.1f km, %.1f min.",
        sentido.value,
        len(paradas),
        distancia_total / 1000,
        duracion_total / 60,
    )

    return RutaOptimizada(
        sentido=sentido,
        origen=origin,
        paradas=paradas,
        distancia_total_m=distancia_total,
        duracion_total_s=duracion_total,
        excepciones=excepciones,
    )
