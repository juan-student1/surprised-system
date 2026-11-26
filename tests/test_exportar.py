"""Fase 4: exportación agregada y anonimizada a BigQuery (/tareas/exportar)."""
import json
from datetime import date

import pytest

from centinela import exportar, rutas


@pytest.mark.parametrize("numero, indicativo, tipo, ciudad", [
    ("+576015551234", "+57 601", "fijo", "Bogotá"),
    ("+576045551234", "+57 604", "fijo", "Medellín"),
    ("+573001234567", "+57 300", "celular", None),
    ("+18095550101", "+1 809", "internacional", None),
    ("+2250701234567", "+225", "internacional", None),
    ("85432", "corto", "corto", None),
])
def test_clasificar_numero(numero, indicativo, tipo, ciudad):
    c = exportar.clasificar_numero(numero)
    assert (c["indicativo"], c["tipo"], c["ciudad"]) == (indicativo, tipo, ciudad)


def test_top_numeros_salen_enmascarados(monkeypatch):
    monkeypatch.setattr(exportar, "q", lambda *a, **k: [{"fecha": date(2026, 11, 25), "numero": "+573001234567", "posicion": 1,
        "reportes_dia": 4, "score_actual": 83, "nivel_actual": "alto", "categoria": "suplantacion"}])
    f = exportar.filas_top_numeros()[0]
    assert f["numero_enmascarado"] == "+57 300 ••• 4567"
    assert "3001234567" not in json.dumps(f, default=str, ensure_ascii=False)


def test_riesgo_por_prefijo_agrega_sin_numeros(monkeypatch):
    monkeypatch.setattr(exportar, "q", lambda *a, **k: [
        {"fecha": date(2026, 11, 25), "numero": "+573001111111", "reportes": 3, "score": 80, "nivel": "alto"},
        {"fecha": date(2026, 11, 25), "numero": "+573002222222", "reportes": 1, "score": 40, "nivel": "medio"},
        {"fecha": date(2026, 11, 25), "numero": "+18095550101", "reportes": 1, "score": 55, "nivel": "medio"}])
    filas = {f["indicativo"]: f for f in exportar.filas_riesgo_por_prefijo()}
    assert filas["+57 300"]["reportes"] == 4 and filas["+57 300"]["numeros"] == 2
    assert filas["+57 300"]["score_promedio"] == 60.0 and filas["+57 300"]["numeros_alto_riesgo"] == 1
    assert filas["+1 809"]["prefijo_wangiri"] is True
    assert "3001111111" not in json.dumps(list(filas.values()), default=str)


def test_costo_ia_estimado(monkeypatch):
    monkeypatch.setattr(exportar, "VERTEX_PRECIO_ENTRADA_M", 0.5)
    monkeypatch.setattr(exportar, "VERTEX_PRECIO_SALIDA_M", 3.0)
    monkeypatch.setattr(exportar, "q", lambda *a, **k: [
        {"fecha": date(2026, 11, 25), "nodo": "JE", "proveedor": "vertex", "tipo": "chat", "resultado": "ok", "llamadas": 2, "tokens_entrada": 1_000_000, "tokens_salida": 100_000},
        {"fecha": date(2026, 11, 25), "nodo": "JE", "proveedor": "ollama", "tipo": "chat", "resultado": "ok", "llamadas": 5, "tokens_entrada": 0, "tokens_salida": 0}])
    filas = {f["proveedor"]: f for f in exportar.filas_uso_ia()}
    assert filas["vertex"]["costo_estimado_usd"] == pytest.approx(0.8)
    assert filas["ollama"]["costo_estimado_usd"] == 0.0


def test_costo_ia_sin_precio_es_nulo(monkeypatch):
    monkeypatch.setattr(exportar, "VERTEX_PRECIO_ENTRADA_M", 0.0)
    monkeypatch.setattr(exportar, "VERTEX_PRECIO_SALIDA_M", 0.0)
    monkeypatch.setattr(exportar, "q", lambda *a, **k: [{"fecha": date(2026, 11, 25), "nodo": "JE", "proveedor": "vertex",
        "tipo": "chat", "resultado": "ok", "llamadas": 1, "tokens_entrada": 10, "tokens_salida": 5}])
    assert exportar.filas_uso_ia()[0]["costo_estimado_usd"] is None


def test_esquemas_coinciden_con_generadores():
    assert set(exportar.TABLAS) == set(exportar.GENERADORES) == set(exportar.DESCRIPCIONES)
    for t in exportar.TABLAS:
        assert exportar.TABLAS[t][0] == ("fecha", "DATE")      # todas particionadas por fecha


def test_multipart_load_job(monkeypatch):
    monkeypatch.setattr(exportar, "BQ_PROYECTO", "p")
    cuerpo, tipo = exportar.cuerpo_multipart("canales", exportar.ndjson([{"fecha": date(2026, 11, 25), "canal": "web", "reportes": 2}]))
    frontera = tipo.split("boundary=")[1]
    partes = cuerpo.decode().split("--" + frontera)
    config = json.loads(partes[1].split("\r\n\r\n", 1)[1])
    load = config["configuration"]["load"]
    assert load["writeDisposition"] == "WRITE_TRUNCATE" and load["sourceFormat"] == "NEWLINE_DELIMITED_JSON"
    assert load["timePartitioning"] == {"type": "DAY", "field": "fecha"}
    assert load["destinationTable"] == {"projectId": "p", "datasetId": "centinela_analitica", "tableId": "canales"}
    assert '"fecha": "2026-11-25"' in partes[2]


class R:
    def __init__(self, data=None, status=200):
        self._d, self.status_code = data or {}, status
    def json(self):
        return self._d
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_exportar_completo_simulado(monkeypatch):
    monkeypatch.setattr(exportar, "BQ_PROYECTO", "p")
    monkeypatch.setattr("centinela.gcp.token", lambda: "tok")
    for t in exportar.GENERADORES:
        monkeypatch.setitem(exportar.GENERADORES, t, lambda: [{"fecha": date(2026, 11, 25)}])
    monkeypatch.setitem(exportar.GENERADORES, "uso_ia", lambda: [])                    # tabla vacía: solo se crea
    def sin_fuente():
        raise RuntimeError("relation does not exist")
    monkeypatch.setitem(exportar.GENERADORES, "seguridad", sin_fuente)                 # migración no aplicada
    posts, gets = [], []
    def post(url, **k):
        posts.append(url)
        return R({"jobReference": {"jobId": "j-" + str(len(posts))}}) if "upload" in url else R(status=409)
    monkeypatch.setattr(exportar.httpx, "post", post)
    monkeypatch.setattr(exportar.httpx, "get", lambda url, **k: gets.append(url) or R({"status": {"state": "DONE"}}))
    res = exportar.exportar()
    assert res["tablas"]["canales"]["estado"] == "ok"
    assert res["tablas"]["uso_ia"]["estado"] == "vacia"
    assert res["tablas"]["seguridad"]["estado"] == "sin_fuente"
    assert res["ok"] is False                                   # una tabla sin fuente → Scheduler reintenta
    assert sum("upload" in u for u in posts) == 6 and all("location=us-east1" in g for g in gets)


def test_exportar_error_de_bigquery(monkeypatch):
    monkeypatch.setattr(exportar, "BQ_PROYECTO", "p")
    monkeypatch.setattr("centinela.gcp.token", lambda: "tok")
    for t in exportar.GENERADORES:
        monkeypatch.setitem(exportar.GENERADORES, t, lambda: [{"fecha": date(2026, 11, 25)}])
    monkeypatch.setattr(exportar.httpx, "post", lambda url, **k: R({"jobReference": {"jobId": "j"}}) if "upload" in url else R(status=409))
    monkeypatch.setattr(exportar.httpx, "get", lambda url, **k: R({"status": {"state": "DONE", "errorResult": {"message": "x"}}}))
    res = exportar.exportar()
    assert res["ok"] is False and all(v["estado"] == "error" for v in res["tablas"].values())


# ---------- ruta /tareas/exportar ----------

def test_exportar_apagado_sin_bq(cliente):
    assert cliente.post("/tareas/exportar").status_code == 404     # sin BQ_PROYECTO (así corre JP)


def test_exportar_exige_oidc(cliente, monkeypatch):
    monkeypatch.setattr(rutas, "BQ_PROYECTO", "p")
    assert cliente.post("/tareas/exportar").status_code == 401
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {"email": "intruso@x.iam.gserviceaccount.com", "email_verified": True})
    assert cliente.post("/tareas/exportar", headers={"authorization": "Bearer a.b.c"}).status_code == 403


def test_exportar_ok_y_fallo(cliente, monkeypatch):
    monkeypatch.setattr(rutas, "BQ_PROYECTO", "p")
    monkeypatch.setattr(rutas, "evento", lambda *a, **k: None)
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {"email": "centinela-tareas@proyecto.iam.gserviceaccount.com", "email_verified": True})
    h = {"authorization": "Bearer a.b.c"}
    monkeypatch.setattr(rutas, "exportar_bq", lambda: {"ok": True, "dataset": "d", "tablas": {"canales": {"filas": 2, "estado": "ok"}}})
    r = cliente.post("/tareas/exportar", headers=h)                 # sin secreto del gateway: /tareas/* usa OIDC
    assert r.status_code == 200 and r.json()["tablas"]["canales"]["filas"] == 2
    monkeypatch.setattr(rutas, "exportar_bq", lambda: {"ok": False, "dataset": "d", "tablas": {"canales": {"filas": 2, "estado": "error"}}})
    assert cliente.post("/tareas/exportar", headers=h).status_code == 500


def test_tareas_funciona_en_mantenimiento(cliente, monkeypatch):
    from centinela.config import MANTENIMIENTO
    MANTENIMIENTO["on"] = True
    assert cliente.post("/tareas/exportar").status_code == 404      # llega a la ruta (no 503)
