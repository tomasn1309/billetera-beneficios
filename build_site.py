"""Arma el sitio estático en _site/ (web + datos + config.js).

Uso local:  GOOGLE_MAPS_KEY=tu_key python scripts/build_site.py && python -m http.server -d _site 8000
En GitHub Actions lo llama el workflow de despliegue.
"""
import json, os, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"

def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "web", OUT, ignore=shutil.ignore_patterns("config.example.js", "config.js"))
    (OUT / "data").mkdir()
    for name in ("beneficios.json", "retirados.json"):
        shutil.copy(ROOT / "data" / name, OUT / "data" / name)
    key = os.environ.get("GOOGLE_MAPS_KEY", "")
    local_cfg = ROOT / "web" / "config.js"
    if not key and local_cfg.exists():
        shutil.copy(local_cfg, OUT / "config.js")
    else:
        (OUT / "config.js").write_text("window.BB_CONFIG = " + json.dumps({"googleMapsKey": key}) + ";\n", encoding="utf-8")
    print(f"Sitio listo en {OUT} ({'con' if key or local_cfg.exists() else 'sin'} Google Maps)")

if __name__ == "__main__":
    main()
