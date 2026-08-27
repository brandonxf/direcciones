"""Herramienta dedicada: Excel de pasajeros -> Excel con latitud/longitud reales.

No calcula rutas. Todas las coordenadas provienen de una consulta real al servicio de
geocodificación configurado (por defecto Nominatim/OpenStreetMap) — las direcciones que no
se pueden ubicar quedan marcadas como excepción, nunca con coordenadas inventadas.

Ejemplo:
    python geocodificar.py --excel data/samples/pasajeros.xlsx --salida data/output/pasajeros_geocodificados.xlsx
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.config import configure_logging
from src.export.excel_exporter import export_passengers_to_excel, summarize
from src.pipeline import run_geocoding_pipeline

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Geocodifica un Excel de pasajeros y exporta el resultado.")
    parser.add_argument("--excel", required=True, help="Ruta al archivo Excel/CSV de entrada.")
    parser.add_argument("--salida", required=True, help="Ruta del archivo Excel de salida con latitud/longitud.")
    args = parser.parse_args()

    configure_logging()

    try:
        passengers = run_geocoding_pipeline(args.excel)
    except Exception as exc:
        logger.exception("Falló el procesamiento: %s", exc)
        return 1

    export_passengers_to_excel(passengers, args.salida)
    resumen = summarize(passengers)

    print(f"\nProcesados: {resumen['total']}")
    print(f"Geocodificados con éxito: {resumen['exitosos']} ({resumen['tasa_exito']:.1f}%)")
    print(f"Sin geolocalizar: {resumen['fallidos']}")
    print(f"\nResultado exportado a: {args.salida}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
