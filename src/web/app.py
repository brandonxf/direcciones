"""Interfaz web (Flask) para el motor de procesamiento.

Página principal (`/`): flujo simple pedido por el negocio — subir un Excel de pasajeros,
geocodificar cada dirección con datos reales (Nominatim/Google, nunca inventados) y descargar
un Excel con latitud/longitud (RF-16).

Página secundaria (`/ruta`): flujo completo con cálculo de ruta óptima, para cuando se
necesite ese caso de uso adicional.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from src.config import BASE_DIR, configure_logging
from src.export.excel_exporter import export_passengers_to_excel, summarize
from src.models.schemas import SentidoRuta
from src.persistence.repository import get_route_detail, get_route_history
from src.pipeline import run_geocoding_pipeline, run_pipeline

configure_logging()
logger = logging.getLogger(__name__)

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = BASE_DIR / "data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = "dev-only-no-usar-en-produccion"


# --- Página principal: geocodificación (Excel -> Excel con lat/lon reales) ---

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", resultado=None)


@app.route("/geocodificar", methods=["POST"])
def geocodificar():
    archivo = request.files.get("excel")
    if not archivo or archivo.filename == "":
        flash("Debes seleccionar un archivo Excel/CSV.")
        return redirect(url_for("index"))

    filename = secure_filename(archivo.filename)
    upload_path = UPLOAD_DIR / filename
    archivo.save(upload_path)

    try:
        passengers = run_geocoding_pipeline(str(upload_path))
    except Exception as exc:
        logger.exception("Error geocodificando el archivo: %s", exc)
        flash(f"Error al procesar el archivo: {exc}")
        return redirect(url_for("index"))

    stem = Path(filename).stem
    output_filename = f"{stem}_geocodificado_{int(time.time())}.xlsx"
    export_passengers_to_excel(passengers, OUTPUT_DIR / output_filename)

    resultado = {
        "passengers": passengers,
        "resumen": summarize(passengers),
        "archivo": output_filename,
    }
    return render_template("index.html", resultado=resultado)


@app.route("/descargar-excel/<path:filename>")
def descargar_excel(filename: str):
    safe_name = secure_filename(filename)
    if not (OUTPUT_DIR / safe_name).exists():
        flash("El archivo solicitado no existe o ya expiró.")
        return redirect(url_for("index"))
    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=True)


# --- Página secundaria: cálculo de ruta óptima (flujo completo de las 4 fases) ---

@app.route("/ruta", methods=["GET"])
def ruta_form():
    historial = get_route_history(limit=10)
    return render_template("ruta.html", historial=historial)


@app.route("/ruta/procesar", methods=["POST"])
def ruta_procesar():
    archivo = request.files.get("excel")
    origen = request.form.get("origen", "").strip()
    destino = request.form.get("destino", "").strip() or None
    sentido = request.form.get("sentido", "entrada")
    turno = request.form.get("turno", "").strip() or None

    if not archivo or archivo.filename == "":
        flash("Debes seleccionar un archivo Excel/CSV.")
        return redirect(url_for("ruta_form"))

    if not origen:
        flash("Debes indicar la dirección de origen.")
        return redirect(url_for("ruta_form"))

    filename = secure_filename(archivo.filename)
    file_path = UPLOAD_DIR / filename
    archivo.save(file_path)

    try:
        ruta = run_pipeline(
            excel_path=str(file_path),
            origin_address=origen,
            destination_address=destino,
            sentido=SentidoRuta(sentido),
            turno=turno,
        )
    except Exception as exc:
        logger.exception("Error procesando el archivo: %s", exc)
        flash(f"Error al procesar el archivo: {exc}")
        return redirect(url_for("ruta_form"))

    return render_template("resultado.html", ruta=ruta)


@app.route("/ruta/descargar/<int:ruta_id>.csv")
def ruta_descargar(ruta_id: int):
    detalle = get_route_detail(ruta_id)
    if detalle is None:
        flash("Ruta no encontrada.")
        return redirect(url_for("ruta_form"))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "orden", "identificador", "nombre", "direccion_original", "direccion_normalizada",
        "latitud", "longitud", "distancia_desde_anterior_m", "duracion_desde_anterior_s",
    ])
    for p in detalle["paradas"]:
        writer.writerow([
            p["orden"], p["identificador_pasajero"], p["nombre_pasajero"], p["direccion_original"],
            p["direccion_normalizada"], p["latitud"], p["longitud"],
            p["distancia_desde_anterior_m"], p["duracion_desde_anterior_s"],
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ruta_{ruta_id}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
