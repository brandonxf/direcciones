"""Fase 3: Validación y Geocodificación — RF-07, RF-08, RF-09, RNF-08, RNF-12, RNF-13.

Lógica de negocio independiente del proveedor concreto (Nominatim, Google, etc.),
que solo depende del contrato `GeocodingProvider`.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

from src.geocoding.base import GeocodingProvider
from src.geocoding.candidate_scoring import normalizar
from src.models.schemas import EstadoGeocodificacion, Pasajero

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, Pasajero], None]


def _sin_numero_de_placa(direccion: str) -> str | None:
    """Quita el '#NN-NN' dejando el nombre de la vía + barrio/municipio.

    Hallazgo real: Nominatim suele devolver "SIN RESULTADOS" cuando la combinación exacta de
    calle + número de placa + barrio no está indexada a nivel de predio, aunque la calle y el
    barrio sí existan por separado. Quitar el número de placa suele recuperar un resultado
    dentro del barrio correcto (ver README, sección de precisión).
    """
    sin_numero = re.sub(r"#\s*\S+", "", direccion)
    sin_numero = re.sub(r"\s+,", ",", sin_numero).strip().strip(",").strip()
    return sin_numero if sin_numero and sin_numero != direccion else None


def _solo_localidad(direccion: str) -> str | None:
    """Se queda solo con lo que sigue a la primera coma (barrio/municipio), sin la vía."""
    partes = direccion.split(",", 1)
    if len(partes) < 2:
        return None
    localidad = partes[1].strip()
    return localidad or None


def _geocodificar_con_reintentos(
    direccion: str,
    provider: GeocodingProvider,
    barrio: str | None = None,
    municipio: str | None = None,
) -> tuple[tuple[float, float] | None, str | None]:
    """Intenta geocodificar con precisión decreciente. Devuelve (coords, nota_precision).

    nota_precision es None si el resultado corresponde a la consulta completa (máxima
    precisión disponible); en caso contrario describe qué tan aproximado quedó el punto.

    Cuando la Fase 2 (IA) identificó el barrio y el municipio por separado, se usan para que
    el proveedor elija, entre varios candidatos, el tramo de calle que está en el barrio
    correcto (`geocode_detallado`) — evita el error de tomar el primer resultado y caer en
    otro barrio a varios kilómetros.
    """
    via = direccion.split(",", 1)[0].strip() or None

    detalle = provider.geocode_detallado(direccion, via=via, barrio=barrio, municipio=municipio)
    if detalle is not None:
        return detalle.coords, detalle.nota_precision

    # Respaldos determinísticos (para proveedores sin selección de candidato).
    sin_numero = _sin_numero_de_placa(direccion)
    if sin_numero:
        coords = provider.geocode(sin_numero)
        if coords is not None:
            return coords, "Aproximado: no se encontró el número de placa exacto; ubicación a nivel de calle/barrio."

    consulta_localidad = None
    if barrio and municipio:
        consulta_localidad = f"{barrio}, {municipio}"
    elif barrio:
        consulta_localidad = barrio
    if consulta_localidad is None:
        consulta_localidad = _solo_localidad(direccion)
    if consulta_localidad:
        coords = provider.geocode(consulta_localidad)
        if coords is not None:
            return coords, "Aproximado: solo se pudo ubicar el barrio/municipio, no la calle exacta."

    if municipio and normalizar(municipio) not in normalizar(consulta_localidad):
        coords = provider.geocode(municipio)
        if coords is not None:
            return coords, "Aproximado: solo se pudo ubicar el municipio, no el barrio ni la calle."

    return None, None


def geocode_passengers(
    passengers: list[Pasajero],
    provider: GeocodingProvider,
    progress_callback: ProgressCallback | None = None,
) -> list[Pasajero]:
    """RF-07/RF-08: geocodifica cada dirección normalizada, con reintentos de precisión decreciente.
    RF-09: registra en estado EXCEPCION las que no logran ser geolocalizadas, sin detener el flujo.

    Si se pasa `progress_callback`, se invoca con (indice_actual, total, pasajero) tras procesar
    cada pasajero, para reportar progreso en tiempo real (índice 1-based).
    """
    exitosos = 0
    aproximados = 0
    total = len(passengers)
    for i, pasajero in enumerate(passengers, start=1):
        direccion = pasajero.direccion_normalizada or pasajero.direccion_original
        try:
            coords, nota = _geocodificar_con_reintentos(
                direccion,
                provider,
                barrio=pasajero.barrio_normalizado,
                municipio=pasajero.municipio_normalizado,
            )
        except Exception as exc:  # RNF-13: no perder los datos ya procesados ante fallo del servicio
            logger.error("Error consultando el servicio de geocodificación para '%s': %s", direccion, exc)
            pasajero.estado = EstadoGeocodificacion.EXCEPCION
            pasajero.error_detalle = f"Error de servicio: {exc}"
            if progress_callback:
                progress_callback(i, total, pasajero)
            continue

        if coords is None:
            pasajero.estado = EstadoGeocodificacion.EXCEPCION
            detalle = "Dirección no geolocalizable tras el saneamiento con IA."
            if pasajero.advertencia_ia:
                detalle = f"{detalle} Aviso de la IA: {pasajero.advertencia_ia}."
            pasajero.error_detalle = detalle
            logger.warning("Excepción de geocodificación: %s (%s)", pasajero.nombre, direccion)
            if progress_callback:
                progress_callback(i, total, pasajero)
            continue

        pasajero.latitud, pasajero.longitud = coords
        pasajero.estado = EstadoGeocodificacion.GEOCODIFICADA
        pasajero.nota_precision = nota
        exitosos += 1
        if nota:
            aproximados += 1
            logger.info("Geocodificado de forma aproximada: %s (%s)", pasajero.nombre, nota)
        if progress_callback:
            progress_callback(i, total, pasajero)

    tasa = (exitosos / total * 100) if total else 0.0
    logger.info(
        "Geocodificación: %d/%d exitosos (%.1f%%), de los cuales %d aproximados.",
        exitosos, total, tasa, aproximados,
    )  # RNF-08
    return passengers


def retry_single_address(pasajero: Pasajero, corrected_address: str, provider: GeocodingProvider) -> Pasajero:
    """RF-10: corrección manual de una dirección fallida y reintento individual."""
    pasajero.direccion_normalizada = corrected_address
    coords, nota = _geocodificar_con_reintentos(
        corrected_address,
        provider,
        barrio=pasajero.barrio_normalizado or pasajero.barrio,
        municipio=pasajero.municipio_normalizado,
    )
    if coords is None:
        pasajero.estado = EstadoGeocodificacion.EXCEPCION
        pasajero.error_detalle = "Dirección corregida manualmente sigue sin ser geolocalizable."
        return pasajero

    pasajero.latitud, pasajero.longitud = coords
    pasajero.estado = EstadoGeocodificacion.GEOCODIFICADA
    pasajero.error_detalle = None
    pasajero.nota_precision = nota
    return pasajero
