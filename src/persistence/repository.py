"""Operaciones de persistencia sobre rutas, paradas y excepciones (RF-17)."""
from __future__ import annotations

from src.models.schemas import RutaOptimizada
from src.persistence.database import get_connection


def save_route(ruta: RutaOptimizada, turno: str | None, archivo_origen: str | None) -> int:
    """Guarda la ruta generada, asociada a fecha, turno y archivo de origen (RF-17)."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO rutas (sentido, origen, turno, archivo_origen, distancia_total_m, duracion_total_s)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ruta.sentido.value, ruta.origen, turno, archivo_origen, ruta.distancia_total_m, ruta.duracion_total_s),
        )
        ruta_id = cursor.lastrowid

        for parada in ruta.paradas:
            p = parada.pasajero
            conn.execute(
                """
                INSERT INTO paradas (
                    ruta_id, orden, identificador_pasajero, nombre_pasajero,
                    direccion_original, direccion_normalizada, latitud, longitud,
                    distancia_desde_anterior_m, duracion_desde_anterior_s
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ruta_id, parada.orden, p.identificador, p.nombre,
                    p.direccion_original, p.direccion_normalizada, p.latitud, p.longitud,
                    parada.distancia_desde_anterior_m, parada.duracion_desde_anterior_s,
                ),
            )

        for excepcion in ruta.excepciones:
            conn.execute(
                """
                INSERT INTO excepciones (
                    ruta_id, identificador_pasajero, nombre_pasajero,
                    direccion_original, direccion_normalizada, error_detalle
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ruta_id, excepcion.identificador, excepcion.nombre,
                    excepcion.direccion_original, excepcion.direccion_normalizada, excepcion.error_detalle,
                ),
            )

        return ruta_id


def get_route_detail(ruta_id: int) -> dict | None:
    """Detalle completo de una ruta persistida: cabecera, paradas y excepciones."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, sentido, origen, turno, archivo_origen, fecha_generacion, "
            "distancia_total_m, duracion_total_s FROM rutas WHERE id = ?",
            (ruta_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [c[0] for c in cursor.description]
        ruta = dict(zip(columns, row))

        cursor = conn.execute(
            "SELECT orden, identificador_pasajero, nombre_pasajero, direccion_original, "
            "direccion_normalizada, latitud, longitud, distancia_desde_anterior_m, "
            "duracion_desde_anterior_s FROM paradas WHERE ruta_id = ? ORDER BY orden",
            (ruta_id,),
        )
        columns = [c[0] for c in cursor.description]
        ruta["paradas"] = [dict(zip(columns, r)) for r in cursor.fetchall()]

        cursor = conn.execute(
            "SELECT identificador_pasajero, nombre_pasajero, direccion_original, "
            "direccion_normalizada, error_detalle FROM excepciones WHERE ruta_id = ?",
            (ruta_id,),
        )
        columns = [c[0] for c in cursor.description]
        ruta["excepciones"] = [dict(zip(columns, r)) for r in cursor.fetchall()]

    return ruta


def get_route_history(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        conn.row_factory = None
        cursor = conn.execute(
            "SELECT id, sentido, origen, turno, archivo_origen, fecha_generacion, "
            "distancia_total_m, duracion_total_s FROM rutas ORDER BY fecha_generacion DESC LIMIT ?",
            (limit,),
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
