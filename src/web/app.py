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
import json
import logging
import time
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from src.config import BASE_DIR, configure_logging
from src.export.excel_exporter import export_passengers_to_excel, summarize
from src.models.schemas import SentidoRuta
from src.persistence.database import init_db
from src.persistence.repository import get_route_detail, get_route_history
from src.pipeline import run_geocoding_pipeline, run_pipeline

configure_logging()
logger = logging.getLogger(__name__)

init_db()

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


@app.route("/geocodificar/progreso", methods=["POST"])
def geocodificar_progreso():
    """Mismo flujo que `/geocodificar` pero transmitiendo progreso en tiempo real vía SSE."""
    archivo = request.files.get("excel")
    if not archivo or archivo.filename == "":
        flash("Debes seleccionar un archivo Excel/CSV.")
        return redirect(url_for("index"))

    filename = secure_filename(archivo.filename)
    upload_path = UPLOAD_DIR / filename
    archivo.save(upload_path)

    from queue import Empty, Queue
    from flask import stream_with_context

    cola = Queue()

    def _en_cola(datos: dict) -> None:
        cola.put(("evento", datos))

    def _cerrar() -> None:
        cola.put(("fin", None))

    def _emit():
        def _geo_progreso(i: int, total: int, pasajero):
            _en_cola({
                "tipo": "progreso",
                "indice": i,
                "total": total,
                "identificador": pasajero.identificador,
                "nombre": pasajero.nombre,
                "direccion": pasajero.direccion_normalizada or pasajero.direccion_original,
                "latitud": pasajero.latitud,
                "longitud": pasajero.longitud,
                "estado": pasajero.estado.value,
                "nota_precision": pasajero.nota_precision,
            })

        def _log_linea(mensaje: str):
            # Emite eventos de fase / limpieza / log a partir de las líneas del pipeline.
            if mensaje.startswith("=== Fase"):
                _en_cola({"tipo": "fase", "titulo": mensaje.strip("= ").strip()})
                return
            if mensaje.startswith("Limpieza"):
                # "Limpieza i/total: nombre (direccion)"
                cabecera, resto = mensaje.split(": ", 1)
                i_total = cabecera.split()[1]
                indice, total = i_total.split("/")
                nombre = resto.split(" (", 1)[0]
                if " (" in resto:
                    direccion = resto.split(" (", 1)[1].rstrip(")")
                else:
                    direccion = ""
                _en_cola({
                    "tipo": "progreso_limpieza",
                    "indice": int(indice),
                    "total": int(total),
                    "nombre": nombre,
                    "direccion": direccion,
                })
                return
            # Cualquier otra línea de log que deba mostrarse
            _en_cola({"tipo": "log", "mensaje": mensaje})

        # Se dispara el procesamiento en un hilo de fondo; el generador principal
        # entrega los eventos de la cola mientras llegan.
        import threading
        def _trabajo():
            try:
                passengers = run_geocoding_pipeline(
                    str(upload_path),
                    progress_callback=_geo_progreso,
                    log_callback=_log_linea,
                )
            except Exception as exc:
                logger.exception("Error procesando el archivo: %s", exc)
                _en_cola({"tipo": "error", "mensaje": str(exc)})
                _cerrar()
                return

            stem = Path(filename).stem
            output_filename = f"{stem}_geocodificado_{int(time.time())}.xlsx"
            export_passengers_to_excel(passengers, OUTPUT_DIR / output_filename)
            _en_cola({"tipo": "fin", "archivo": output_filename, "resumen": summarize(passengers)})
            _cerrar()

        threading.Thread(target=_trabajo, daemon=True).start()

        yield "retry: 2000\n\n"
        while True:
            try:
                marca, datos = cola.get(timeout=1.0)
            except Empty:
                continue
            if marca == "fin":
                break
            yield f"data: {json.dumps(datos, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(_emit()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
