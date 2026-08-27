"""Fase 2: Saneamiento y Normalización — RF-04, RF-05, RF-06, RNF-12, RNF-13."""
from __future__ import annotations

import logging
from collections.abc import Callable

from src.ai_normalization.client import AddressNormalizerClient
from src.models.schemas import EstadoGeocodificacion, Pasajero

logger = logging.getLogger(__name__)

NormalizationCallback = Callable[[int, int, Pasajero], None]

# Los 23 municipios del departamento del Atlántico. Se usa para garantizar de forma
# determinística que toda dirección final incluya un municipio — la IA no siempre agrega el
# municipio por defecto cuando el texto ya trae un barrio (ver hallazgo documentado en README).
MUNICIPIOS_ATLANTICO = [
    "barranquilla", "soledad", "malambo", "puerto colombia", "galapa", "baranoa",
    "sabanalarga", "santo tomás", "santo tomas", "palmar de varela", "sabanagrande",
    "ponedera", "repelón", "repelon", "luruaco", "piojó", "piojo", "tubará", "tubara",
    "usiacurí", "usiacuri", "candelaria", "manatí", "manati", "campo de la cruz", "suan",
    "santa lucía", "santa lucia", "polonuevo", "juan de acosta",
]

DEFAULT_MUNICIPIO = "Barranquilla, Atlántico"


def _asegurar_municipio(direccion: str) -> str:
    """Si ninguna de las 23 municipalidades del Atlántico aparece en el texto, la agrega.

    No confía en que el modelo de IA lo haga siempre (se observó que a veces lo omite cuando
    el texto ya trae un barrio) — esta verificación es determinística y siempre se aplica.
    """
    texto_normalizado = direccion.lower()
    if any(municipio in texto_normalizado for municipio in MUNICIPIOS_ATLANTICO):
        return direccion
    return f"{direccion}, {DEFAULT_MUNICIPIO}"


def normalize_addresses(
    passengers: list[Pasajero],
    client: AddressNormalizerClient,
    progress_callback: NormalizationCallback | None = None,
) -> list[Pasajero]:
    """Envía cada dirección al módulo de IA y conserva original + normalizada (RF-06).

    RNF-13 (tolerancia a fallos): si el servicio de IA falla para un registro puntual,
    se conserva la dirección original y se continúa con el resto del lote sin perder datos.

    Si se pasa `progress_callback`, se invoca con (indice_actual, total, pasajero) tras
    normalizar cada dirección.
    """
    total = len(passengers)
    for i, pasajero in enumerate(passengers, start=1):
        # Si el Excel trae un barrio/sector aparte, se anexa al texto de entrada: ayuda a
        # distinguir calles con el mismo nombre en distintos sectores (ver client.py, regla 6).
        texto_entrada = pasajero.direccion_original
        if pasajero.barrio:
            texto_entrada = f"{texto_entrada}, {pasajero.barrio}"

        try:
            resultado = client.normalize(texto_entrada)
            pasajero.direccion_normalizada = _asegurar_municipio(resultado)
            pasajero.estado = EstadoGeocodificacion.NORMALIZADA
        except Exception as exc:  # servicio de IA no disponible o error puntual
            logger.warning(
                "Fallo al normalizar dirección de %s (%s): %s. Se usará la dirección original.",
                pasajero.nombre,
                pasajero.identificador,
                exc,
            )
            pasajero.direccion_normalizada = _asegurar_municipio(texto_entrada)

        if progress_callback:
            progress_callback(i, total, pasajero)

    logger.info("Normalización completada para %d pasajeros.", len(passengers))
    return passengers
