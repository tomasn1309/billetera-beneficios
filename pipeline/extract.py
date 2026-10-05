"""Convierte el texto de las páginas en beneficios estructurados usando la API de Claude.

Usar un modelo en vez de selectores CSS hace que el pipeline siga funcionando cuando un banco
rediseña su sitio: solo depende de que el texto del beneficio siga visible en la página.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable

from .fetch import Page
from .models import CATEGORIAS

CHUNK = 30000
# Motor de extracción: "gemini" (gratis con una key de Google AI Studio) o "anthropic" (pagado).
# Por defecto usa el que tenga key disponible, prefiriendo Gemini.
GEMINI_MODEL = os.environ.get("BB_GEMINI_MODEL", "gemini-flash-latest")
ANTHROPIC_MODEL = os.environ.get("BB_MODEL", "claude-sonnet-5-5")
GEMINI_PAUSA_S = float(os.environ.get("BB_GEMINI_PAUSA", "7"))  # respeta ~10 solicitudes/minuto del plan gratis

TOOL = {
    "name": "registrar_beneficios",
    "description": "Registra los beneficios vigentes encontrados en las páginas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "beneficios": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "comercio": {"type": "string", "description": "Nombre del comercio o programa, sin el porcentaje."},
                        "categoria": {"type": "string", "enum": list(CATEGORIAS)},
                        "descuento": {"type": "string", "description": "Muy corto: '40%', 'hasta 30%', '$100/L', '6 cuotas s/i', '2x1'."},
                        "detalle": {"type": "string", "description": "Una o dos frases con condiciones clave (horario, exclusiones, cómo activarlo)."},
                        "dias": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6},
                                 "description": "0=lunes … 6=domingo. Todos si aplica todos los días."},
                        "tarjetas": {"type": "string", "description": "Qué tarjeta o tipo de cliente lo obtiene."},
                        "tope": {"type": ["string", "null"]},
                        "canal": {"type": ["string", "null"], "description": "Presencial, Online, App, o combinación."},
                        "online": {"type": "boolean"},
                        "vigencia_hasta": {"type": ["string", "null"], "description": "YYYY-MM-DD si la página lo indica."},
                        "cadena": {"type": "boolean", "description": "true si aplica en muchos locales de una cadena."},
                        "direcciones": {"type": "array", "items": {"type": "string"},
                                        "description": "Direcciones o locales específicos con comuna, si la página los nombra."},
                        "region_metropolitana": {"type": "boolean", "description": "false si es solo para regiones fuera de Santiago."},
                        "url": {"type": ["string", "null"], "description": "URL de la página donde aparece."},
                    },
                    "required": ["comercio", "categoria", "descuento", "dias", "tarjetas"],
                },
            }
        },
        "required": ["beneficios"],
    },
}

PROMPT = """Eres un extractor de datos. Hoy es {hoy}. Abajo está el texto de páginas públicas de beneficios de {proveedor}.
El usuario tiene: {tarjetas}.

Extrae SOLO beneficios concretos y vigentes (descuentos, cashback, cuotas sin interés, rebajas en combustible, etc.) que el usuario pueda usar.
- Ignora beneficios ya vencidos, menús de navegación, publicidad de productos financieros y requisitos legales genéricos.
- Si un mismo comercio tiene condiciones distintas según el día, registra una fila por cada combinación.
- Si la página dice "todos los días" o no menciona días, usa los 7 días.
- No inventes datos: si algo no aparece, déjalo vacío o null.
{salida}

{paginas}"""


def chunks(pages: Iterable[Page]) -> list[str]:
    out, cur = [], ""
    for p in pages:
        if not p.ok or len(p.text.strip()) < 80:
            continue
        block = f"=== {p.url} ===\n{p.text.strip()}\n\n"
        while len(block) > CHUNK:  # páginas enormes se parten
            out.append(block[:CHUNK])
            block = f"=== {p.url} (cont.) ===\n" + block[CHUNK - 1500:]
        if len(cur) + len(block) > CHUNK and cur:
            out.append(cur)
            cur = ""
        cur += block
    if cur:
        out.append(cur)
    return out


def parse_tool_response(content: list[Any]) -> list[dict]:
    for block in content:
        btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if btype == "tool_use":
            inp = getattr(block, "input", None) or block.get("input")
            if isinstance(inp, str):
                inp = json.loads(inp)
            return list(inp.get("beneficios", []))
    return []


SALIDA_TOOL = "Llama a la herramienta registrar_beneficios una sola vez con todos los resultados."
SALIDA_JSON = ('Responde SOLO con un objeto JSON de la forma {"beneficios": [ ... ]}, donde cada elemento tiene estos campos: '
               + json.dumps(TOOL["input_schema"]["properties"]["beneficios"]["items"]["properties"], ensure_ascii=False))


def backend() -> str:
    pedido = os.environ.get("BB_EXTRACTOR", "").lower()
    if pedido in ("gemini", "anthropic"):
        return pedido
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError("Falta GEMINI_API_KEY (gratis en aistudio.google.com) o ANTHROPIC_API_KEY.")


def parse_json_text(text: str) -> list[dict]:
    """Lee {"beneficios": [...]} aunque venga envuelto en ```json ... ``` o con texto alrededor."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return []
    obj = json.loads(text[start:end + 1])
    return list(obj.get("beneficios", [])) if isinstance(obj, dict) else []


def _gemini(prompt: str, http=None) -> list[dict]:
    import time
    import httpx
    http = http or httpx.Client(timeout=180)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 16000}}
    for intento in range(5):
        r = http.post(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, json=body)
        if r.status_code in (429, 500, 503):
            time.sleep(20 * (intento + 1))
            continue
        r.raise_for_status()
        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        time.sleep(GEMINI_PAUSA_S)
        return parse_json_text("".join(p.get("text", "") for p in parts))
    raise RuntimeError("Gemini no respondió tras 5 intentos (límite del plan gratis).")


def _anthropic(prompt: str, client=None) -> list[dict]:
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    msg = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=16000, tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_tool_response(msg.content)


def extract(pages: list[Page], proveedor: str, tarjetas: str, hoy: str, client=None, motor: str | None = None) -> list[dict]:
    motor = motor or ("anthropic" if client is not None else backend())
    items: list[dict] = []
    for text in chunks(pages):
        salida = SALIDA_TOOL if motor == "anthropic" else SALIDA_JSON
        prompt = PROMPT.format(hoy=hoy, proveedor=proveedor, tarjetas=tarjetas, paginas=text, salida=salida)
        items.extend(_anthropic(prompt, client) if motor == "anthropic" else _gemini(prompt, client))
    return items
