"""Fase 3: IA híbrida (Ollama → Vertex Gemini → reglas), topes, caché y análisis profundo."""
import httpx
import pytest

from centinela import analisis, ia, rutas

CONTROL = {"x-centinela-control": "control-prueba"}


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
    def json(self):
        return self._d
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


def gemini(texto, tin=100, tout=20):
    return Resp({"candidates": [{"content": {"parts": [{"text": "pensando...", "thought": True}, {"text": texto}]}}],
                 "usageMetadata": {"promptTokenCount": tin, "candidatesTokenCount": tout}})


@pytest.fixture
def vertex(monkeypatch):
    """Vertex encendido con topes chicos y una API de Google simulada."""
    monkeypatch.setattr(ia, "VERTEX_ACTIVO", True)
    monkeypatch.setattr(ia, "VERTEX_PROYECTO", "proyecto-prueba")
    monkeypatch.setattr(ia, "VERTEX_MAX_HORA", 3)
    monkeypatch.setattr(ia, "VERTEX_MAX_DIA", 5)
    monkeypatch.setattr(ia, "VERTEX_MAX_PROFUNDO_DIA", 1)
    monkeypatch.setattr(ia, "_token", lambda: "token-prueba")
    monkeypatch.setattr(ia, "ollama_disponible", lambda *a, **k: False)
    ia._llamadas.clear(); ia._profundas.clear(); ia._cache.clear(); ia._uso.clear()
    llamadas = []

    def post(url, json=None, timeout=None, headers=None, **k):
        llamadas.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return gemini("respuesta de gemini")
    monkeypatch.setattr(ia.httpx, "post", post)
    yield llamadas
    ia._llamadas.clear(); ia._profundas.clear(); ia._cache.clear(); ia._uso.clear()


def test_url_global_y_regional(monkeypatch):
    monkeypatch.setattr(ia, "VERTEX_PROYECTO", "p")
    monkeypatch.setattr(ia, "VERTEX_MODELO", "gemini-3.8-flash")
    monkeypatch.setattr(ia, "VERTEX_REGION", "global")
    assert ia._url_vertex() == "https://aiplatform.googleapis.com/v1/projects/p/locations/global/publishers/google/models/gemini-3.8-flash:generateContent"
    monkeypatch.setattr(ia, "VERTEX_REGION", "us-east1")
    assert ia._url_vertex().startswith("https://us-east1-aiplatform.googleapis.com/v1/projects/p/locations/us-east1/")


def test_vertex_apagado_por_defecto():
    assert ia.VERTEX_ACTIVO is False          # en los tests no hay VERTEX_PROYECTO (igual que en JP)
    with pytest.raises(ia.SinIA):
        ia.vertex_chat("s", "u")


def test_hibrido_usa_vertex_si_ollama_no_esta(vertex):
    txt, fuente = ia.ia_generar("sistema", "hola", tipo="chat")
    assert (txt, fuente) == ("respuesta de gemini", "vertex")   # sin el "pensamiento"
    assert vertex[0]["headers"]["Authorization"] == "Bearer token-prueba"
    assert vertex[0]["json"]["systemInstruction"]["parts"][0]["text"] == "sistema"


def test_hibrido_prefiere_ollama(vertex, monkeypatch):
    monkeypatch.setattr(ia, "ollama_disponible", lambda *a, **k: True)
    monkeypatch.setattr(ia, "ollama_chat", lambda *a, **k: "respuesta local")
    assert ia.ia_generar("s", "u") == ("respuesta local", "ollama")
    assert vertex == []                                           # Gemini no se tocó


def test_si_ollama_falla_pasa_a_vertex(vertex, monkeypatch):
    monkeypatch.setattr(ia, "ollama_disponible", lambda *a, **k: True)
    def falla(*a, **k):
        raise httpx.ConnectError("lenovo apagado")
    monkeypatch.setattr(ia, "ollama_chat", falla)
    assert ia.ia_generar("s", "u")[1] == "vertex"


def test_cache_no_repite_la_llamada(vertex):
    ia.vertex_chat("s", "misma pregunta")
    ia.vertex_chat("s", "misma pregunta")
    assert len(vertex) == 1
    assert ia._uso and any(k[3] == "cache" for k in ia._uso)


def test_tope_por_hora(vertex):
    for i in range(3):
        ia.vertex_chat("s", f"pregunta {i}")
    with pytest.raises(ia.SinIA):
        ia.vertex_chat("s", "una más")
    assert len(vertex) == 3
    assert not ia.vertex_puede()


def test_error_de_vertex_es_sin_ia(vertex, monkeypatch):
    monkeypatch.setattr(ia.httpx, "post", lambda *a, **k: Resp({}, 429))
    with pytest.raises(ia.SinIA):
        ia.vertex_chat("s", "u")
    assert any(k[3] == "error" for k in ia._uso)


def test_chat_con_vertex_por_la_api(cliente, gw, vertex, monkeypatch):
    monkeypatch.setattr(rutas, "ia_disponible", ia.ia_disponible)
    monkeypatch.setattr(rutas, "q", lambda *a, **k: {"numeros": 1, "reportes_24h": 0})
    r = cliente.post("/api/chat", json={"mensaje": "me llamaron del banco pidiendo la clave"}, headers=gw).json()
    assert r["fuente"] == "vertex" and r["respuesta"] == "respuesta de gemini"


def test_chat_sin_cupo_responde_por_reglas(cliente, gw, vertex, monkeypatch):
    monkeypatch.setattr(ia, "VERTEX_MAX_HORA", 0)
    monkeypatch.setattr(rutas, "ia_disponible", ia.ia_disponible)
    monkeypatch.setattr(rutas, "q", lambda *a, **k: None)
    r = cliente.post("/api/chat", json={"mensaje": "me llamaron del banco pidiendo la clave"}, headers=gw).json()
    assert r["fuente"] == "reglas"


# ---------- análisis profundo ----------

def test_anonimizar_quita_telefonos():
    t = analisis.anonimizar("me llamó el 300 123 4567 y luego +57 (1) 555-0101 pidiendo la clave")
    assert "300" not in t and "555" not in t and t.count("[número]") == 2


def test_analisis_profundo_con_vertex_y_cache(vertex, monkeypatch):
    monkeypatch.setattr(analisis, "_datos_campanas", lambda: {"numeros": [{"numero": "+573001234567", "personas": 4}]})
    monkeypatch.setattr(analisis, "evento", lambda *a, **k: None)
    monkeypatch.setattr(ia.httpx, "post", lambda url, json=None, **k: vertex.append(json) or gemini('{"campanas": [], "resumen": "Sin campañas"}'))
    analisis._cache.clear()
    r1 = analisis.analisis_profundo("campanas")
    r2 = analisis.analisis_profundo("campanas")
    assert r1["fuente"] == "vertex" and r1["resultado"]["resumen"] == "Sin campañas"
    assert r2["desde_cache"] is True and len(vertex) == 1
    analisis._cache.clear()


def test_analisis_profundo_sin_ia(monkeypatch):
    monkeypatch.setattr(analisis, "_datos_semanal", lambda: {})
    monkeypatch.setattr(analisis, "vertex_puede", lambda **k: False)
    monkeypatch.setattr(analisis, "ollama_disponible", lambda: False)
    analisis._cache.clear()
    with pytest.raises(ia.SinIA):
        analisis.analisis_profundo("semanal")


def test_ruta_analisis_protegida_y_validada(cliente, gw, monkeypatch):
    assert cliente.post("/api/interno/analisis?tipo=campanas", headers=gw).status_code == 401
    assert cliente.post("/api/interno/analisis?tipo=otro", headers={**gw, **CONTROL}).status_code == 422
    monkeypatch.setattr(rutas, "analisis_profundo", lambda t: (_ for _ in ()).throw(ia.SinIA("x")))
    assert cliente.post("/api/interno/analisis?tipo=semanal", headers={**gw, **CONTROL}).status_code == 503
    monkeypatch.setattr(rutas, "analisis_profundo", lambda t: {"tipo": t, "resultado": {"titulo": "ok"}})
    assert cliente.post("/api/interno/analisis?tipo=semanal", headers={**gw, **CONTROL}).json()["resultado"]["titulo"] == "ok"


def test_ruta_ia_interna(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "q", lambda *a, **k: [{"proveedor": "vertex", "tipo": "chat", "resultado": "ok", "llamadas": 2}])
    r = cliente.get("/api/interno/ia", headers={**gw, **CONTROL})
    assert r.status_code == 200 and r.json()["vertex"]["max_hora"] >= 0 and r.json()["uso"][0]["llamadas"] == 2


def test_health_informa_vertex(cliente, monkeypatch):
    monkeypatch.setattr(rutas, "db_ok", lambda: True)
    assert cliente.get("/health").json()["vertex"] is False


def test_volcar_uso_conserva_si_falla(monkeypatch):
    ia._uso.clear()
    ia.registrar_uso("vertex", "chat", "ok", 10, 5)

    class PoolCaido:
        def connection(self, **k):
            raise RuntimeError("sin BD")
    monkeypatch.setattr(ia, "pool", PoolCaido())
    assert ia.volcar_uso_ia() == 0
    assert list(ia._uso.values()) == [[1, 10, 5]]
    ia._uso.clear()


def test_json_del_modelo_invalido_en_profundo(vertex, monkeypatch):
    monkeypatch.setattr(analisis, "_datos_semanal", lambda: {})
    monkeypatch.setattr(analisis, "evento", lambda *a, **k: None)
    monkeypatch.setattr(analisis, "ollama_disponible", lambda: False)
    monkeypatch.setattr(ia.httpx, "post", lambda *a, **k: gemini("esto no es json"))
    analisis._cache.clear()
    with pytest.raises(ia.SinIA):
        analisis.analisis_profundo("semanal")
