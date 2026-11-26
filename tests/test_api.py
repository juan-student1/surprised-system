"""Rutas clave de la API con la base de datos simulada.

Cubre: puerta única del gateway, límite por IP, modo mantenimiento, tokens de /api/control,
/api/bot, /api/llamada y /tareas/latido, reportes (normal y degradado) y privacidad de /api/llamadas.
"""
from datetime import datetime, timedelta, timezone

import pytest

from centinela import rutas, servicios


def _ficha(numero, **extra):
    return {"numero": numero, "pais": "Colombia", "score": 65, "nivel": "alto", "total_reportes": 3,
            "categoria_principal": "suplantacion", "resumen_ia": None, "conocido": True, "modo": "normal", **extra}


# ---------- Puerta única (M1 / C2) ----------

def test_sin_secreto_del_gateway_403(cliente):
    r = cliente.get("/api/stats")
    assert r.status_code == 403
    assert "gateway" in r.json()["error"]


def test_secreto_del_gateway_equivocado_403(cliente):
    assert cliente.get("/api/stats", headers={"x-centinela-gateway": "otro"}).status_code == 403


@pytest.mark.parametrize("ruta", ["/", "/ping"])
def test_rutas_libres_sin_gateway(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 200
    assert r.headers["X-Centinela-Nodo"] == "JE"


def test_health_sin_gateway(cliente, monkeypatch):
    monkeypatch.setattr(rutas, "db_ok", lambda: False)
    r = cliente.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["nodo"] == "JE" and body["db"] is False and body["ollama"] is False
    assert "pendientes" in body


def test_con_gateway_pasa(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "stats_completas", lambda: {"numeros": 1, "reportes": 2})
    r = cliente.get("/api/stats", headers=gw)
    assert r.status_code == 200 and r.json()["reportes"] == 2
    assert r.headers["X-Centinela-Nodo"] == "JE"


# ---------- IP del cliente (H1 / M1) ----------

def test_ip_del_cliente_solo_si_viene_del_gateway():
    from starlette.requests import Request
    from centinela.utilidades import ip_cliente

    def req(headers):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                        "client": ("10.0.0.1", 1234)})

    assert ip_cliente(req({"x-real-ip": "1.2.3.4", "x-centinela-gateway": "gw-prueba"})) == "1.2.3.4"
    # Sin el secreto, los encabezados de IP se ignoran: no se puede inventar otra identidad
    assert ip_cliente(req({"x-real-ip": "1.2.3.4", "x-forwarded-for": "5.6.7.8"})) == "10.0.0.1"


# ---------- Límite por IP en el nodo ----------

def test_limite_global_429(cliente, gw, app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "LIMITE_GLOBAL", 3)
    monkeypatch.setattr(rutas, "top_numeros", lambda limite=10: [])
    h = {**gw, "x-real-ip": "198.51.100.7"}
    codigos = [cliente.get("/api/top", headers=h).status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]
    # Otra IP no se ve afectada
    assert cliente.get("/api/top", headers={**gw, "x-real-ip": "198.51.100.8"}).status_code == 200


# ---------- /api/control y modo mantenimiento ----------

def test_control_sin_token_401(cliente):
    assert cliente.post("/api/control?accion=pausar").status_code == 401
    assert cliente.post("/api/control?accion=pausar", headers={"x-centinela-control": "malo"}).status_code == 401


def test_mantenimiento_devuelve_503_y_se_reactiva(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "evento", lambda *a, **k: None)
    tok = {"x-centinela-control": "control-prueba"}
    assert cliente.post("/api/control?accion=pausar", headers=tok).json()["pausado"] is True
    r = cliente.get("/api/stats", headers=gw)
    assert r.status_code == 503 and r.headers["X-Centinela-Nodo"] == "JE"
    assert cliente.post("/api/control?accion=reactivar", headers=tok).json()["pausado"] is False


# ---------- /tareas/latido (OIDC) ----------

def test_latido_sin_token_401(cliente):
    assert cliente.post("/tareas/latido").status_code == 401


def test_latido_token_que_no_es_jwt_401(cliente):
    assert cliente.post("/tareas/latido", headers={"authorization": "Bearer basura"}).status_code == 401


def test_latido_cuenta_equivocada_403(cliente, monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token",
                        lambda *a, **k: {"email": "otra@proyecto.iam.gserviceaccount.com", "email_verified": True})
    assert cliente.post("/tareas/latido", headers={"authorization": "Bearer a.b.c"}).status_code == 403


def test_latido_cuenta_correcta(cliente, monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token",
                        lambda *a, **k: {"email": "centinela-tareas@proyecto.iam.gserviceaccount.com", "email_verified": True})
    monkeypatch.setattr(rutas, "tareas_programadas", lambda: {"db": True, "sincronizados": 0, "ollama": False})
    r = cliente.post("/tareas/latido", headers={"authorization": "Bearer a.b.c"})
    assert r.status_code == 200 and r.json()["db"] is True


# ---------- /api/bot (solo n8n) ----------

def test_bot_sin_secreto_401(cliente, gw):
    assert cliente.post("/api/bot", json={"chat_id": 1, "texto": "/start"}, headers=gw).status_code == 401


def test_bot_con_secreto_responde_ayuda(cliente, gw):
    r = cliente.post("/api/bot", json={"chat_id": 1, "texto": "/start", "nombre": "Ana"},
                     headers={**gw, "x-centinela-bot": "bot-prueba"})
    assert r.status_code == 200 and "Hola Ana" in r.json()["respuesta"]


# ---------- Consultas y chat ----------

def test_consultar_numero_normaliza(cliente, gw, monkeypatch):
    vistos = []
    monkeypatch.setattr(rutas, "ficha", lambda n: vistos.append(n) or _ficha(n))
    r = cliente.get("/api/numero/300 123 4567", headers=gw)
    assert r.status_code == 200 and vistos == ["+573001234567"]


def test_consultar_numero_invalido_422(cliente, gw):
    assert cliente.get("/api/numero/12", headers=gw).status_code == 422


def test_chat_fuera_de_tema_sin_ia(cliente, gw):
    r = cliente.post("/api/chat", json={"mensaje": "cuanto es 2+2 en matematicas"}, headers=gw)
    assert r.json() == {"respuesta": rutas.FUERA_DE_TEMA, "fuente": "reglas", "nodo": "JE", "numeros": []}


def test_chat_solo_numero_responde_ficha(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "ficha", lambda n: _ficha(n))
    r = cliente.post("/api/chat", json={"mensaje": "3001234567"}, headers=gw).json()
    assert r["fuente"] == "reglas" and "riesgo alto" in r["respuesta"]


# ---------- Reportes ----------

def test_reporte_categoria_invalida_422(cliente, gw):
    r = cliente.post("/api/reportar", json={"numero": "3001234567", "categoria": "inventada"}, headers=gw)
    assert r.status_code == 422


def test_reporte_ignora_reportero_del_cliente(cliente, gw, monkeypatch):
    guardados = []
    monkeypatch.setattr(servicios, "guardar_reporte", lambda p: guardados.append(p) or 7)
    monkeypatch.setattr(servicios, "ficha", lambda n: _ficha(n))
    monkeypatch.setattr(servicios, "detectar_campana", lambda n: None)
    r = cliente.post("/api/reportar", json={"numero": "3001234567", "categoria": "estafa", "reportero_id": "falso"},
                     headers={**gw, "x-real-ip": "203.0.113.50"})
    assert r.status_code == 200 and r.json()["modo"] == "normal" and r.json()["id"] == 7
    from centinela.utilidades import hash_reportero
    assert guardados[0]["reportero"] == hash_reportero("203.0.113.50")
    assert guardados[0]["numero"] == "+573001234567"


def test_reporte_modo_degradado_sin_bd(cliente, gw):
    # Sin DATABASE_URL guardar falla → el reporte queda en la bandeja local (SQLite) para sincronizar luego
    from centinela.db import local
    with local() as c:
        antes = c.execute("select count(*) n from pendientes").fetchone()["n"]
    r = cliente.post("/api/reportar", json={"numero": "3001234567", "descripcion": "dicen ser del banco"},
                     headers={**gw, "x-real-ip": "203.0.113.60"})
    assert r.status_code == 200 and r.json()["modo"] == "degradado"
    with local() as c:
        assert c.execute("select count(*) n from pendientes").fetchone()["n"] == antes + 1


def test_reporte_limite_10_por_ip(cliente, gw, monkeypatch):
    monkeypatch.setattr(servicios, "guardar_reporte", lambda p: 1)
    monkeypatch.setattr(servicios, "ficha", lambda n: _ficha(n))
    monkeypatch.setattr(servicios, "detectar_campana", lambda n: None)
    h = {**gw, "x-real-ip": "203.0.113.70"}
    codigos = [cliente.post("/api/reportar", json={"numero": "3001234567"}, headers=h).status_code for _ in range(11)]
    assert codigos[:10] == [200] * 10 and codigos[10] == 429


# ---------- Llamadas reales (M2 / B3) ----------

def test_llamada_token_invalido_401(cliente, gw):
    assert cliente.post("/api/llamada", json={"numero": "3001234567"}, headers=gw).status_code == 401
    assert cliente.post("/api/llamada", json={"numero": "3001234567"},
                        headers={**gw, "x-centinela-token": "malo"}).status_code == 401


def test_llamada_con_token(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "ficha", lambda n: _ficha(n))
    monkeypatch.setattr(rutas, "q", lambda *a, **k: None)
    monkeypatch.setattr(rutas, "telegram_enviar", lambda *a, **k: None)
    r = cliente.post("/api/llamada", json={"numero": "3001234567"}, headers={**gw, "x-centinela-token": "llamadas-prueba"})
    assert r.status_code == 200 and r.json()["nivel"] == "alto"


def _filas_llamadas(*a, **k):
    return [{"id": 1, "numero": "+573001234567", "dispositivo": "Pixel de Juan", "score": 65, "nivel": "alto",
             "nodo": "JE", "creado": datetime.now(timezone.utc) - timedelta(seconds=5), "pais": "Colombia",
             "total_reportes": 3, "categoria_principal": "estafa", "resumen_ia": None}]


def test_llamadas_publico_enmascarado(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "q", _filas_llamadas)
    f = cliente.get("/api/llamadas", headers=gw).json()[0]
    assert f["numero"] == "+57 300 ••• 4567"
    assert "dispositivo" not in f


def test_llamadas_completo_con_token(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "q", _filas_llamadas)
    f = cliente.get("/api/llamadas", headers={**gw, "x-centinela-token": "llamadas-prueba"}).json()[0]
    assert f["numero"] == "+573001234567" and f["dispositivo"] == "Pixel de Juan"
