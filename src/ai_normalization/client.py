"""Abstracción del proveedor de IA (RNF-09: módulos desacoplados, RNF-10: interoperabilidad).

Implementación por defecto: NVIDIA NIM (https://build.nvidia.com), que expone un endpoint
compatible con la API de OpenAI. Cambiar de proveedor solo requiere una nueva clase que
cumpla AddressNormalizerClient (p. ej. OpenAI, Azure OpenAI, un modelo local, etc.).

La IA devuelve un objeto estructurado `DireccionNormalizada` (no una sola línea de texto):
además de la dirección corregida entrega el barrio y el municipio por separado, marca si el
municipio tuvo que asumirse y emite una advertencia legible cuando la dirección es incompleta
o ambigua (la causa #1 de errores de geocodificación, ver README).
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

from openai import BadRequestError, OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models.schemas import ConfianzaNormalizacion, DireccionNormalizada

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un asistente experto en normalización de direcciones postales colombianas. "
    "El sistema opera en el departamento del Atlántico (Barranquilla, Soledad, Malambo, "
    "Puerto Colombia, Galapa, Sabanalarga y demás municipios).\n\n"
    "Recibes una dirección con posibles errores tipográficos, abreviaturas no estandarizadas "
    "o formato inconsistente. Debes devolver ÚNICAMENTE un objeto JSON válido (sin texto "
    "adicional, sin markdown, sin ```), con exactamente estas claves:\n"
    '  "direccion": string  — la dirección corregida en una sola línea, incluyendo barrio y '
    "municipio si se conocen.\n"
    '  "barrio": string|null — el barrio, urbanización o sector si aparece en el texto '
    "(nunca lo inventes).\n"
    '  "municipio": string|null — el municipio del Atlántico (o el que mencione el texto).\n'
    '  "municipio_inferido": boolean — true SOLO si el texto original no mencionaba ningún '
    "municipio y tú asumiste Barranquilla.\n"
    '  "confianza": "alta" | "media" | "baja".\n'
    '  "advertencia": string|null — nota breve para un operador humano cuando la dirección '
    "sea arriesgada de ubicar; null si no hay riesgo.\n\n"
    "Reglas para 'direccion':\n"
    "1. Expande TODAS las abreviaturas de tipo de vía a su forma completa, estén como estén "
    "(con o sin punto, mayúsculas/minúsculas, con o sin espacio antes del número):\n"
    "   - CLL / Cl / Cl. / C. / Cll / Cll. / Calle -> Calle\n"
    "   - KRA / CR / CR. / Cra / Cra. / CRA / Car / Carrera -> Carrera\n"
    "   - TV / Tv. / Tvra / TRA / Transv / Transversal -> Transversal\n"
    "   - DIAG / Dg. / Dg / Diagonal -> Diagonal\n"
    "   - AV / Av. / Ave / Avenida -> Avenida\n"
    "   - CIRC / Circ. / Circular -> Circular\n"
    "   - A.K. / AK / Avenida Carrera -> Avenida Carrera\n"
    "2. Usa siempre el símbolo # para separar el número de vía del número de placa "
    "(ej. 'Carrera 46 #82-25'), nunca 'No', 'Nro' o '#No'.\n"
    "3. Si la dirección YA menciona un municipio o ciudad, consérvalo tal cual y NO lo "
    "sustituyas ni antepongas otro distinto.\n"
    "4. Solo si NO menciona ningún municipio, usa Barranquilla y pon municipio_inferido=true.\n"
    "5. Capitalización estándar y tildes correctas. NUNCA inventes números de placa ni barrios. "
    "Si el texto no trae número de placa, deja solo la vía (ej. 'Calle 26') — NO pongas '#0-0' "
    "ni ningún relleno; baja la confianza y explícalo en 'advertencia'.\n"
    "6. Si el texto incluye un barrio/urbanización/sector, CONSÉRVALO en 'direccion' y en "
    "'barrio': es clave para diferenciar calles con el mismo nombre en distintos sectores.\n"
    "7. Transversal es una vía perpendicular a calles y carreras; nunca la conviertas en "
    "Calle ni Carrera.\n\n"
    "Reglas para 'confianza' y 'advertencia':\n"
    "- 'baja' + advertencia si: no hay número de placa, no hay barrio y el municipio es "
    "grande (Barranquilla/Soledad) donde abundan calles homónimas, o el texto es demasiado "
    "vago para ubicarlo (ej. solo un nombre de lugar).\n"
    "- 'media' + advertencia si: falta el barrio pero hay placa, o el municipio fue inferido.\n"
    "- 'alta' + advertencia=null si la dirección quedó completa (vía + placa + barrio + municipio).\n"
    "Ejemplo de salida: "
    '{"direccion": "Calle 26 #17d-23, Boulevard Sol Real, Soledad, Atlántico", '
    '"barrio": "Boulevard Sol Real", "municipio": "Soledad", "municipio_inferido": false, '
    '"confianza": "alta", "advertencia": null}'
)

# Parámetro específico de NVIDIA NIM para modelos Nemotron con razonamiento activado por defecto:
# sin esto, el modelo intercala su cadena de pensamiento con la respuesta final.
DISABLE_THINKING_EXTRA_BODY = {"chat_template_kwargs": {"thinking": False}}

_THINK_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)


class RespuestaIAIlegible(Exception):
    """La respuesta del modelo no contiene un objeto JSON con la clave 'direccion'.

    Es un fallo transitorio típico de los modelos "reasoning" (filtran su razonamiento o
    truncan): conviene reintentar la petición antes de degradar el registro.
    """


def _objetos_json_candidatos(texto: str):
    """Decodifica todo objeto JSON que empiece en cada '{' del texto (tolera texto/razonamiento
    alrededor y llaves dentro de strings). Se devuelven en orden inverso: el último objeto de
    nivel superior suele ser la respuesta final del modelo, tras su cadena de pensamiento."""
    decoder = json.JSONDecoder()
    encontrados = []
    for i, ch in enumerate(texto):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(texto, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            encontrados.append(obj)
    return list(reversed(encontrados))


def _parsear_respuesta(contenido: str, raw_address: str) -> DireccionNormalizada:
    """Extrae el objeto JSON de la respuesta del modelo, tolerando texto/razonamiento alrededor.

    Lanza `RespuestaIAIlegible` si no hay un JSON con 'direccion' — para que `normalize()`
    pueda reintentar. Solo tras agotar los reintentos se degrada el registro (RNF-13).
    """
    contenido = _THINK_BLOCK_RE.sub("", contenido or "").strip()

    datos = None
    for posible in _objetos_json_candidatos(contenido):
        if str(posible.get("direccion", "")).strip():
            datos = posible
            break

    if datos is None:
        raise RespuestaIAIlegible(
            f"Sin JSON utilizable en la respuesta para '{raw_address}': {contenido[:200]!r}"
        )

    try:
        confianza = ConfianzaNormalizacion(str(datos.get("confianza", "alta")).lower())
    except ValueError:
        confianza = ConfianzaNormalizacion.MEDIA

    def _limpio(valor) -> str | None:
        texto = str(valor).strip() if valor not in (None, "") else ""
        return texto or None

    return DireccionNormalizada(
        direccion=str(datos["direccion"]).strip(),
        barrio=_limpio(datos.get("barrio")),
        municipio=_limpio(datos.get("municipio")),
        municipio_inferido=bool(datos.get("municipio_inferido", False)),
        confianza=confianza,
        advertencia=_limpio(datos.get("advertencia")),
    )


class AddressNormalizerClient(ABC):
    """Contrato del Módulo de IA (interno) descrito en la sección 6 del documento técnico."""

    @abstractmethod
    def normalize(self, raw_address: str) -> DireccionNormalizada:
        """Devuelve la dirección normalizada y sus componentes (RF-04, RF-05)."""
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
        # Algunos modelos del catálogo NIM no aceptan response_format=json_object. Se intenta
        # una vez; si el modelo lo rechaza, se desactiva y se confía en el parseo tolerante.
        self._usar_json_mode = True

    def normalize(self, raw_address: str) -> DireccionNormalizada:
        try:
            return self._normalize_con_reintentos(raw_address)
        except Exception as exc:  # se agotaron los reintentos (incl. RespuestaIAIlegible)
            logger.warning(
                "IA no devolvió una respuesta utilizable para '%s' tras varios intentos: %s. "
                "Se degrada el registro para revisión manual.",
                raw_address, exc,
            )
            return DireccionNormalizada(
                direccion=raw_address,
                confianza=ConfianzaNormalizacion.BAJA,
                advertencia="La IA no devolvió una respuesta utilizable; revisar manualmente.",
            )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _normalize_con_reintentos(self, raw_address: str) -> DireccionNormalizada:
        kwargs = dict(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_address},
            ],
            temperature=0.0,
            max_tokens=512,
            extra_body=DISABLE_THINKING_EXTRA_BODY,
        )
        if self._usar_json_mode:
            try:
                response = self._client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs
                )
            except BadRequestError:
                logger.warning(
                    "El modelo %s no acepta response_format=json_object; se continúa sin él.",
                    self._model,
                )
                self._usar_json_mode = False
                response = self._client.chat.completions.create(**kwargs)
        else:
            response = self._client.chat.completions.create(**kwargs)
        contenido = response.choices[0].message.content or ""
        return _parsear_respuesta(contenido, raw_address)
