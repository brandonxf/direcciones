"""Fase 4 (alternativa gratuita): Cálculo y Optimización de la Ruta con OSRM.

Usa el servicio "trip" de OSRM (Open Source Routing Machine), que resuelve el mismo problema
que Directions API con optimize_waypoints=True (TSP aproximado con origen/destino fijos),
sin API key ni tarjeta, contra el servidor de demostración público.

Nota: el servidor demo público (router.project-osrm.org) es solo para pruebas/desarrollo,
no para producción con volumen alto — ver
https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server. Para producción real,
autohospedar OSRM o usar `src/routing/route_optimizer.py` (Google, de pago) es lo recomendado.
"""
from __future__ import annotations

import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.geocoding.base import GeocodingProvider
from src.models.schemas import ParadaRuta, Pasajero, RutaOptimizada, SentidoRuta

logger = logging.getLogger(__name__)

MAX_WAYPOINTS = 50  # límite práctico razonable para el servidor demo público de OSRM


class OSRMRoutingClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.osrm_base_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def trip(self, coordinates: list[tuple[float, float]], roundtrip: bool) -> dict:
        """coordinates: lista de (lat, lng) en el orden de entrada (OSRM espera lon,lat en la URL)."""
        coords_str = ";".join(f"{lng},{lat}" for lat, lng in coordinates)
        params = {
            "source": "first",
            "roundtrip": "true" if roundtrip else "false",
            "overview": "false",
        }
        if not roundtrip:
            params["destination"] = "last"

        url = f"{self._base_url}/trip/v1/driving/{coords_str}"
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM devolvió un error: {data.get('code')} - {data.get('message')}")
        return data


def optimize_route(
    origin: str,
    passengers: list[Pasajero],
    client: OSRMRoutingClient,
    sentido: SentidoRuta,
    geocoder: GeocodingProvider,
    destination: str | None = None,
) -> RutaOptimizada:
    """RF-11/RF-12/RF-13: calcula la secuencia óptima de paradas para un sentido dado.

    A diferencia de la Directions API de Google, OSRM necesita coordenadas (no direcciones)
    para origen y destino, por lo que se geocodifican aquí usando el mismo `geocoder` de la Fase 3.
    """
    geocoded = [p for p in passengers if p.tiene_coordenadas()]
    excepciones = [p for p in passengers if not p.tiene_coordenadas()]

    if not geocoded:
        raise ValueError("No hay pasajeros geocodificados para calcular la ruta.")

    if len(geocoded) > MAX_WAYPOINTS:
        raise ValueError(
            f"El lote tiene {len(geocoded)} paradas, por encima del límite de {MAX_WAYPOINTS} "
            "recomendado para el servidor demo público de OSRM."
        )

    origin_coords = geocoder.geocode(origin)
    if origin_coords is None:
        raise ValueError(f"No se pudo geocodificar la dirección de origen: {origin}")

    roundtrip = destination is None or destination == origin
    destination_coords = None
    if not roundtrip:
        destination_coords = geocoder.geocode(destination)
        if destination_coords is None:
            raise ValueError(f"No se pudo geocodificar la dirección de destino: {destination}")

    waypoint_coords = [(p.latitud, p.longitud) for p in geocoded]
    all_coords = [origin_coords] + waypoint_coords + ([] if roundtrip else [destination_coords])

    data = client.trip(all_coords, roundtrip=roundtrip)

    # data["waypoints"] conserva el orden de ENTRADA; cada uno trae "waypoint_index" = su
    # posición en el recorrido optimizado. El índice 0 es siempre el origen (source=first).
    waypoint_meta = data["waypoints"]
    passenger_waypoint_meta = waypoint_meta[1:] if roundtrip else waypoint_meta[1:-1]

    order = sorted(range(len(geocoded)), key=lambda i: passenger_waypoint_meta[i]["waypoint_index"])
    ordered_passengers = [geocoded[i] for i in order]

    # legs[i] es el tramo que llega a la parada i-ésima del recorrido optimizado; el tramo
    # sobrante (regreso al origen en roundtrip, o nada en trayecto abierto) no se usa aquí.
    legs = data["trips"][0]["legs"][: len(ordered_passengers)]

    paradas: list[ParadaRuta] = []
    distancia_total = 0.0
    duracion_total = 0.0
    for idx, (pasajero, leg) in enumerate(zip(ordered_passengers, legs), start=1):
        distancia_total += leg["distance"]
        duracion_total += leg["duration"]
        paradas.append(
            ParadaRuta(
                orden=idx,
                pasajero=pasajero,
                distancia_desde_anterior_m=leg["distance"],
                duracion_desde_anterior_s=leg["duration"],
            )
        )

    logger.info(
        "Ruta OSRM (%s) calculada: %d paradas, %.1f km, %.1f min.",
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
