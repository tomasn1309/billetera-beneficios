"""Fusiona una corrida nueva con los datos publicados: altas, actualizaciones y bajas.

Reglas (todas puras, sin red, cubiertas por tests):
- Un proveedor cuya corrida falla o trae muy pocos beneficios NO toca sus datos (se reporta).
- Un beneficio visto de nuevo se actualiza y queda verificado hoy.
- Un beneficio que no aparece suma una ausencia y deja de estar verificado; tras N ausencias
  en corridas sanas se da de baja.
- Un beneficio con vigencia vencida se da de baja siempre.
- Los beneficios con origen "manual" (data/manual.json) nunca se dan de baja por ausencia.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

from .models import CAMPOS_ACTUALIZABLES


@dataclass
class ProviderResult:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class Report:
    altas: list[dict] = field(default_factory=list)
    bajas: list[dict] = field(default_factory=list)
    cambios: list[tuple[dict, list[str]]] = field(default_factory=list)
    sin_confirmar: list[dict] = field(default_factory=list)
    proveedores: dict[str, str] = field(default_factory=dict)  # prov -> "ok" | motivo de falla

    @property
    def hay_cambios(self) -> bool:
        return bool(self.altas or self.bajas or self.cambios)


def is_healthy(result: ProviderResult | None, prev_count: int, cfg: dict) -> tuple[bool, str]:
    if result is None:
        return False, "no se ejecutó"
    if not result.ok:
        return False, result.error or "error desconocido"
    n = len(result.items)
    if n < cfg["min_beneficios"]:
        return False, f"solo {n} beneficios (mínimo {cfg['min_beneficios']})"
    if prev_count and n < math.ceil(cfg["min_ratio"] * prev_count):
        return False, f"cayó de {prev_count} a {n} beneficios; se conservan los datos anteriores"
    return True, "ok"


def merge(prev: dict, results: dict[str, ProviderResult], today: str, cfg: dict,
          manual: list[dict] | None = None) -> tuple[dict, list[dict], Report]:
    data = copy.deepcopy(prev)
    rep = Report()
    out: list[dict] = []
    retired: list[dict] = []
    by_prov: dict[str, list[dict]] = {}
    for b in data["beneficios"]:
        by_prov.setdefault(b["proveedor"], []).append(b)

    for prov in data["proveedores"]:
        prev_items = by_prov.get(prov, [])
        auto_prev = [b for b in prev_items if b.get("origen") != "manual"]
        res = results.get(prov)
        healthy, why = is_healthy(res, len(auto_prev), cfg)
        rep.proveedores[prov] = why
        if not healthy:
            out.extend(prev_items)
            continue
        data["proveedores"][prov]["ultima_actualizacion_ok"] = today
        fresh = {}
        for it in res.items:
            fresh.setdefault(it["id"], it)  # primera aparición gana
        for b in prev_items:
            if b.get("origen") == "manual":
                out.append(b)
                continue
            nb = fresh.pop(b["id"], None)
            if nb is not None:
                changed = [k for k in CAMPOS_ACTUALIZABLES if k in nb and nb[k] != b.get(k)]
                for k in changed:
                    b[k] = nb[k]
                if "direcciones" in changed:
                    b["ubicaciones"] = []  # se vuelven a geocodificar
                if changed and b.get("origen") != "semilla":
                    rep.cambios.append((b, changed))
                b.update(ultimo_visto=today, verificado=today, ausencias=0, estado="activo")
                if b.get("origen") == "semilla":
                    b["origen"] = "scraper"
                out.append(b)
            else:
                b["ausencias"] = b.get("ausencias", 0) + 1
                b["verificado"] = None
                if b["ausencias"] >= cfg["ausencias_para_retirar"]:
                    b.update(estado="retirado", retirado=today, motivo_baja="ya no aparece en la fuente")
                    retired.append(b)
                    rep.bajas.append(b)
                else:
                    rep.sin_confirmar.append(b)
                    out.append(b)
        for nb in fresh.values():
            nb.update(estado="activo", primer_visto=today, ultimo_visto=today, verificado=today,
                      ausencias=0, origen="scraper")
            nb.setdefault("ubicaciones", [])
            out.append(nb)
            rep.altas.append(nb)

    # beneficios manuales nuevos (o editados) desde data/manual.json
    if manual:
        ids = {b["id"]: i for i, b in enumerate(out)}
        for m in manual:
            m = {**m, "origen": "manual", "estado": "activo"}
            m.setdefault("primer_visto", today)
            m.setdefault("ubicaciones", [])
            if m["id"] in ids:
                old = out[ids[m["id"]]]
                m["ubicaciones"] = m["ubicaciones"] or old.get("ubicaciones", [])
                m["primer_visto"] = old.get("primer_visto", today)
                out[ids[m["id"]]] = m
            else:
                out.append(m)
                rep.altas.append(m)

    # vencidos
    keep = []
    for b in out:
        if b.get("vigencia_hasta") and b["vigencia_hasta"] < today:
            b.update(estado="retirado", retirado=today, motivo_baja=f"venció el {b['vigencia_hasta']}")
            retired.append(b)
            rep.bajas.append(b)
        else:
            keep.append(b)

    data["beneficios"] = sorted(keep, key=lambda b: (b["proveedor"], b["comercio"].lower(), b["id"]))
    data["generado"] = today
    return data, retired, rep


def report_markdown(rep: Report, today: str) -> str:
    L = [f"# Actualización de beneficios, {today}", ""]
    L.append("## Estado por proveedor")
    for p, s in rep.proveedores.items():
        L.append(f"- **{p}**: {'✅ ok' if s == 'ok' else '⚠️ ' + s}")
    def sec(title, items, fmt):
        if items:
            L.extend(["", f"## {title} ({len(items)})"] + [fmt(x) for x in items])
    sec("Nuevos", rep.altas, lambda b: f"- {b['proveedor']} · {b['comercio']}: {b['descuento']}")
    sec("Dados de baja", rep.bajas, lambda b: f"- {b['proveedor']} · {b['comercio']}: {b.get('motivo_baja','')}")
    sec("Modificados", rep.cambios, lambda c: f"- {c[0]['proveedor']} · {c[0]['comercio']}: {', '.join(c[1])}")
    sec("No vistos en esta corrida (se bajan si faltan otra vez)", rep.sin_confirmar, lambda b: f"- {b['proveedor']} · {b['comercio']}")
    if not rep.hay_cambios:
        L += ["", "Sin cambios en los beneficios."]
    return "\n".join(L) + "\n"
