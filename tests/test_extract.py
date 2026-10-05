from types import SimpleNamespace
from pipeline.extract import chunks, extract, parse_tool_response, CHUNK
from pipeline.fetch import Page


def test_chunks_agrupa_y_parte():
    pages = [Page("u1", True, "a" * 100), Page("u2", True, "b" * (CHUNK * 2)), Page("u3", False, error="x"), Page("u4", True, "corto")]
    cs = chunks(pages)
    assert len(cs) >= 3 and all(len(c) <= CHUNK + 200 for c in cs)
    assert "u3" not in "".join(cs) and "u4" not in "".join(cs)


def test_extract_con_cliente_falso():
    calls = []

    class FakeMessages:
        def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"beneficios": [{"comercio": "Dunkin'", "descuento": "40%", "categoria": "comida", "dias": [1], "tarjetas": "CMR"}]})])

    out = extract([Page("https://x", True, "Dunkin 40% martes " * 20)], "Falabella", "CMR", "2026-10-12", client=SimpleNamespace(messages=FakeMessages()))
    assert out[0]["comercio"] == "Dunkin'"
    assert calls[0]["tool_choice"]["name"] == "registrar_beneficios"


def test_parse_sin_tool_use():
    assert parse_tool_response([SimpleNamespace(type="text", text="hola")]) == []


def test_gemini_con_http_falso(monkeypatch):
    import pipeline.extract as ex
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(ex, "GEMINI_PAUSA_S", 0)
    sent = []

    class R:
        def __init__(self, code, data): self.status_code, self._d = code, data
        def raise_for_status(self): pass
        def json(self): return self._d

    class H:
        n = 0
        def post(self, url, headers, json):
            sent.append((url, headers, json)); H.n += 1
            return R(200, {"candidates": [{"content": {"parts": [{"text": '```json\n{"beneficios":[{"comercio":"Kobo","descuento":"30%","categoria":"comida","dias":[0,1,2,3,4,5,6],"tarjetas":"Copec Pay"}]}\n```'}]}}]})

    out = ex.extract([Page("https://x", True, "Kobo 30% " * 30)], "Copec Pay", "Copec Pay", "2026-10-12", client=H(), motor="gemini")
    assert out[0]["comercio"] == "Kobo"
    assert sent[0][1]["x-goog-api-key"] == "k" and "generateContent" in sent[0][0]
    assert "JSON" in sent[0][2]["contents"][0]["parts"][0]["text"]


def test_backend_elige_gemini(monkeypatch):
    import pipeline.extract as ex
    monkeypatch.delenv("BB_EXTRACTOR", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k"); monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert ex.backend() == "gemini"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert ex.backend() == "anthropic"


def test_ordena_modelos_flash_estables_primero():
    from pipeline.extract import _ordenar_modelos
    out = _ordenar_modelos(["gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite",
                            "gemini-3-flash-preview", "gemini-2.5-flash-image", "gemini-embedding-001"])
    assert out[0] == "gemini-2.5-flash" and "gemini-2.5-pro" not in out and "gemini-2.5-flash-image" not in out
    assert out.index("gemini-2.0-flash") < out.index("gemini-2.5-flash-lite") < out.index("gemini-3-flash-preview")


def test_salta_modelo_sin_cuota(monkeypatch):
    import pipeline.extract as ex
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(ex, "GEMINI_PAUSA_S", 0)
    monkeypatch.setattr(ex, "GEMINI_MODEL", "")
    monkeypatch.setattr(ex, "_modelos", None)
    monkeypatch.setattr(ex, "_agotados", set())
    usados = []

    class R:
        def __init__(self, code, data=None, text=""): self.status_code, self._d, self.text = code, data, text
        def json(self): return self._d

    class H:
        def get(self, url, headers=None, params=None):
            return R(200, {"models": [{"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]},
                                      {"name": "models/gemini-8-flash", "supportedGenerationMethods": ["generateContent"]}]})
        def post(self, url, headers, json):
            usados.append(url)
            if "gemini-9-flash" in url:
                return R(429, text='{"error": {"message": "Quota exceeded for metric generate_content_free_tier_requests, limit: 0"}}')
            return R(200, {"candidates": [{"content": {"parts": [{"text": '{"beneficios": [{"comercio": "X"}]}'}]}}]})

    assert ex._gemini("hola", H()) == [{"comercio": "X"}]
    assert "gemini-9-flash" in usados[0] and "gemini-8-flash" in usados[1]
    assert ex._gemini("otra", H()) and "gemini-9-flash" not in usados[2]   # recuerda que estaba agotado
