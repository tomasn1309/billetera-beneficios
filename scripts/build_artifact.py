"""Genera una sola página HTML autocontenida (datos + mapa SVG, sin Google Maps).

Sirve para publicarla como artifact en Claude o abrirla offline:
    python scripts/build_artifact.py  ->  dist/billetera-artifact.html
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

def main() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")
    app_markup = re.search(r"<!--APP-->(.*)<!--/APP-->", index, re.S).group(1)
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts[^>]+>', index).group(0)
    data = json.loads((ROOT / "data" / "beneficios.json").read_text(encoding="utf-8"))
    comunas = (WEB / "comunas.json").read_text(encoding="utf-8")
    def js(name):
        return (WEB / name).read_text(encoding="utf-8").replace("</script", "<\\/script")
    page = "\n".join([
        "<title>Mi Billetera de Beneficios</title>",
        fonts,
        "<style>\n" + (WEB / "styles.css").read_text(encoding="utf-8") + "\n</style>",
        app_markup,
        "<script>window.BB_DATA=" + json.dumps(data, ensure_ascii=False) + ";window.BB_COMUNAS=" + comunas + ";</script>",
        "<script>\n" + js("map-svg.js") + "\n</script>",
        "<script>\n" + js("app.js") + "\n</script>",
    ])
    out = ROOT / "dist" / "billetera-artifact.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"{out} ({len(page)//1024} KB)")

if __name__ == "__main__":
    main()
