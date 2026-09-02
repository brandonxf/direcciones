"""Configuración centralizada del sistema, cargada desde variables de entorno (.env)."""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    nvidia_model: str = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Proveedores intercambiables (RNF-09/RNF-10). Por defecto: gratuitos, sin tarjeta.
    geocoding_provider: str = os.getenv("GEOCODING_PROVIDER", "nominatim")  # nominatim | locationiq | google
    routing_provider: str = os.getenv("ROUTING_PROVIDER", "osrm")  # osrm | google
    nominatim_url: str = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")

    # LocationIQ: alternativa a Nominatim, misma cobertura de datos (OSM) pero sin el límite
    # de 1 solicitud/segundo. Gratis, sin tarjeta — key en https://locationiq.com
    locationiq_api_key: str = os.getenv("LOCATIONIQ_API_KEY", "")
    locationiq_url: str = os.getenv("LOCATIONIQ_URL", "https://us1.locationiq.com/v1/search.php")

    # Sesgo geográfico de geocodificación: el sistema está pensado para operar en el
    # departamento del Atlántico, Colombia (Barranquilla y municipios). Restringe a Colombia
    # y prioriza resultados dentro de esta caja delimitadora (no descarta los de fuera).
    nominatim_countrycodes: str = os.getenv("NOMINATIM_COUNTRYCODES", "co")
    nominatim_viewbox: str = os.getenv("NOMINATIM_VIEWBOX", "-75.3,11.15,-74.6,10.1")
    nominatim_bounded: bool = os.getenv("NOMINATIM_BOUNDED", "0") == "1"

    database_path: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "output" / "rutas.db"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "pipeline.log"))


settings = Settings()


def configure_logging() -> None:
    """RNF-11: cada etapa del flujo debe quedar registrada en bitácoras (logs) para auditoría."""
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
