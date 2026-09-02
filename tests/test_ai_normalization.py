"""Pruebas de la Fase 2 (normalización con IA) sin llamar a ningún servicio externo.

Se usa un cliente falso que implementa el contrato `AddressNormalizerClient`, de modo que
las pruebas verifican la lógica del pipeline (caché, red de seguridad del municipio,
propagación de advertencias) sin credenciales ni red.
"""
from __future__ import annotations

import pytest

from src.ai_normalization.cache import CachingAddressNormalizer
from src.ai_normalization.client import (
    AddressNormalizerClient,
    RespuestaIAIlegible,
    _parsear_respuesta,
)
from src.ai_normalization.normalizer import normalize_addresses
from src.models.schemas import (
    ConfianzaNormalizacion,
    DireccionNormalizada,
    EstadoGeocodificacion,
    Pasajero,
)


class _FakeNormalizer(AddressNormalizerClient):
    """Devuelve una respuesta fija y cuenta cuántas veces se le llamó."""

    def __init__(self, respuesta: DireccionNormalizada) -> None:
        self._respuesta = respuesta
        self.llamadas = 0

    def normalize(self, raw_address: str) -> DireccionNormalizada:
        self.llamadas += 1
        return DireccionNormalizada(
            direccion=self._respuesta.direccion,
            barrio=self._respuesta.barrio,
            municipio=self._respuesta.municipio,
            municipio_inferido=self._respuesta.municipio_inferido,
            confianza=self._respuesta.confianza,
            advertencia=self._respuesta.advertencia,
        )


def _pasajero(direccion: str, barrio: str | None = None) -> Pasajero:
    return Pasajero(identificador="1", nombre="Ana", direccion_original=direccion, barrio=barrio)


def test_parseo_tolera_texto_alrededor_del_json():
    contenido = (
        'El razonamiento del modelo se coló aquí... {"direccion": "Calle 1 #2-3, Soledad, '
        'Atlántico", "barrio": null, "municipio": "Soledad", "municipio_inferido": false, '
        '"confianza": "media", "advertencia": "sin barrio"} y más texto.'
    )
    resultado = _parsear_respuesta(contenido, "cll 1 2 3 soledad")
    assert resultado.direccion == "Calle 1 #2-3, Soledad, Atlántico"
    assert resultado.municipio == "Soledad"
    assert resultado.confianza == ConfianzaNormalizacion.MEDIA
    assert resultado.advertencia == "sin barrio"


def test_parseo_lanza_ilegible_si_no_hay_json():
    with pytest.raises(RespuestaIAIlegible):
        _parsear_respuesta("no pude procesar esto", "direccion rara")


def test_parseo_ignora_bloque_think_y_toma_el_json_final():
    contenido = (
        "<think>La entrada parece Calle 1. Voy a devolver {\"direccion\": \"borrador\"}</think>"
        '{"direccion": "Calle 1 #2-3, Barranquilla, Atlántico", "barrio": null, '
        '"municipio": "Barranquilla", "municipio_inferido": true, "confianza": "media", '
        '"advertencia": "municipio asumido"}'
    )
    resultado = _parsear_respuesta(contenido, "cll 1 2 3")
    assert resultado.direccion == "Calle 1 #2-3, Barranquilla, Atlántico"
    assert resultado.municipio_inferido is True


def test_cache_evita_segunda_llamada_para_direccion_repetida():
    fake = _FakeNormalizer(DireccionNormalizada(direccion="Calle 30 #8-60, Barranquilla, Atlántico"))
    cache = CachingAddressNormalizer(fake)

    cache.normalize("Calle 30 #8-60, Barranquilla")
    cache.normalize("calle 30  #8-60,   barranquilla")  # misma clave tras normalizar espacios/case

    assert fake.llamadas == 1
    assert cache.hits == 1
    assert cache.misses == 1


def test_red_de_seguridad_agrega_municipio_y_marca_advertencia():
    fake = _FakeNormalizer(
        DireccionNormalizada(direccion="Calle 1 #2-3", municipio_inferido=False)
    )
    pasajeros = [_pasajero("cll 1 #2-3")]

    normalize_addresses(pasajeros, fake)

    p = pasajeros[0]
    assert p.direccion_normalizada.endswith("Barranquilla, Atlántico")
    assert p.municipio_normalizado == "Barranquilla, Atlántico"
    assert "municipio asumido" in (p.advertencia_ia or "")
    assert p.estado == EstadoGeocodificacion.NORMALIZADA


def test_confianza_baja_produce_advertencia_para_revision():
    fake = _FakeNormalizer(
        DireccionNormalizada(
            direccion="Calle 26, Soledad, Atlántico",
            municipio="Soledad",
            confianza=ConfianzaNormalizacion.BAJA,
            advertencia="varias calles homónimas sin barrio",
        )
    )
    pasajeros = [_pasajero("calle 26 soledad")]

    normalize_addresses(pasajeros, fake)

    aviso = pasajeros[0].advertencia_ia or ""
    assert "ambigua" in aviso or "homónimas" in aviso


def test_fallo_de_ia_conserva_direccion_y_avisa():
    class _Roto(AddressNormalizerClient):
        def normalize(self, raw_address: str) -> DireccionNormalizada:
            raise RuntimeError("servicio caído")

    pasajeros = [_pasajero("cra 5 #6-7, Malambo")]
    normalize_addresses(pasajeros, _Roto())

    p = pasajeros[0]
    assert p.direccion_normalizada is not None
    assert "No se pudo normalizar con IA" in (p.advertencia_ia or "")
