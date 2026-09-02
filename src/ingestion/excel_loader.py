"""Fase 1: Ingesta de Datos (Importación) — RF-01, RF-02, RF-03, RNF-07."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.models.schemas import Pasajero

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# Alias aceptados por columna lógica, para tolerar variaciones de nombre en el archivo de origen.
COLUMN_ALIASES: dict[str, list[str]] = {
    "identificador": ["identificador", "id", "cedula", "documento", "codigo"],
    "nombre": ["nombre", "nombres", "pasajero", "nombre completo"],
    # 'direccion_original' permite re-ingerir un Excel ya exportado por el sistema
    # (p. ej. para reprocesar tras corregir direcciones a mano).
    "direccion": [
        "direccion", "dirección", "direccion original", "direccion_original",
        "dirección original", "address",
    ],
    "turno": ["turno", "jornada", "horario"],
    # Opcional: distingue calles con el mismo nombre en distintos sectores/barrios
    # (frecuente en Colombia, ej. varias "Calle 26" en diferentes barrios de un mismo municipio).
    "barrio": ["barrio", "urbanizacion", "urbanización", "sector", "vereda", "conjunto"],
}

REQUIRED_LOGICAL_COLUMNS = ["identificador", "nombre", "direccion"]


class ExcelValidationError(Exception):
    """Error de validación de estructura del archivo (RF-03)."""


def _detect_column(df_columns: list[str], aliases: list[str]) -> str | None:
    normalized = {col.strip().lower(): col for col in df_columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """RF-02: identifica y extrae automáticamente las columnas relevantes, descartando el resto."""
    columns = list(df.columns)
    mapping: dict[str, str] = {}
    for logical_name, aliases in COLUMN_ALIASES.items():
        found = _detect_column(columns, aliases)
        if found:
            mapping[logical_name] = found

    missing = [c for c in REQUIRED_LOGICAL_COLUMNS if c not in mapping]
    if missing:
        raise ExcelValidationError(
            f"No se encontraron las columnas obligatorias: {missing}. "
            f"Columnas disponibles en el archivo: {columns}"
        )
    return mapping


def load_passengers(file_path: str | Path) -> list[Pasajero]:
    """Carga y valida un archivo de pasajeros (RF-01, RF-03) y devuelve entidades Pasajero (RF-02)."""
    path = Path(file_path)

    if not path.exists():
        raise ExcelValidationError(f"El archivo no existe: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ExcelValidationError(
            f"Formato no soportado '{path.suffix}'. Formatos válidos: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    logger.info("Cargando archivo de pasajeros: %s", path)

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, dtype=str)

    if df.empty:
        raise ExcelValidationError("El archivo no contiene filas de datos.")

    mapping = _map_columns(df)

    # RF-03: descarta filas vacías en columnas obligatorias y notifica.
    required_cols = [mapping[c] for c in REQUIRED_LOGICAL_COLUMNS]
    df_clean = df.dropna(subset=required_cols, how="any")
    filas_descartadas = len(df) - len(df_clean)
    if filas_descartadas:
        logger.warning("Se descartaron %d filas por datos obligatorios vacíos.", filas_descartadas)

    if df_clean.empty:
        raise ExcelValidationError("Ninguna fila cumple con los datos obligatorios (identificador, nombre, dirección).")

    passengers: list[Pasajero] = []
    for _, row in df_clean.iterrows():
        passengers.append(
            Pasajero(
                identificador=str(row[mapping["identificador"]]).strip(),
                nombre=str(row[mapping["nombre"]]).strip(),
                direccion_original=str(row[mapping["direccion"]]).strip(),
                turno=str(row[mapping["turno"]]).strip() if "turno" in mapping and pd.notna(row.get(mapping["turno"])) else None,
                barrio=str(row[mapping["barrio"]]).strip() if "barrio" in mapping and pd.notna(row.get(mapping["barrio"])) else None,
            )
        )

    logger.info("Se cargaron %d pasajeros válidos desde %s.", len(passengers), path.name)
    return passengers
