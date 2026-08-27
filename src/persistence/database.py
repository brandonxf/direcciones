"""Capa de Persistencia (sección 7): pasajeros, direcciones normalizadas, coordenadas,
rutas generadas e historial (RF-17).

MVP con SQLite (stdlib, sin dependencias extra). Para producción, este módulo puede
reemplazarse por Postgres/otro motor sin afectar al resto del pipeline (RNF-09).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS rutas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentido TEXT NOT NULL,
    origen TEXT NOT NULL,
    turno TEXT,
    archivo_origen TEXT,
    fecha_generacion TEXT NOT NULL DEFAULT (datetime('now')),
    distancia_total_m REAL NOT NULL,
    duracion_total_s REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS paradas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_id INTEGER NOT NULL REFERENCES rutas(id),
    orden INTEGER NOT NULL,
    identificador_pasajero TEXT NOT NULL,
    nombre_pasajero TEXT NOT NULL,
    direccion_original TEXT NOT NULL,
    direccion_normalizada TEXT,
    latitud REAL,
    longitud REAL,
    distancia_desde_anterior_m REAL,
    duracion_desde_anterior_s REAL
);

CREATE TABLE IF NOT EXISTS excepciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_id INTEGER REFERENCES rutas(id),
    identificador_pasajero TEXT NOT NULL,
    nombre_pasajero TEXT NOT NULL,
    direccion_original TEXT NOT NULL,
    direccion_normalizada TEXT,
    error_detalle TEXT,
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.database_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
