"""Pruebas de la selección de candidato de geocodificación (sin red)."""
from __future__ import annotations

from src.geocoding.candidate_scoring import barrio_coincide, elegir_mejor, via_coincide

VIEWBOX = "-75.3,11.15,-74.6,10.1"


def _cand(lat, lon, road=None, suburb=None, city=None, house_number=None, tipo="residential"):
    addr = {}
    if road:
        addr["road"] = road
    if suburb:
        addr["suburb"] = suburb
    if city:
        addr["city"] = city
    if house_number:
        addr["house_number"] = house_number
    return {"lat": str(lat), "lon": str(lon), "type": tipo, "address": addr}


def test_barrio_coincide_tolera_acentos_y_relleno():
    assert barrio_coincide("Boulevard Sol Real", {"suburb": "Boulevard Sol Real"})
    assert barrio_coincide("boulevard sol real", {"neighbourhood": "Blvd Sol Real"})
    assert barrio_coincide("La Concepción", {"suburb": "Barrio La Concepcion"})
    assert not barrio_coincide("Villa Country", {"suburb": "Barlovento"})


def test_via_coincide_por_tipo_y_numero():
    assert via_coincide("Carrera 46 #79-50", {"road": "Carrera 46"})
    assert not via_coincide("Carrera 46", {"road": "Carrera 56"})


def test_elige_el_tramo_en_el_barrio_correcto_no_el_primero():
    # El primero de la lista está en otro barrio; el segundo es el correcto.
    candidatos = [
        _cand(10.9851, -74.7765, road="Carrera 46", suburb="Barlovento"),
        _cand(11.0050, -74.8050, road="Carrera 46", suburb="Villa Country"),
    ]
    mejor, nota = elegir_mejor(candidatos, "Carrera 46 #79-50", "Villa Country", "Barranquilla", VIEWBOX)
    assert (mejor["lat"], mejor["lon"]) == ("11.005", "-74.805")
    assert "barrio" in (nota or "").lower() or nota is None


def test_descarta_candidato_en_municipio_distinto():
    candidatos = [_cand(10.63, -74.92, road="Calle 26", city="Sabanalarga", suburb="Centro")]
    mejor, _ = elegir_mejor(candidatos, "Calle 26 #17-23", "Boulevard Sol Real", "Soledad", VIEWBOX)
    assert mejor is None


def test_coincidencia_fuerte_sin_nota_de_aproximacion():
    candidatos = [_cand(11.005, -74.805, road="Carrera 46", suburb="Villa Country", house_number="79")]
    mejor, nota = elegir_mejor(candidatos, "Carrera 46 #79-50", "Villa Country", "Barranquilla", VIEWBOX)
    assert mejor is not None
    assert nota is None
