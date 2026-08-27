"""Abstracción del proveedor de IA (RNF-09: módulos desacoplados, RNF-10: interoperabilidad).

Implementación por defecto: NVIDIA NIM (https://build.nvidia.com), que expone un endpoint
compatible con la API de OpenAI. Cambiar de proveedor solo requiere una nueva clase que
cumpla AddressNormalizerClient (p. ej. OpenAI, Azure OpenAI, un modelo local, etc.).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un asistente experto en normalización de direcciones postales colombianas. "
    "El sistema opera en el departamento del Atlántico (Barranquilla, Soledad, Malambo, "
    "Puerto Colombia, Galapa, Sabanalarga y demás municipios).\n\n"
    "Recibes una dirección con posibles errores tipográficos, abreviaturas no estandarizadas "
    "o formato inconsistente, y debes devolver ÚNICAMENTE la dirección corregida, sin "
    "explicaciones adicionales, sin comillas y en una sola línea. Si no puedes mejorarla, "
    "devuelve la dirección original.\n\n"
    "Reglas obligatorias:\n"
    "1. Expande las abreviaturas de vía a su forma completa: Cll/Cl -> Calle, "
    "Kra/Cra/Cr -> Carrera, Trans/Tv -> Transversal, Diag -> Diagonal, Av -> Avenida, "
    "Circ -> Circular.\n"
    "2. Usa siempre el símbolo # para separar el número de vía del número de placa "
    "(ej. 'Carrera 46 #82-25'), nunca 'No', 'Nro' o '#No'.\n"
    "3. Si la dirección YA menciona un municipio o ciudad (Barranquilla, Soledad, Malambo, "
    "Puerto Colombia, Galapa, Sabanalarga, etc.), consérvalo tal cual y NO agregues ni "
    "antepongas otro municipio distinto.\n"
    "4. Solo si la dirección NO menciona ningún municipio, agrega ', Barranquilla, Atlántico' "
    "al final.\n"
    "5. Usa capitalización estándar y tildes correctas. No inventes números de placa ni "
    "barrios que no estén en el texto original.\n"
    "6. Si el texto incluye un barrio, urbanización o sector (a veces al final, separado por "
    "coma), CONSÉRVALO siempre en el resultado: es clave para diferenciar calles con el mismo "
    "nombre en distintos sectores de un mismo municipio (muy común en el Atlántico)."
)

# Parámetro específico de NVIDIA NIM para modelos Nemotron con razonamiento activado por defecto:
# sin esto, el modelo intercala su cadena de pensamiento con la respuesta final.
DISABLE_THINKING_EXTRA_BODY = {"chat_template_kwargs": {"thinking": False}}


class AddressNormalizerClient(ABC):
    """Contrato del Módulo de IA (interno) descrito en la sección 6 del documento técnico."""

    @abstractmethod
    def normalize(self, raw_address: str) -> str:
        """Devuelve la dirección normalizada (RF-04, RF-05)."""
        raise NotImplementedError


class NvidiaAddressNormalizer(AddressNormalizerClient):
    def __init__(self) -> None:
        if not settings.nvidia_api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY no está configurada. Define la variable de entorno en tu archivo .env "
                "(obtén la key en https://build.nvidia.com)."
            )
        self._client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
        )
        self._model = settings.nvidia_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def normalize(self, raw_address: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_address},
            ],
            temperature=0.0,
            max_tokens=200,
            extra_body=DISABLE_THINKING_EXTRA_BODY,
        )
        normalized = (response.choices[0].message.content or "").strip()
        return normalized or raw_address
