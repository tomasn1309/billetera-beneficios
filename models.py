"""Esquema y normalización de beneficios."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

CATEGORIAS = {
    "rest": "Restaurantes",
    "comida": "Comida rápida y café",
    "bencina": "Bencina",
    "salud": "Farmacia y salud",
    "entre": "Entretención",
    "compras": "Compras",
    "viajes": "Viajes",
    "finanzas": "Finanzas",
}
TODOS_LOS_DIAS = [0, 1, 2, 3, 4, 5, 6]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def dias_firma(dias: list[int]) -> str:
    if sorted(set(dias)) == TODOS_LOS_DIAS:
        return "diario"
    return "".join(str(d) for d in sorted(set(dias)))


def make_id(proveedor: str, comercio: str, dias: list[int]) -> str:
    return f"{proveedor}-{slug(comercio)}-{dias_firma(dias)}"


def _pct_value(descuento: str) -> int | None:
    if not descuento or "envío" in descuento.lower() or descuento.strip().startswith("+"):
        return None
    m = re.search(r"(\d{1,3})\s*%", descuento)
    return int(m.group(1)) if m and int(m.group(1)) <= 100 else None


def normalize(raw: dict[str, Any], proveedor: str, fuente: str) -> dict[str, Any] | None:
    """Convierte la salida del extractor en un beneficio válido, o None si no sirve."""
    comercio = (raw.get("comercio") or "").strip()
    descuento = (raw.get("descuento") or "").strip()
    if not comercio or not descuento:
        return None
    if raw.get("region_metropolitana") is False and not raw.get("online"):
        return None  # fuera de Santiago y solo presencial
    dias = sorted({int(d) for d in raw.get("dias") or [] if str(d).isdigit() and 0 <= int(d) <= 6}) or TODOS_LOS_DIAS
    cat = raw.get("categoria") if raw.get("categoria") in CATEGORIAS else "compras"
    vig = raw.get("vigencia_hasta")
    if vig and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(vig)):
        vig = None
    direcciones = [d.strip() for d in raw.get("direcciones") or [] if isinstance(d, str) and len(d.strip()) > 5][:15]
    return {
        "id": make_id(proveedor, comercio, dias),
        "proveedor": proveedor,
        "comercio": comercio[:80],
        "categoria": cat,
        "descuento": descuento[:24],
        "descuento_valor": _pct_value(descuento),
        "detalle": (raw.get("detalle") or "").strip()[:280],
        "dias": dias,
        "tarjetas": (raw.get("tarjetas") or "").strip()[:90],
        "tope": (raw.get("tope") or None),
        "canal": (raw.get("canal") or None),
        "cadena": bool(raw.get("cadena")) or (not direcciones and not raw.get("online")),
        "direcciones": direcciones,
        "ubicaciones": [],
        "vigencia_hasta": vig,
        "fuente": raw.get("url") or fuente,
    }


CAMPOS_ACTUALIZABLES = [
    "comercio", "categoria", "descuento", "descuento_valor", "detalle", "dias", "tarjetas",
    "tope", "canal", "cadena", "vigencia_hasta", "fuente", "direcciones",
]
