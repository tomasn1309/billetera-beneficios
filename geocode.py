"""Ubica los beneficios en el mapa.

Gratis por defecto (OpenStreetMap):
- Direcciones explícitas -> Nominatim (máx. 1 consulta por segundo, según su política de uso).
- Cadenas sin dirección -> Overpass API (locales con ese nombre o marca dentro de Santiago).
Si existe GOOGLE_GEOCODING_KEY se usan Google Geocoding y Places, más precisos para cadenas chicas.
Todo queda en data/geocache.json para no repetir búsquedas.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

RM_BOUNDS = {"low": {"latitude": -33.65, "longitude": -70.85}, "high": {"latitude": -33.30, "longitude": -70.45}}
SUCURSALES_MAX = 12
REFRESCO_DIAS = 60


class Geocoder:
    def __init__(self, cache_path: Path, key: str | None = None):
        self.key = key or os.environ.get("GOOGLE_GEOCODING_KEY")
        self.path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        contacto = os.environ.get("BB_CONTACTO") or ("https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "billetera-beneficios"))
        self.http = httpx.Client(timeout=60, headers={"User-Agent": f"billetera-beneficios/1.0 ({contacto})"})
        self._last = 0.0

    def _polite(self, gap: float = 1.1) -> None:
        wait = self._last + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    def _fresh(self, k: str) -> bool:
        hit = self.cache.get(k)
        return bool(hit) and hit.get("fecha", "1970-01-01") >= str(date.today() - timedelta(days=REFRESCO_DIAS))

    def address(self, addr: str) -> dict | None:
        k = "addr:" + addr.lower()
        if k in self.cache:
            return self.cache[k]["r"]
        if not self.key:
            res = self._nominatim(addr)
            self.cache[k] = {"r": res, "fecha": str(date.today())}
            return res
        r = self.http.get("https://maps.googleapis.com/maps/api/geocode/json",
                          params={"address": addr + ", Región Metropolitana, Chile", "key": self.key, "region": "cl", "language": "es"}).json()
        res = None
        if r.get("status") == "OK":
            g = r["results"][0]
            loc = g["geometry"]["location"]
            res = {"nombre": addr.split(",")[0], "direccion": g["formatted_address"].replace(", Chile", ""),
                   "lat": round(loc["lat"], 6), "lng": round(loc["lng"], 6),
                   "aprox": g["geometry"].get("location_type") not in ("ROOFTOP", "RANGE_INTERPOLATED")}
        self.cache[k] = {"r": res, "fecha": str(date.today())}
        return res

    def branches(self, comercio: str) -> list[dict]:
        k = "places:" + comercio.lower()
        if self._fresh(k):
            return self.cache[k]["r"]
        if not self.key:
            res = self._overpass(comercio)
            self.cache[k] = {"r": res, "fecha": str(date.today())}
            return res
        r = self.http.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.businessStatus"},
            json={"textQuery": f"{comercio} Santiago", "languageCode": "es", "regionCode": "CL",
                  "maxResultCount": SUCURSALES_MAX, "locationRestriction": {"rectangle": RM_BOUNDS}},
        ).json()
        res = []
        for p in r.get("places", []):
            if p.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
                continue
            name = p.get("displayName", {}).get("text", comercio)
            if comercio.split()[0].lower() not in name.lower():
                continue  # descarta resultados que no son la cadena
            res.append({"nombre": name, "direccion": p.get("formattedAddress", "").replace(", Chile", ""),
                        "lat": round(p["location"]["latitude"], 6), "lng": round(p["location"]["longitude"], 6), "aprox": False})
        self.cache[k] = {"r": res, "fecha": str(date.today())}
        return res

    # ---------- OpenStreetMap (gratis) ----------
    def _nominatim(self, addr: str) -> dict | None:
        self._polite()
        try:
            r = self.http.get("https://nominatim.openstreetmap.org/search", params={
                "q": addr + ", Región Metropolitana, Chile", "format": "jsonv2", "limit": 1, "countrycodes": "cl",
                "viewbox": "-70.85,-33.30,-70.45,-33.65", "bounded": 1, "accept-language": "es"})
            r.raise_for_status()
            hits = r.json()
        except Exception:  # noqa: BLE001
            return None
        if not hits:
            return None
        h = hits[0]
        return {"nombre": addr.split(",")[0], "direccion": h.get("display_name", addr).split(", Región Metropolitana")[0],
                "lat": round(float(h["lat"]), 6), "lng": round(float(h["lon"]), 6),
                "aprox": h.get("addresstype") not in ("building", "house", "amenity", "shop")}

    def _overpass(self, comercio: str) -> list[dict]:
        limpio = comercio.replace("'", "").replace('"', "").strip()
        name = re.sub(r"([.^$*+?()\[\]{}|])", r"\\\\\1", limpio)  # escapa para regex dentro de un string Overpass
        bbox = "-33.65,-70.85,-33.30,-70.45"
        q = (f'[out:json][timeout:60];(nwr["name"~"^{name}",i]({bbox});nwr["brand"~"^{name}",i]({bbox}););'
             f"out center {SUCURSALES_MAX * 2};")
        self._polite(2.0)
        try:
            r = self.http.post("https://overpass-api.de/api/interpreter", data={"data": q})
            r.raise_for_status()
            els = r.json().get("elements", [])
        except Exception:  # noqa: BLE001
            return []
        out: list[dict] = []
        for e in els:
            lat, lng = e.get("lat") or e.get("center", {}).get("lat"), e.get("lon") or e.get("center", {}).get("lon")
            if lat is None or any(abs(o["lat"] - lat) < 0.0005 and abs(o["lng"] - lng) < 0.0005 for o in out):
                continue
            t = e.get("tags", {})
            calle = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
            comuna = t.get("addr:city") or t.get("addr:suburb") or ""
            out.append({"nombre": t.get("name", comercio), "direccion": ", ".join(x for x in (calle, comuna) if x) or t.get("name", comercio),
                        "lat": round(lat, 6), "lng": round(lng, 6), "aprox": False})
            if len(out) >= SUCURSALES_MAX:
                break
        return out


def locate_all(beneficios: list[dict], geo: Geocoder, buscar_sucursales: bool = True) -> int:
    """Completa `ubicaciones` donde falte. Devuelve cuántos beneficios se ubicaron."""
    n = 0
    for b in beneficios:
        if b.get("ubicaciones"):
            continue
        locs = [x for x in (geo.address(a) for a in b.get("direcciones") or []) if x]
        if not locs and buscar_sucursales and b.get("cadena") and b.get("canal") not in ("Online", "App"):
            locs = geo.branches(b["comercio"].split("(")[0].strip())
        if locs:
            b["ubicaciones"] = locs
            n += 1
    return n
