"""Exportación de resultados a Excel (RF-16).

Principio de diseño: nunca se escribe una coordenada que no provenga de una respuesta real
del servicio de geocodificación. Las direcciones que no pudieron geolocalizarse quedan con
latitud/longitud vacías y su motivo en la columna `error_detalle`, nunca con valores inventados.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.models.schemas import EstadoGeocodificacion, Pasajero


def export_passengers_to_excel(passengers: list[Pasajero], output_path: str | Path) -> None:
    rows = []
    for p in passengers:
        rows.append({
            "identificador": p.identificador,
            "nombre": p.nombre,
            "direccion_original": p.direccion_original,
            "barrio": p.barrio,
            "direccion_normalizada": p.direccion_normalizada,
            "latitud": p.latitud,  # None si no se pudo geocodificar (nunca un valor inventado)
            "longitud": p.longitud,
            "estado": p.estado.value,
            "nota_precision": p.nota_precision,
            "error_detalle": p.error_detalle,
        })

    df = pd.DataFrame(rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)


def summarize(passengers: list[Pasajero]) -> dict:
    total = len(passengers)
    exitosos = sum(1 for p in passengers if p.estado == EstadoGeocodificacion.GEOCODIFICADA)
    return {
        "total": total,
        "exitosos": exitosos,
        "fallidos": total - exitosos,
        "tasa_exito": (exitosos / total * 100) if total else 0.0,
    }
