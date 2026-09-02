"""Proveedor de geocodificación gratuito: Nominatim (OpenStreetMap), sin API key ni tarjeta.

Política de uso justo de Nominatim (https://operations.osmfoundation.org/policies/nominatim/):
máx. 1 solicitud/segundo y un User-Agent que identifique la aplicación. Este cliente respeta
ambas condiciones. Para volumen alto o uso en producción, la recomendación oficial es
autohospedar Nominatim o usar un proveedor comercial (p. ej. Google Maps, ya soportado en
`src/geocoding/google_maps_client.py`).
"""
from __future__ import annotations

import logging
import time

import re

import requests

from src.config import settings
from src.geocoding.base import GeocodingProvider, ResultadoGeocodificacion
from src.geocoding.candidate_scoring import elegir_mejor

logger = logging.getLogger(__name__)

USER_AGENT = "SistemaOptimizacionRutas/1.0 (uso educativo/desarrollo)"
MIN_INTERVAL_SECONDS = 1.1
FALLBACK_RATE_LIMIT_SECONDS = 5.0

# Campos de 'address' (con addressdetails=1) que indican que el resultado de Nominatim tiene
# una granularidad útil para ubicar un pasajero (calle, barrio/sector o predio), y no solo el
# centroide de una ciudad, departamento o país completo.
#
# Hallazgo real: cuando el barrio de una dirección no está bien escrito ni siquiera Nominatim
# lo reconoce, el motor de búsqueda de OSM a veces ignora el token no reconocido y devuelve un
# resultado válido pero demasiado genérico (el centro administrativo de "Barranquilla,
# Atlántico"). Esto hace que pasajeros con direcciones completamente distintas terminen con
# EXACTAMENTE las mismas coordenadas, lo cual rompe la optimización de rutas sin que se note
# (el resultado se reporta como "geocodificado" con éxito). Para evitarlo, se descartan los
# resultados cuyo 'address' no incluya ningún campo de esta lista: quedan como "no encontrada"
# y el pasajero cae en Gestión de Excepciones (RF-09) para revisión manual, en vez de un punto
# falso en el mapa.
CAMPOS_GRANULARIDAD_MINIMA = {
    "road", "residential", "pedestrian", "house_number", "building",
    "suburb", "neighbourhood", "quarter", "city_district",
}


class RateLimitError(Exception):
    """Servicio de geocodificación limitando temporalmente la IP del usuario (HTTP 429)."""


class NominatimGeocodingProvider(GeocodingProvider):
    def __init__(self) -> None:
        self._last_request_ts = 0.0

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)

    def _buscar(self, params: dict) -> list[dict]:
        """Ejecuta una consulta a Nominatim y devuelve la lista de resultados (con addressdetails).

        Ante un 429 (límite de tasa) no reintenta aquí: lanza RateLimitError para que el
        proveedor de conmutación automática cambie al respaldo. Solo reintenta ante timeouts.
        """
        self._respect_rate_limit()
        base = {
            "format": "json",
            "addressdetails": "1",
            "countrycodes": settings.nominatim_countrycodes,
            "viewbox": settings.nominatim_viewbox,
            "bounded": "1" if settings.nominatim_bounded else "0",
        }
        base.update(params)
        for intento in range(3):
            try:
                response = requests.get(
                    settings.nominatim_url,
                    params=base,
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                self._last_request_ts = time.monotonic()
                if response.status_code == 429:
                    raise RateLimitError(
                        "El servicio de geocodificación (Nominatim/OSM) está limitando esta IP "
                        "temporalmente por exceso de solicitudes. Se conmutará automáticamente "
                        "al proveedor de respaldo."
                    )
                response.raise_for_status()
                return response.json() or []
            except requests.exceptions.Timeout:
                if intento == 2:
                    raise
                time.sleep(2.0)
        return []

    @staticmethod
    def _es_granular(resultado: dict) -> bool:
        """El resultado tiene al menos nivel de calle/barrio (no es el centroide de una ciudad)."""
        return bool(CAMPOS_GRANULARIDAD_MINIMA.intersection(resultado.get("address", {}).keys()))

    def geocode(self, address: str) -> tuple[float, float] | None:
        results = [r for r in self._buscar({"q": address, "limit": 1}) if self._es_granular(r)]
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])

    def geocode_detallado(
        self,
        address: str,
        *,
        via: str | None = None,
        barrio: str | None = None,
        municipio: str | None = None,
    ) -> ResultadoGeocodificacion | None:
        """Pide varios candidatos y elige el que mejor coincide con vía + barrio + municipio.

        Evita el error frecuente de tomar el primer resultado y caer en un tramo de la misma
        calle situado en OTRO barrio (ver `candidate_scoring`).
        """
        via = via or _via_desde_direccion(address)
        via_sin_placa = re.sub(r"#\s*\S+", "", via or "").strip() if via else None

        vistos: set[tuple] = set()
        acumulados: list[dict] = []

        def _agregar(nuevos: list[dict]) -> None:
            for c in nuevos:
                clave = (c.get("lat"), c.get("lon"))
                if clave in vistos or not self._es_granular(c):
                    continue
                vistos.add(clave)
                acumulados.append(c)

        # Consultas de más a menos específica. Se evalúan de forma incremental y se corta en
        # cuanto hay una coincidencia fuerte (calle + barrio), para no golpear a Nominatim de más.
        consultas: list[dict] = [{"q": address, "limit": 10}]
        if via_sin_placa and (barrio or municipio):
            structured = {"limit": 10, "street": via_sin_placa, "country": "Colombia", "state": "Atlántico"}
            structured["city"] = barrio or municipio
            if municipio:
                structured["county"] = municipio
            consultas.append(structured)
        if via_sin_placa and barrio and municipio:
            consultas.append({"q": f"{via_sin_placa}, {barrio}, {municipio}, Atlántico", "limit": 10})
        if barrio and municipio:
            consultas.append({"q": f"{barrio}, {municipio}, Atlántico", "limit": 10})

        mejor, nota = None, None
        for params in consultas:
            _agregar(self._buscar(params))
            if not acumulados:
                continue
            mejor, nota = elegir_mejor(acumulados, via, barrio, municipio, settings.nominatim_viewbox)
            if mejor is not None and nota is None:
                break  # coincidencia fuerte: no hacen falta más consultas

        if mejor is None:
            return None
        return ResultadoGeocodificacion(float(mejor["lat"]), float(mejor["lon"]), nota)


def _via_desde_direccion(direccion: str) -> str | None:
    """Extrae la parte de vía (antes de la primera coma): 'Carrera 46 #79-50, Villa Country' -> 'Carrera 46 #79-50'."""
    if not direccion:
        return None
    return direccion.split(",", 1)[0].strip() or None


def _parse_retry_after(response) -> float:
    """Lee el header Retry-After (segundos o fecha RFC 1123) o usa un valor por defecto."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(float(raw), FALLBACK_RATE_LIMIT_SECONDS)
        except ValueError:
            # Puede venir una fecha RFC1123
            try:
                from email.utils import parsedate_to_datetime
                import datetime as _dt
                delta = (parsedate_to_datetime(raw).replace(tzinfo=_dt.timezone.utc)
                         - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
                return max(delta, FALLBACK_RATE_LIMIT_SECONDS)
            except Exception:
                return FALLBACK_RATE_LIMIT_SECONDS
    return FALLBACK_RATE_LIMIT_SECONDS
