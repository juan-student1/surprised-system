"""Fase 2: formulario de leads (JM), métricas de seguridad (JP) y rutas internas del panel."""
from centinela import rutas, servicios

LEAD = {"nombre": "Ana Pérez", "empresa": "Cooperativa Ejemplo", "correo": "Ana@Ejemplo.co", "telefono": "3001234567",
        "segmento": "cooperativa", "plan": "empresa", "mensaje": "Queremos\nuna demo", "acepta_datos": True}
CONTROL = {"x-centinela-control": "control-prueba"}


def _ip(gw, ip):
    return {**gw, "x-real-ip": ip}


# ---------- /api/leads ----------

def test_lead_se_guarda_limpio(cliente, gw, monkeypatch):
    guardados = []
    monkeypatch.setattr(rutas, "q", lambda sql, params=(), **k: guardados.append(params) or {"id": 5})
    avisos = []
    monkeypatch.setattr(rutas, "telegram_enviar", lambda t, *a: avisos.append(t))
    r = cliente.post("/api/leads", json=LEAD, headers=_ip(gw, "203.0.113.10"))
    assert r.status_code == 200 and r.json() == {"ok": True, "id": 5}
    p = guardados[0]
    assert p[2] == "ana@ejemplo.co"             # correo en minúscula
    assert p[6] == "Queremos una demo"          # sin saltos de línea
    assert p[7] != "203.0.113.10"               # nunca la IP en claro
    # El aviso de Telegram no lleva datos personales
    assert "ana@ejemplo.co" not in avisos[0] and "3001234567" not in avisos[0]


def test_lead_sin_autorizacion_422(cliente, gw):
    r = cliente.post("/api/leads", json={**LEAD, "acepta_datos": False}, headers=_ip(gw, "203.0.113.11"))
    assert r.status_code == 422


def test_lead_correo_invalido_422(cliente, gw):
    r = cliente.post("/api/leads", json={**LEAD, "correo": "no-es-correo"}, headers=_ip(gw, "203.0.113.12"))
    assert r.status_code == 422


def test_lead_segmento_invalido_422(cliente, gw):
    r = cliente.post("/api/leads", json={**LEAD, "segmento": "hackers"}, headers=_ip(gw, "203.0.113.13"))
    assert r.status_code == 422


def test_lead_trampa_para_bots_no_guarda(cliente, gw, monkeypatch):
    def no_debe_llamarse(*a, **k):
        raise AssertionError("un bot no debe llegar a la BD")
    monkeypatch.setattr(rutas, "q", no_debe_llamarse)
    r = cliente.post("/api/leads", json={**LEAD, "sitio_web": "http://spam"}, headers=_ip(gw, "203.0.113.14"))
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_lead_limite_3_por_hora(cliente, gw):
    h = _ip(gw, "203.0.113.15")
    codigos = [cliente.post("/api/leads", json={**LEAD, "sitio_web": "x"}, headers=h).status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]


def test_lead_bd_caida_503(cliente, gw, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin BD")
    monkeypatch.setattr(rutas, "q", falla)
    assert cliente.post("/api/leads", json=LEAD, headers=_ip(gw, "203.0.113.16")).status_code == 503


# ---------- rutas internas del panel ----------

def test_interno_sin_token_401(cliente, gw):
    assert cliente.get("/api/interno/leads", headers=gw).status_code == 401
    assert cliente.get("/api/interno/seguridad", headers={**gw, "x-centinela-control": "malo"}).status_code == 401


def test_interno_sin_gateway_403(cliente):
    # Aunque traiga el token, sin el secreto del gateway no entra (puerta única)
    assert cliente.get("/api/interno/leads", headers=CONTROL).status_code == 403


def test_interno_leads_con_token(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "q", lambda *a, **k: [{"id": 1, "nombre": "Ana"}])
    r = cliente.get("/api/interno/leads", headers={**gw, **CONTROL})
    assert r.status_code == 200 and r.json()[0]["nombre"] == "Ana"


def test_interno_seguridad_con_token(cliente, gw, monkeypatch):
    monkeypatch.setattr(rutas, "q", lambda *a, **k: [])
    r = cliente.get("/api/interno/seguridad?horas=9999", headers={**gw, **CONTROL})
    assert r.status_code == 200 and r.json()["horas"] == 168


# ---------- contador de bloqueos ----------

def test_grupo_ruta():
    assert servicios.grupo_ruta("/api/numero/3001234567") == "/api/numero"
    assert servicios.grupo_ruta("/api/../../etc/passwd") == "/api/otra"
    assert servicios.grupo_ruta("/tareas/latido") == "/tareas"
    assert servicios.grupo_ruta("/wp-login.php") == "otra"


def test_middleware_cuenta_401_403_429(cliente, gw):
    servicios._bloqueos.clear()
    cliente.get("/api/stats")                                     # 403: sin gateway
    cliente.post("/api/control")                                  # 401: sin token
    cliente.get("/api/numero/12", headers=gw)                     # 422: no cuenta
    conteo = {(c, r): n for (_, c, r), n in servicios._bloqueos.items()}
    assert conteo == {(403, "/api/stats"): 1, (401, "/api/control"): 1}
    servicios._bloqueos.clear()


def test_volcar_seguridad_conserva_si_falla_la_bd(monkeypatch):
    servicios._bloqueos.clear()
    servicios.contar_bloqueo(429, "/api/chat")

    class PoolCaido:
        def connection(self, **k):
            raise RuntimeError("sin BD")
    monkeypatch.setattr(servicios, "pool", PoolCaido())
    assert servicios.volcar_seguridad() == 0
    assert sum(servicios._bloqueos.values()) == 1                 # nada se pierde
    servicios._bloqueos.clear()
