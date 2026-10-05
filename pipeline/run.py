"""Corrida completa: descargar -> extraer -> fusionar -> ubicar -> guardar -> reportar.

    python -m pipeline.run                    # todos los proveedores
    python -m pipeline.run --solo fal,cop     # algunos
    python -m pipeline.run --dry-run          # no escribe data/
    python -m pipeline.run --desde-cache      # reusa data/raw (no descarga)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .fetch import Page, fetch_provider
from .merge import ProviderResult, merge, report_markdown
from .models import normalize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def dump_json(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run_provider(key: str, src: dict, cfg: dict, hoy: str, desde_cache: bool) -> ProviderResult:
    raw_dir = DATA / "raw" / key
    try:
        if desde_cache and (raw_dir / "pages.json").exists():
            pages = [Page(**p) for p in load_json(raw_dir / "pages.json", [])]
        else:
            pages = asyncio.run(fetch_provider(src["inicio"], src.get("seguir"), cfg["max_detalle"]))
            if not any(p.ok for p in pages) and src.get("alternativas"):
                print(f"  sitio oficial no disponible; usando fuente alternativa", flush=True)
                pages += asyncio.run(fetch_provider(src["alternativas"], None, 0))
            raw_dir.mkdir(parents=True, exist_ok=True)
            dump_json(raw_dir / "pages.json", [p.__dict__ for p in pages])
        ok_pages = [p for p in pages if p.ok]
        if not ok_pages:
            errs = "; ".join(f"{p.url}: {p.error}" for p in pages)
            return ProviderResult(False, error=f"ninguna página descargó ({errs})"[:400])
        from .extract import extract
        raw_items = extract(ok_pages, src["nombre"], src["tarjetas_del_usuario"], hoy)
        dump_json(raw_dir / "extraidos.json", raw_items)
        items = [x for x in (normalize(r, key, src["inicio"][0]) for r in raw_items) if x]
        return ProviderResult(True, items)
    except Exception as e:  # noqa: BLE001 — un proveedor caído no debe botar la corrida
        return ProviderResult(False, error=f"{type(e).__name__}: {e}"[:400])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="proveedores separados por coma")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--desde-cache", action="store_true")
    ap.add_argument("--sin-geocoding", action="store_true")
    a = ap.parse_args(argv)

    hoy = datetime.now(ZoneInfo("America/Santiago")).date().isoformat()
    sources = yaml.safe_load((ROOT / "pipeline" / "sources.yaml").read_text(encoding="utf-8"))
    cfg = sources["defaults"]
    provs = sources["proveedores"]
    keys = a.solo.split(",") if a.solo else list(provs)

    prev = load_json(DATA / "beneficios.json", None)
    if prev is None:
        prev = {"generado": hoy, "categorias": {}, "beneficios": [],
                "proveedores": {k: {"nombre": v["nombre"], "color": v["color"], "fuente": v["inicio"][0]} for k, v in provs.items()}}
    results = {}
    for k in keys:
        print(f"→ {k}: descargando y extrayendo…", flush=True)
        results[k] = run_provider(k, provs[k], cfg, hoy, a.desde_cache)
        r = results[k]
        print(f"  {'ok' if r.ok else 'FALLA'}: {len(r.items)} beneficios {'' if r.ok else '— ' + (r.error or '')}", flush=True)
    # proveedores no pedidos con --solo: se tratan como "no ejecutados" pero sin alarma
    manual = load_json(DATA / "manual.json", {"beneficios": []})["beneficios"]
    data, retired, rep = merge(prev, results, hoy, cfg, manual)
    for k in provs:
        if k not in keys:
            rep.proveedores[k] = "no incluido en esta corrida"

    if not a.sin_geocoding:
        from .geocode import Geocoder, locate_all
        geo = Geocoder(DATA / "geocache.json")
        n = locate_all(data["beneficios"], geo)
        if not a.dry_run:
            geo.save()
        print(f"  geocodificados: {n}")

    md = report_markdown(rep, hoy)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(md, encoding="utf-8")

    # estado de salud: cuenta fallas consecutivas para abrir un issue desde el workflow
    estado = load_json(DATA / "estado.json", {"proveedores": {}})
    for k, s in rep.proveedores.items():
        e = estado["proveedores"].setdefault(k, {"fallas_consecutivas": 0})
        if s == "ok":
            e.update(fallas_consecutivas=0, ultimo_ok=hoy, ultimo_error=None)
        elif k in keys:
            e["fallas_consecutivas"] += 1
            e["ultimo_error"] = s
    estado["ultima_corrida"] = hoy

    if a.dry_run:
        print("(dry-run: no se escribió nada)")
        return 0
    dump_json(DATA / "beneficios.json", data)
    hist = load_json(DATA / "retirados.json", {"beneficios": []})
    hist["beneficios"] = (retired + hist["beneficios"])[:500]
    dump_json(DATA / "retirados.json", hist)
    dump_json(DATA / "estado.json", estado)
    (DATA / "cambios").mkdir(exist_ok=True)
    (DATA / "cambios" / f"{hoy}.md").write_text(md, encoding="utf-8")
    alertas = [k for k, e in estado["proveedores"].items() if e["fallas_consecutivas"] >= 2]
    if alertas:
        (DATA / "ALERTA.txt").write_text(
            "Proveedores con 2+ corridas fallidas seguidas: " + ", ".join(
                f"{k} ({estado['proveedores'][k]['ultimo_error']})" for k in alertas) + "\n", encoding="utf-8")
    elif (DATA / "ALERTA.txt").exists():
        (DATA / "ALERTA.txt").unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
