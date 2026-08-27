"""Orquestador del flujo operativo completo (sección 4 del documento técnico):
Fase 1 Ingesta -> Fase 2 Normalización IA -> Fase 3 Geocodificación -> Fase 4 Ruteo.

Los proveedores de geocodificación y ruteo son intercambiables vía configuración
(GEOCODING_PROVIDER / ROUTING_PROVIDER en .env) — RNF-09, RNF-10.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from src.ai_normalization.client import NvidiaAddressNormalizer
from src.ai_normalization.normalizer import NormalizationCallback, normalize_addresses
from src.config import settings
from src.exceptions.exception_manager import list_exceptions
from src.geocoding.base import GeocodingProvider
from src.geocoding.service import ProgressCallback, geocode_passengers
from src.ingestion.excel_loader import load_passengers
from src.models.schemas import RutaOptimizada, SentidoRuta
from src.models.schemas import Pasajero
from src.persistence.database import init_db
from src.persistence.repository import save_route

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def run_geocoding_pipeline(
    excel_path: str,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> list[Pasajero]:
    """Fase 1 -> Fase 2 -> Fase 3, sin ruteo: ingesta, normalización IA y geocodificación real.

    Cada Pasajero devuelto tiene latitud/longitud reales (obtenidas del proveedor configurado)
    o None si no pudo geolocalizarse — nunca un valor inventado.

    `progress_callback` se reenvía a la geocodificación para reportar progreso en tiempo real.
    `log_callback` recibe mensajes de estado de cada fase (ingesta, limpieza, geocodificación)
    para mostrarlos en la interfaz web.
    """
    def _log(msg: str) -> None:
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    _log("=== Fase 1: Ingesta ===")
    passengers = load_passengers(excel_path)
    _log(f"Se cargaron {len(passengers)} pasajeros válidos desde el archivo.")

    _log("=== Fase 2: Saneamiento y Normalización (IA) ===")
    ai_client = NvidiaAddressNormalizer()

    def _norm_progreso(i: int, total: int, pasajero: Pasajero) -> None:
        if log_callback:
            log_callback(f"Limpieza {i}/{total}: {pasajero.nombre} ({pasajero.direccion_normalizada or pasajero.direccion_original})")

    passengers = normalize_addresses(passengers, ai_client, _norm_progreso)
    _log("Normalización completada.")

    _log(f"=== Fase 3: Validación y Geocodificación ({settings.geocoding_provider}) ===")
    geo_provider = _build_geocoding_provider()

    def _geo_progreso(i: int, total: int, pasajero: Pasajero) -> None:
        if pasajero.latitud is not None and pasajero.longitud is not None:
            estado_msg = f"{pasajero.latitud}, {pasajero.longitud}"
        else:
            estado_msg = "NO ENCONTRADA"
        if log_callback:
            log_callback(f"Geocodificación {i}/{total}: {pasajero.nombre} -> {estado_msg}")
        if progress_callback:
            progress_callback(i, total, pasajero)

    passengers = geocode_passengers(passengers, geo_provider, _geo_progreso)

    resumen = list_exceptions(passengers)
    if resumen:
        logger.warning("%d dirección(es) no se pudieron geolocalizar.", len(resumen))
        if log_callback:
            log_callback(f"{len(resumen)} dirección(es) no se pudieron geolocalizar.")

    return passengers


def _build_geocoding_provider() -> GeocodingProvider:
    if settings.geocoding_provider == "google":
        from src.geocoding.google_maps_client import GeocodingClient

        return GeocodingClient()

    if settings.geocoding_provider == "locationiq":
        from src.geocoding.locationiq_client import LocationIQGeocodingProvider

        return LocationIQGeocodingProvider()

    from src.geocoding.nominatim_client import NominatimGeocodingProvider

    return NominatimGeocodingProvider()


def _compute_route(
    origin_address: str,
    passengers: list,
    sentido: SentidoRuta,
    destination_address: str | None,
    geo_provider: GeocodingProvider,
) -> RutaOptimizada:
    if settings.routing_provider == "google":
        from src.routing.route_optimizer import RoutingClient
        from src.routing.route_optimizer import optimize_route as optimize_route_google

        routing_client = RoutingClient()
        return optimize_route_google(
            origin=origin_address,
            passengers=passengers,
            client=routing_client,
            sentido=sentido,
            destination=destination_address,
        )

    from src.routing.osrm_client import OSRMRoutingClient
    from src.routing.osrm_client import optimize_route as optimize_route_osrm

    routing_client = OSRMRoutingClient()
    return optimize_route_osrm(
        origin=origin_address,
        passengers=passengers,
        client=routing_client,
        sentido=sentido,
        geocoder=geo_provider,
        destination=destination_address,
    )


def run_pipeline(
    excel_path: str,
    origin_address: str,
    sentido: SentidoRuta,
    turno: str | None = None,
    destination_address: str | None = None,
) -> RutaOptimizada:
    """Ejecuta el flujo completo para un archivo de pasajeros y devuelve la ruta optimizada."""
    init_db()

    logger.info("=== Fase 1: Ingesta === (%s)", excel_path)
    passengers = load_passengers(excel_path)

    logger.info("=== Fase 2: Saneamiento y Normalización (IA) ===")
    ai_client = NvidiaAddressNormalizer()
    passengers = normalize_addresses(passengers, ai_client)

    logger.info("=== Fase 3: Validación y Geocodificación (%s) ===", settings.geocoding_provider)
    geo_provider = _build_geocoding_provider()
    passengers = geocode_passengers(passengers, geo_provider)

    excepciones = list_exceptions(passengers)
    if excepciones:
        logger.warning(
            "%d pasajero(s) requieren revisión manual (excepciones de geocodificación).",
            len(excepciones),
        )

    logger.info("=== Fase 4: Cálculo y Optimización de la Ruta (%s) ===", settings.routing_provider)
    ruta = _compute_route(origin_address, passengers, sentido, destination_address, geo_provider)

    ruta_id = save_route(ruta, turno=turno, archivo_origen=excel_path)
    ruta.id = ruta_id
    logger.info("Ruta guardada con id=%d en el historial.", ruta_id)

    return ruta
