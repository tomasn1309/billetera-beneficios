from pipeline.geocode import Geocoder, locate_all


class R:
    def __init__(self, d): self.d = d
    def raise_for_status(self): pass
    def json(self): return self.d


class FakeHTTP:
    def __init__(self): self.calls = []
    def post(self, url, data=None, **kw):
        self.calls.append(data["data"])
        return R({"elements": [
            {"type": "node", "lat": -33.4250, "lon": -70.6110, "tags": {"name": "Juan Maestro", "addr:street": "Av. Providencia", "addr:housenumber": "2124", "addr:city": "Providencia"}},
            {"type": "node", "lat": -33.42501, "lon": -70.61101, "tags": {"name": "Juan Maestro"}},
            {"type": "way", "center": {"lat": -33.5180, "lon": -70.5990}, "tags": {"brand": "Juan Maestro"}}]})
    def get(self, url, params=None, **kw):
        self.calls.append(params["q"])
        return R([{"lat": "-33.5186", "lon": "-70.5986", "display_name": "Mallplaza Vespucio, La Florida, Región Metropolitana de Santiago, Chile", "addresstype": "amenity"}])


def test_osm_sin_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_GEOCODING_KEY", raising=False)
    g = Geocoder(tmp_path / "c.json"); g.http = FakeHTTP(); g._polite = lambda *a: None
    bs = [{"comercio": "Juan Maestro", "cadena": True, "canal": "Presencial", "ubicaciones": [], "direcciones": []},
          {"comercio": "Tanta", "cadena": False, "ubicaciones": [], "direcciones": ["Mallplaza Vespucio, La Florida"]},
          {"comercio": "Rappi", "cadena": True, "canal": "App", "ubicaciones": [], "direcciones": []}]
    assert locate_all(bs, g) == 2
    assert len(bs[0]["ubicaciones"]) == 2 and bs[0]["ubicaciones"][0]["direccion"] == "Av. Providencia 2124, Providencia"
    assert bs[1]["ubicaciones"][0]["direccion"] == "Mallplaza Vespucio, La Florida" and bs[1]["ubicaciones"][0]["aprox"] is False
    assert bs[2]["ubicaciones"] == []
    g.save(); g2 = Geocoder(tmp_path / "c.json"); g2.http = None
    assert g2.branches("Juan Maestro")  # sale del caché sin red
    assert '"^Juan Maestro"' in g.http.calls[0] or '^Juan Maestro' in g.http.calls[-1]
