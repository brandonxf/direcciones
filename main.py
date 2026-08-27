"""Punto de entrada CLI del motor de procesamiento (backend).

Ejemplo de uso:
    python main.py --excel data/samples/pasajeros.xlsx \\
        --origen "Terminal de Transporte, Bogotá" \\
        --sentido entrada --turno mañana \\
        --export data/output/ruta_entrada.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from src.config import configure_logging
from src.models.schemas import SentidoRuta
from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def export_route_csv(ruta, output_path: str) -> None:
    """RF-16: exporta la ruta (orden de paradas, direcciones, tiempos y distancias) en CSV."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "orden", "identificador", "nombre", "direccion_original", "direccion_normalizada",
            "latitud", "longitud", "distancia_desde_anterior_m", "duracion_desde_anterior_s",
        ])
        for parada in ruta.paradas:
            p = parada.pasajero
            writer.writerow([
                parada.orden, p.identificador, p.nombre, p.direccion_original, p.direccion_normalizada,
                p.latitud, p.longitud, parada.distancia_desde_anterior_m, parada.duracion_desde_anterior_s,
            ])
    logger.info("Ruta exportada a %s", output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Motor de optimización de rutas de transporte.")
    parser.add_argument("--excel", required=True, help="Ruta al archivo Excel/CSV de pasajeros.")
    parser.add_argument("--origen", required=True, help="Dirección de origen (garaje / punto de partida).")
    parser.add_argument("--destino", default=None, help="Dirección de destino (por defecto, igual al origen).")
    parser.add_argument("--sentido", choices=["entrada", "salida"], required=True, help="Sentido de la ruta.")
    parser.add_argument("--turno", default=None, help="Turno asociado (ej. mañana, tarde).")
    parser.add_argument("--export", default=None, help="Ruta de archivo CSV para exportar el resultado.")

    args = parser.parse_args()

    configure_logging()

    try:
        ruta = run_pipeline(
            excel_path=args.excel,
            origin_address=args.origen,
            destination_address=args.destino,
            sentido=SentidoRuta(args.sentido),
            turno=args.turno,
        )
    except Exception as exc:
        logger.exception("El pipeline falló: %s", exc)
        return 1

    print(f"\nRuta calculada ({ruta.sentido.value}): {len(ruta.paradas)} paradas")
    print(f"Distancia total: {ruta.distancia_total_m / 1000:.2f} km")
    print(f"Duración total: {ruta.duracion_total_s / 60:.1f} min")
    if ruta.excepciones:
        print(f"Excepciones (requieren revisión manual): {len(ruta.excepciones)}")
        for exc_p in ruta.excepciones:
            print(f"  - {exc_p.nombre} ({exc_p.identificador}): {exc_p.error_detalle}")

    if args.export:
        export_route_csv(ruta, args.export)
        print(f"\nResultado exportado a: {args.export}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
