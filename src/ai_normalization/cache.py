"""Caché de normalizaciones de IA (Fase 2).

Motivación: en una lista real de pasajeros muchas direcciones comparten la misma calle o el
mismo barrio, y a veces se repiten exactamente. Sin caché, cada fila gasta una llamada al
proveedor de IA (con su latencia y su costo). La caché guarda el resultado por texto de
entrada ya preprocesado, de modo que direcciones idénticas se resuelven una sola vez.

Es un envoltorio del contrato `AddressNormalizerClient`, así que es transparente para el
resto del pipeline y funciona con cualquier proveedor.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from src.ai_normalization.client import AddressNormalizerClient
from src.models.schemas import DireccionNormalizada

logger = logging.getLogger(__name__)


class CachingAddressNormalizer(AddressNormalizerClient):
    """Decorador que memoiza `normalize()` por texto de entrada normalizado (minúsculas/espacios)."""

    def __init__(self, inner: AddressNormalizerClient) -> None:
        self._inner = inner
        self._cache: dict[str, DireccionNormalizada] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _clave(raw_address: str) -> str:
        return " ".join(raw_address.lower().split())

    def normalize(self, raw_address: str) -> DireccionNormalizada:
        clave = self._clave(raw_address)
        cacheado = self._cache.get(clave)
        if cacheado is not None:
            self.hits += 1
            logger.debug("Caché de normalización: acierto para '%s'.", raw_address)
            # Copia defensiva: el pipeline puede mutar campos del resultado por pasajero.
            return replace(cacheado)

        self.misses += 1
        resultado = self._inner.normalize(raw_address)
        self._cache[clave] = resultado
        return replace(resultado)

    def resumen(self) -> str:
        total = self.hits + self.misses
        ahorro = (self.hits / total * 100) if total else 0.0
        return (
            f"Caché de normalización IA: {self.hits} aciertos / {self.misses} llamadas reales "
            f"({ahorro:.0f}% de llamadas evitadas)."
        )
