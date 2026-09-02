"""Fase 2: Saneamiento y Normalización — RF-04, RF-05, RF-06, RNF-12, RNF-13."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

from src.ai_normalization.client import AddressNormalizerClient
from src.models.schemas import (
    ConfianzaNormalizacion,
    DireccionNormalizada,
    EstadoGeocodificacion,
    Pasajero,
)

logger = logging.getLogger(__name__)

NormalizationCallback = Callable[[int, int, Pasajero], None]

# Siglas de tipo de vía colombianas -> forma completa. Normalización determinística previa
# a la IA: garantiza que 'Cra', 'Tv', 'Cl', etc. (con o sin punto, en cualquier mayúscula)
# siempre se expandan bien, sin depender de que el modelo de IA las reconozca.
# El orden importa: se procesan las más específicas/largas primero para evitar coincidencias
# parciales (ej. 'Tvra' antes de 'Tv', 'Avenida Calle' antes de 'Calle').
VIA_SIGLAS = [
    # (regex, forma_completa)
    # Usamos (?!\w) en vez de \b al final para capturar siglas seguidas de punto (''Cra.''),
    # y separamos la 'vía + numero' (ej. 'Av 30') de la letra suelta, evitando falsos positivos.
    (r"\bavenida\s+carrera\b", "Avenida Carrera"),
    (r"\bav\.?\s+carrera\b", "Avenida Carrera"),
    (r"\bav\.?\s*k\.?\b", "Avenida Carrera"),
    (r"\bak\.?\b(?!\w)", "Avenida Carrera"),
    (r"\baka\.?\b(?!\w)", "Avenida Carrera"),
    (r"\bautopista\b(?!\w)", "Autopista"),
    (r"\btransversal\b(?!\w)", "Transversal"),
    (r"\bdiagonal\b(?!\w)", "Diagonal"),
    (r"\bcarrera\b(?!\w)", "Carrera"),
    (r"\bavenida\b(?!\w)", "Avenida"),
    (r"\bcircular\b(?!\w)", "Circular"),
    (r"\bcll\.?\b(?!\w)", "Calle"),
    (r"\bcra\.?\b(?!\w)", "Carrera"),
    (r"\bkra\.?\b(?!\w)", "Carrera"),
    (r"\bcar\.?\b(?!\w)", "Carrera"),
    (r"\bcr\.?\b(?!\w)", "Carrera"),
    (r"\bkr\.?\b(?!\w)", "Carrera"),
    (r"\bcl\.?\b(?!\w)", "Calle"),
    (r"\btvra\.?\b(?!\w)", "Transversal"),
    (r"\btra\.?\b(?!\w)", "Transversal"),
    (r"\btransv\.?\b(?!\w)", "Transversal"),
    (r"\btv\.?\b(?!\w)", "Transversal"),
    (r"\bdiag\.?\b(?!\w)", "Diagonal"),
    (r"\bdg\.?\b(?!\w)", "Diagonal"),
    (r"\bav\.?\b(?!\w)", "Avenida"),
    (r"\bave\.?\b(?!\w)", "Avenida"),
    (r"\bcirc\.?\b(?!\w)", "Circular"),
    (r"\bcl\.?\b(?!\w)\s*(?!\d)", "Calle"),
    (r"\bt\.?\b(?!\w)\s*(?!\d)", "Transversal"),
    (r"\bc\.?\b(?!\w)\s*(?!\d)", "Calle"),
]


def _expandir_siglas_via(direccion: str) -> str:
    """Expande siglas de tipo de vía a su forma completa, de forma determinística.

    Se aplica como preprocesamiento antes de enviar a la IA. No modifica el resto de la
    dirección (números, barrios, municipios).
    """
    texto = direccion.strip()
    # Separa sigla de número cuando están pegadas (ej. 'Cra.21', 'Tv9') para que las
    # reglas las detecten con el separador de palabra.
    texto = re.sub(r"\b([a-z]{1,4})\.?([0-9])", r"\1 \2", texto, flags=re.IGNORECASE)
    for patron, forma in VIA_SIGLAS:
        texto = re.sub(patron, forma, texto, flags=re.IGNORECASE)
    # Elimina puntos de abreviatura residuales tras los tipos de vía ya expandidos
    # (ej. 'Carrera. 21' -> 'Carrera 21', 'Avenida.' -> 'Avenida').
    texto = re.sub(r"\b(Calle|Carrera|Transversal|Diagonal|Avenida|Circular|Autopista)\.(?=\s|#|$)", r"\1", texto, flags=re.IGNORECASE)
    # Normaliza espacios duplicados y espacios antes de comas
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s*,\s*", ", ", texto)
    return texto


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


def _asegurar_municipio(direccion: str) -> tuple[str, bool]:
    """Si ninguna de las 23 municipalidades del Atlántico aparece en el texto, la agrega.

    No confía en que el modelo de IA lo haga siempre (se observó que a veces lo omite cuando
    el texto ya trae un barrio) — esta verificación es determinística y siempre se aplica.

    Devuelve (direccion_final, municipio_fue_agregado).
    """
    texto_normalizado = direccion.lower()
    if any(municipio in texto_normalizado for municipio in MUNICIPIOS_ATLANTICO):
        return direccion, False
    return f"{direccion}, {DEFAULT_MUNICIPIO}", True


def _construir_advertencia(resultado: DireccionNormalizada, municipio_agregado: bool) -> str | None:
    """Une la advertencia de la IA con los avisos determinísticos en una sola nota legible."""
    avisos: list[str] = []
    if resultado.municipio_inferido or municipio_agregado:
        avisos.append("municipio asumido como Barranquilla (no venía en la dirección)")
    if resultado.confianza == ConfianzaNormalizacion.BAJA:
        avisos.append("dirección incompleta o ambigua: alto riesgo de ubicación imprecisa")
    if resultado.advertencia:
        avisos.append(resultado.advertencia)
    if not avisos:
        return None
    # Sin duplicados, conservando el orden.
    vistos: dict[str, None] = {}
    for aviso in avisos:
        vistos.setdefault(aviso.strip().rstrip("."), None)
    return "; ".join(vistos)


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

        # Normalización determinística de siglas de vía (Cra, Tv, Cl, etc.) antes de la IA:
        # asegura que 'transversal', 'cra', 'cll' etc. lleguen ya expandidos al modelo.
        texto_entrada = _expandir_siglas_via(texto_entrada)

        try:
            resultado = client.normalize(texto_entrada)
            direccion_final, municipio_agregado = _asegurar_municipio(resultado.direccion)
            pasajero.direccion_normalizada = direccion_final
            pasajero.barrio_normalizado = resultado.barrio or pasajero.barrio
            pasajero.municipio_normalizado = resultado.municipio or (
                DEFAULT_MUNICIPIO if (resultado.municipio_inferido or municipio_agregado) else None
            )
            pasajero.advertencia_ia = _construir_advertencia(resultado, municipio_agregado)
            pasajero.estado = EstadoGeocodificacion.NORMALIZADA
        except Exception as exc:  # servicio de IA no disponible o error puntual
            logger.warning(
                "Fallo al normalizar dirección de %s (%s): %s. Se usará la dirección original.",
                pasajero.nombre,
                pasajero.identificador,
                exc,
            )
            direccion_final, _ = _asegurar_municipio(texto_entrada)
            pasajero.direccion_normalizada = direccion_final
            pasajero.barrio_normalizado = pasajero.barrio
            pasajero.advertencia_ia = (
                "No se pudo normalizar con IA (servicio no disponible); se usó la dirección "
                "original preprocesada. Conviene revisarla manualmente."
            )

        if progress_callback:
            progress_callback(i, total, pasajero)

    logger.info("Normalización completada para %d pasajeros.", len(passengers))
    return passengers
