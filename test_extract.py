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
