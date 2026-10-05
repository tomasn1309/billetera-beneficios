import copy
from pipeline.merge import ProviderResult, merge, report_markdown
from pipeline.models import normalize, make_id

CFG = {"min_beneficios": 2, "min_ratio": 0.4, "ausencias_para_retirar": 2, "max_detalle": 5}
HOY = "2026-10-12"


def b(prov, comercio, dias=(0,), **kw):
    x = {"id": make_id(prov, comercio, list(dias)), "proveedor": prov, "comercio": comercio, "categoria": "rest",
         "descuento": "40%", "descuento_valor": 40, "detalle": "", "dias": list(dias), "tarjetas": "CMR",
         "tope": None, "canal": "Presencial", "cadena": True, "direcciones": [], "ubicaciones": [],
         "vigencia_hasta": None, "fuente": "x", "estado": "activo", "origen": "scraper",
         "primer_visto": "2026-10-01", "ultimo_visto": "2026-10-05", "ausencias": 0, "verificado": "2026-10-05"}
    x.update(kw)
    return x


def base(items):
    return {"generado": "2026-10-05", "categorias": {}, "beneficios": items,
            "proveedores": {"fal": {"nombre": "F", "color": "fal"}, "san": {"nombre": "S", "color": "san"}}}


def test_alta_actualizacion_y_ausencia():
    prev = base([b("fal", "Tanta"), b("fal", "Dunkin", (1,)), b("fal", "Papa Johns", (1,))])
    nuevo = [b("fal", "Tanta", descuento="30%"), b("fal", "Dunkin", (1,)), b("fal", "Sushi Nuevo", (2,))]
    data, ret, rep = merge(prev, {"fal": ProviderResult(True, nuevo)}, HOY, CFG)
    ids = {x["id"]: x for x in data["beneficios"]}
    assert ids[make_id("fal", "Tanta", [0])]["descuento"] == "30%"
    assert ids[make_id("fal", "Tanta", [0])]["primer_visto"] == "2026-10-01"
    assert ids[make_id("fal", "Sushi Nuevo", [2])]["primer_visto"] == HOY
    pj = ids[make_id("fal", "Papa Johns", [1])]
    assert pj["ausencias"] == 1 and pj["verificado"] is None and pj["estado"] == "activo"
    assert [c[1] for c in rep.cambios] == [["descuento"]]
    assert not ret
    # segunda corrida sana sin Papa Johns -> baja
    data2, ret2, rep2 = merge(data, {"fal": ProviderResult(True, nuevo)}, "2026-10-19", CFG)
    assert make_id("fal", "Papa Johns", [1]) not in {x["id"] for x in data2["beneficios"]}
    assert ret2[0]["motivo_baja"] == "ya no aparece en la fuente"


def test_proveedor_caido_no_borra_nada():
    prev = base([b("fal", "Tanta"), b("fal", "Dunkin", (1,)), b("san", "Kato", (5,))])
    data, ret, rep = merge(prev, {"fal": ProviderResult(False, error="timeout"), "san": ProviderResult(True, [b("san", "Kato", (5,)), b("san", "Fork", tuple(range(7)))])}, HOY, CFG)
    assert len([x for x in data["beneficios"] if x["proveedor"] == "fal"]) == 2
    assert all(x["ausencias"] == 0 for x in data["beneficios"] if x["proveedor"] == "fal")
    assert rep.proveedores["fal"] == "timeout" and rep.proveedores["san"] == "ok"


def test_caida_brusca_se_trata_como_falla():
    prev = base([b("fal", f"Local {i}") for i in range(10)])
    data, ret, rep = merge(prev, {"fal": ProviderResult(True, [b("fal", "Local 1"), b("fal", "Local 2")])}, HOY, CFG)
    assert len(data["beneficios"]) == 10 and "cayó de 10 a 2" in rep.proveedores["fal"]


def test_vencidos_se_bajan_aunque_el_proveedor_falle():
    prev = base([b("fal", "Tanta", vigencia_hasta="2026-10-10"), b("fal", "Dunkin", (1,))])
    data, ret, rep = merge(prev, {}, HOY, CFG)
    assert [x["comercio"] for x in ret] == ["Tanta"]
    assert "venció" in ret[0]["motivo_baja"]


def test_manual_nunca_se_baja_por_ausencia():
    prev = base([b("fal", "Tanta"), b("fal", "Dunkin", (1,)), b("fal", "Mi favorito", origen="manual")])
    nuevo = [b("fal", "Tanta"), b("fal", "Dunkin", (1,))]
    for d in ("2026-10-12", "2026-10-19", "2026-10-26"):
        prev, _, _ = merge(prev, {"fal": ProviderResult(True, nuevo)}, d, CFG)
    assert "Mi favorito" in [x["comercio"] for x in prev["beneficios"]]


def test_semilla_pasa_a_scraper_sin_reportarse_como_cambio():
    prev = base([b("fal", "Tanta", origen="semilla", detalle="viejo"), b("fal", "Dunkin", (1,))])
    data, _, rep = merge(prev, {"fal": ProviderResult(True, [b("fal", "Tanta", detalle="nuevo"), b("fal", "Dunkin", (1,))])}, HOY, CFG)
    t = [x for x in data["beneficios"] if x["comercio"] == "Tanta"][0]
    assert t["origen"] == "scraper" and t["detalle"] == "nuevo" and not rep.cambios


def test_cambio_de_direccion_obliga_a_regeocodificar():
    prev = base([b("fal", "Tanta", direcciones=["A 1"], ubicaciones=[{"lat": 1, "lng": 1}]), b("fal", "Dunkin", (1,))])
    data, _, _ = merge(prev, {"fal": ProviderResult(True, [b("fal", "Tanta", direcciones=["B 2"]), b("fal", "Dunkin", (1,))])}, HOY, CFG)
    assert [x for x in data["beneficios"] if x["comercio"] == "Tanta"][0]["ubicaciones"] == []


def test_normalize():
    n = normalize({"comercio": "Dunkin'", "descuento": "40%", "categoria": "comida", "dias": [1, 1, 9], "tarjetas": "CMR"}, "fal", "u")
    assert n["dias"] == [1] and n["descuento_valor"] == 40 and n["id"] == "fal-dunkin-1"
    assert normalize({"comercio": "X", "descuento": "90% envío", "dias": []}, "ent", "u")["descuento_valor"] is None
    assert normalize({"comercio": "X", "descuento": "20%", "region_metropolitana": False}, "fal", "u") is None
    assert normalize({"comercio": "", "descuento": "20%"}, "fal", "u") is None
    assert normalize({"comercio": "Y", "descuento": "20%", "categoria": "otra"}, "fal", "u")["categoria"] == "compras"


def test_reporte():
    prev = base([b("fal", "Tanta"), b("fal", "Dunkin", (1,))])
    _, _, rep = merge(prev, {"fal": ProviderResult(True, [b("fal", "Tanta"), b("fal", "Dunkin", (1,)), b("fal", "Nuevo", (3,))])}, HOY, CFG)
    md = report_markdown(rep, HOY)
    assert "Nuevos (1)" in md and "Nuevo" in md
