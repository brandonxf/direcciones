"""Selección del mejor candidato de geocodificación cuando el proveedor devuelve varios.

Problema real (ver README): OpenStreetMap no tiene numeración de placa en el Atlántico, así
que para una calle dada suele haber varios tramos en barrios distintos. Pedir `limit=1` y
tomar el primer resultado hace que un pasajero de "Carrera 46, Villa Country" termine en
"Carrera 46, Barlovento" — otro barrio a varios kilómetros, reportado como éxito.

Este módulo puntúa cada candidato contra la dirección buscada (calle + barrio) y elige el
mejor, además de decir con honestidad qué tan aproximado quedó (barrio confirmado, solo el
barrio, o ni siquiera eso).
"""
from __future__ import annotations

import re
import unicodedata

# Campos del 'address' de Nominatim que representan un barrio / sector / urbanización.
CAMPOS_BARRIO = ("suburb", "neighbourhood", "quarter", "city_district", "residential", "hamlet")
# Campos que representan el municipio.
CAMPOS_MUNICIPIO = ("city", "town", "village", "municipality", "county")

_PALABRAS_RELLENO = {
    "barrio", "urbanizacion", "urb", "sector", "conjunto", "residencial", "etapa",
    "manzana", "mz", "el", "la", "los", "las", "de", "del", "y",
}


def normalizar(texto: str | None) -> str:
    """minúsculas, sin tildes, sin puntuación, sin palabras de relleno."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-z0-9 ]", " ", texto.lower())
    tokens = [t for t in texto.split() if t and t not in _PALABRAS_RELLENO]
    return " ".join(tokens)


def _tokens(texto: str | None) -> set[str]:
    return set(normalizar(texto).split())


def barrio_coincide(barrio_objetivo: str | None, address: dict) -> bool:
    """True si el barrio buscado coincide (por inclusión o solape de tokens) con algún
    campo de barrio del resultado de Nominatim."""
    objetivo = normalizar(barrio_objetivo)
    if not objetivo:
        return False
    obj_tokens = set(objetivo.split())
    for campo in CAMPOS_BARRIO:
        cand = normalizar(address.get(campo))
        if not cand:
            continue
        if objetivo in cand or cand in objetivo:
            return True
        cand_tokens = set(cand.split())
        solape = obj_tokens & cand_tokens
        # Coincidencia parcial fuerte: comparten una palabra "significativa" (>3 letras)
        # y esa palabra no es un número de calle.
        if any(len(t) > 3 and not t.isdigit() for t in solape):
            return True
    return False


def municipio_coincide(municipio_objetivo: str | None, address: dict) -> bool:
    objetivo = normalizar(municipio_objetivo)
    if not objetivo:
        return False
    for campo in CAMPOS_MUNICIPIO:
        cand = normalizar(address.get(campo))
        if cand and (objetivo in cand or cand in objetivo):
            return True
    return False


def via_coincide(via_objetivo: str | None, address: dict) -> bool:
    """True si el nombre de vía buscado (ej. 'Carrera 46') coincide con el 'road' del resultado."""
    objetivo = _tokens(via_objetivo)
    road = _tokens(address.get("road"))
    if not objetivo or not road:
        return False
    # El tipo de vía y el número deben coincidir (ej. {'carrera','46'} ⊆ road).
    return objetivo.issubset(road) or road.issubset(objetivo)


def dentro_viewbox(lat: float, lon: float, viewbox: str) -> bool:
    try:
        min_lon, max_lat, max_lon, min_lat = (float(x) for x in viewbox.split(","))
    except (ValueError, AttributeError):
        return True
    return min_lat <= lat <= max_lat and min(min_lon, max_lon) <= lon <= max(min_lon, max_lon)


def puntuar(
    candidato: dict,
    via_objetivo: str | None,
    barrio_objetivo: str | None,
    municipio_objetivo: str | None,
    viewbox: str | None,
) -> tuple[int, list[str]]:
    """Devuelve (puntaje, motivos). Puntaje alto = candidato más confiable."""
    address = candidato.get("address", {})
    puntaje = 0
    motivos: list[str] = []

    if barrio_coincide(barrio_objetivo, address):
        puntaje += 5
        motivos.append("barrio")
    elif municipio_coincide(municipio_objetivo, address):
        puntaje += 1
        motivos.append("municipio")
    elif municipio_objetivo:
        # candidato fuera del municipio buscado: penalización fuerte
        puntaje -= 4
        motivos.append("municipio_distinto")

    if via_coincide(via_objetivo, address):
        puntaje += 3
        motivos.append("via")

    if address.get("house_number"):
        puntaje += 2
        motivos.append("placa")

    if candidato.get("type") in {"residential", "living_street", "unclassified", "tertiary", "secondary", "primary", "house", "building"}:
        puntaje += 1

    if viewbox:
        try:
            if dentro_viewbox(float(candidato["lat"]), float(candidato["lon"]), viewbox):
                puntaje += 1
            else:
                puntaje -= 3
                motivos.append("fuera_de_region")
        except (KeyError, ValueError):
            pass

    return puntaje, motivos


def elegir_mejor(
    candidatos: list[dict],
    via_objetivo: str | None,
    barrio_objetivo: str | None,
    municipio_objetivo: str | None,
    viewbox: str | None,
) -> tuple[dict | None, str | None]:
    """Elige el candidato de mayor puntaje. Devuelve (candidato, nota_precision).

    nota_precision es None solo si la coincidencia es fuerte (vía + barrio); en otro caso
    describe honestamente el nivel de aproximación.
    """
    if not candidatos:
        return None, None

    # Descarta de entrada los candidatos que están en OTRO municipio del buscado: es la causa
    # documentada de coincidencias a decenas de km (una calle homónima en otro pueblo).
    if normalizar(municipio_objetivo):
        en_municipio = [
            c for c in candidatos
            if municipio_coincide(municipio_objetivo, c.get("address", {}))
            or not any(
                normalizar(c.get("address", {}).get(campo)) for campo in CAMPOS_MUNICIPIO
            )
        ]
        if not en_municipio:
            return None, None  # ningún candidato está en el municipio correcto
        candidatos = en_municipio

    puntuados = [
        (puntuar(c, via_objetivo, barrio_objetivo, municipio_objetivo, viewbox), c)
        for c in candidatos
    ]
    puntuados.sort(key=lambda x: x[0][0], reverse=True)
    (mejor_puntaje, motivos), mejor = puntuados[0]

    if mejor_puntaje < 0:
        return None, None  # ni el municipio coincide: mejor dejarlo como excepción

    tiene_barrio = "barrio" in motivos
    tiene_via = "via" in motivos
    tiene_placa = "placa" in motivos

    if tiene_via and tiene_barrio and tiene_placa:
        return mejor, None
    if tiene_via and tiene_barrio:
        return mejor, "Aproximado: calle y barrio correctos, sin número de placa (OSM no lo tiene)."
    if tiene_barrio:
        return mejor, "Aproximado: ubicado dentro del barrio correcto; la calle exacta no se confirmó."
    if tiene_via:
        return mejor, "Aproximado: calle correcta, pero el barrio no se pudo confirmar."
    return mejor, "Aproximado: solo se ubicó el municipio; revisar manualmente."
