"""CENTINELA · capa de IA híbrida.

1º Ollama en el Lenovo (local, gratis, privado). 2º Vertex AI Gemini (nube) SOLO si Ollama no responde,
con tope de llamadas por hora y por día, caché de respuestas y timeout. 3º Si no hay ninguna: reglas.
Nunca hay bucles automáticos hacia Gemini: cada llamada nace de una acción de una persona
(un chat, un reporte con descripción o un botón de "análisis profundo" en el panel).
Ver docs/16_VERTEX_AI.md.
"""
import hashlib, json, os, threading, time
from collections import defaultdict, deque
from datetime import datetime, timezone

import httpx

from .config import (OLLAMA_URL, OLLAMA_MODEL, OLLAMA_PROXY, CATEGORIAS, NODO, VERTEX_PROYECTO, VERTEX_REGION,
                     VERTEX_MODELO, VERTEX_MAX_HORA, VERTEX_MAX_DIA, VERTEX_MAX_PROFUNDO_DIA, VERTEX_TIMEOUT,
                     VERTEX_CACHE_SEG, log)
from .db import pool, recalcular


class SinIA(Exception):
    """Ninguna IA disponible (Ollama caído y Vertex apagado o sin cupo)."""


# ---------------- Ollama (local) ----------------
_ollama_estado = {"ok": False, "t": 0.0}

def ollama_disponible(forzar=False) -> bool:
    if not forzar and time.time() - _ollama_estado["t"] < 60:
        return _ollama_estado["ok"]
    try: ok = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3 if OLLAMA_PROXY else 2, proxy=OLLAMA_PROXY).status_code == 200
    except Exception: ok = False
    _ollama_estado.update(ok=ok, t=time.time())
    return ok

def ollama_chat(system: str, usuario: str, json_mode=False, timeout=90, temperatura=0.2, num_predict=220) -> str:
    opciones = {"temperature": temperatura, "num_predict": num_predict, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "1024"))}
    cuerpo = {"model": OLLAMA_MODEL, "stream": False, "options": opciones, "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "10m"), "messages": [{"role": "system", "content": system}, {"role": "user", "content": usuario}]}
    if json_mode: cuerpo["format"] = "json"
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=cuerpo, timeout=timeout, proxy=OLLAMA_PROXY)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ---------------- Vertex AI Gemini (nube, respaldo) ----------------
VERTEX_ACTIVO = bool(VERTEX_PROYECTO and VERTEX_MODELO)
_lock = threading.Lock()
_llamadas: deque = deque()            # instantes de cada llamada real a Gemini (últimas 24 h)
_profundas: deque = deque()           # instantes de los análisis profundos (últimas 24 h)
_cache: dict[str, tuple[float, str]] = {}
_CACHE_MAX = 300
_cred = {"c": None}

def _url_vertex() -> str:
    host = "aiplatform.googleapis.com" if VERTEX_REGION == "global" else f"{VERTEX_REGION}-aiplatform.googleapis.com"
    return (f"https://{host}/v1/projects/{VERTEX_PROYECTO}/locations/{VERTEX_REGION}"
            f"/publishers/google/models/{VERTEX_MODELO}:generateContent")

def _token() -> str:
    """Token de la cuenta de servicio del nodo (en Cloud Run: centinela-run, sin llaves JSON)."""
    import google.auth
    from google.auth.transport.requests import Request
    with _lock:
        if _cred["c"] is None:
            _cred["c"], _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _cred["c"].valid:
            _cred["c"].refresh(Request())
        return _cred["c"].token

def _podar(cola: deque, ahora: float):
    while cola and ahora - cola[0] > 86400: cola.popleft()

def vertex_cupo(profundo=False) -> dict:
    """Cuántas llamadas a Gemini quedan (los topes protegen la factura)."""
    ahora = time.time()
    with _lock:
        _podar(_llamadas, ahora); _podar(_profundas, ahora)
        hora = sum(1 for t in _llamadas if ahora - t < 3600)
        return {"activo": VERTEX_ACTIVO, "modelo": VERTEX_MODELO, "region": VERTEX_REGION,
                "hora": hora, "max_hora": VERTEX_MAX_HORA, "dia": len(_llamadas), "max_dia": VERTEX_MAX_DIA,
                "profundo_dia": len(_profundas), "max_profundo_dia": VERTEX_MAX_PROFUNDO_DIA}

def vertex_puede(profundo=False) -> bool:
    c = vertex_cupo()
    if not c["activo"] or c["hora"] >= c["max_hora"] or c["dia"] >= c["max_dia"]: return False
    return not profundo or c["profundo_dia"] < c["max_profundo_dia"]

def _clave_cache(*partes) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in partes).encode()).hexdigest()

def vertex_chat(system: str, usuario: str, json_mode=False, temperatura=0.2, max_tokens=1024, timeout=None,
                tipo="chat", profundo=False) -> str:
    """Una llamada a Gemini con caché, topes y timeout. Lanza SinIA si no hay cupo."""
    clave = _clave_cache(VERTEX_MODELO, system, usuario, json_mode, temperatura)
    ahora = time.time()
    with _lock:
        hit = _cache.get(clave)
    if hit and ahora - hit[0] < VERTEX_CACHE_SEG:
        registrar_uso("vertex", tipo, "cache")
        return hit[1]
    if not vertex_puede(profundo):
        registrar_uso("vertex", tipo, "sin_cupo" if VERTEX_ACTIVO else "apagado")
        raise SinIA("Vertex sin cupo o apagado")
    with _lock:
        _llamadas.append(ahora)
        if profundo: _profundas.append(ahora)
    cuerpo = {"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": usuario}]}],
              "generationConfig": {"temperature": temperatura, "maxOutputTokens": max_tokens,
                                   **({"responseMimeType": "application/json"} if json_mode else {})}}
    try:
        r = httpx.post(_url_vertex(), json=cuerpo, timeout=timeout or VERTEX_TIMEOUT,
                       headers={"Authorization": f"Bearer {_token()}"})
        r.raise_for_status()
        data = r.json()
        partes = data["candidates"][0]["content"]["parts"]
        txt = "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
        if not txt: raise ValueError("respuesta vacía")
        uso = data.get("usageMetadata", {})
        registrar_uso("vertex", tipo, "ok", uso.get("promptTokenCount", 0), uso.get("candidatesTokenCount", 0) + uso.get("thoughtsTokenCount", 0))
    except Exception as e:
        registrar_uso("vertex", tipo, "error")
        log.warning("Vertex falló (%s): %s", tipo, str(e)[:200])
        raise SinIA(str(e)[:200]) from e
    with _lock:
        if len(_cache) >= _CACHE_MAX: _cache.pop(next(iter(_cache)))
        _cache[clave] = (ahora, txt)
    return txt


# ---------------- Híbrido ----------------
def ia_disponible() -> bool:
    return ollama_disponible() or vertex_puede()

def ia_generar(system: str, usuario: str, tipo="chat", json_mode=False, temperatura=0.2, num_predict=220,
               timeout=90) -> tuple[str, str]:
    """Ollama primero; si no responde, Gemini (con cupo). Devuelve (texto, fuente)."""
    if ollama_disponible():
        try:
            txt = ollama_chat(system, usuario, json_mode=json_mode, timeout=timeout, temperatura=temperatura, num_predict=num_predict)
            registrar_uso("ollama", tipo, "ok")
            return txt, "ollama"
        except Exception as e:
            registrar_uso("ollama", tipo, "error")
            _ollama_estado.update(ok=False, t=time.time())   # no volver a esperarlo en el próximo minuto
            log.warning("Ollama falló (%s), paso a Vertex: %s", tipo, e)
    txt = vertex_chat(system, usuario, json_mode=json_mode, temperatura=temperatura, max_tokens=max(num_predict * 4, 512), tipo=tipo)
    return txt, "vertex"


# ---------------- Uso de IA (para el panel y la analítica) ----------------
# Se agrega en memoria por (hora, proveedor, tipo, resultado) y se vuelca a ia_uso_hora en cada latido.
_uso: dict[tuple, list] = defaultdict(lambda: [0, 0, 0])   # llamadas, tokens_entrada, tokens_salida

def registrar_uso(proveedor: str, tipo: str, resultado: str, tok_in: int = 0, tok_out: int = 0):
    hora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
    with _lock:
        v = _uso[(hora, proveedor, tipo, resultado)]
        v[0] += 1; v[1] += int(tok_in or 0); v[2] += int(tok_out or 0)

def volcar_uso_ia() -> int:
    with _lock:
        if not _uso: return 0
        lote = {k: list(v) for k, v in _uso.items()}; _uso.clear()
    try:
        with pool.connection(timeout=4) as conn:
            for (hora, prov, tipo, res), (n, ti, to) in lote.items():
                conn.execute("""insert into ia_uso_hora (hora, nodo, proveedor, tipo, resultado, llamadas, tokens_entrada, tokens_salida)
                                values (%s,%s,%s,%s,%s,%s,%s,%s)
                                on conflict (hora, nodo, proveedor, tipo, resultado) do update set
                                  llamadas = ia_uso_hora.llamadas + excluded.llamadas,
                                  tokens_entrada = ia_uso_hora.tokens_entrada + excluded.tokens_entrada,
                                  tokens_salida = ia_uso_hora.tokens_salida + excluded.tokens_salida""",
                             (hora, NODO, prov, tipo, res, n, ti, to))
        return len(lote)
    except Exception as e:
        with _lock:
            for k, (n, ti, to) in lote.items():
                v = _uso[k]; v[0] += n; v[1] += ti; v[2] += to
        log.warning("No se pudo guardar el uso de IA: %s", e); return 0


# ---------------- Clasificación de reportes ----------------
def clasificar_con_ia(reporte_id: int, numero: str, descripcion: str):
    if not descripcion or not ia_disponible(): return
    try:
        system = ("Eres un analista antifraude telefónico en Colombia. Clasifica el reporte en UNA categoría:\n"
                  "- suplantacion: dicen ser de un banco, entidad, empresa o autoridad para pedir claves, códigos o datos\n"
                  "- estafa: premios falsos, inversiones, falsos familiares en apuros, ventas engañosas para robar dinero\n"
                  "- extorsion: amenazas, intimidación, exigen dinero bajo presión\n"
                  "- cobranza: cobran deudas o cuotas\n"
                  "- telemarketing: ofrecen productos, planes, créditos o servicios\n"
                  "- encuesta: encuestas o estudios de opinión\n"
                  "- wangiri: timbran una vez desde el extranjero para que devuelvas la llamada\n"
                  "- otro: nada de lo anterior\n"
                  'Responde SOLO JSON: {"categoria": "...", "resumen": "frase corta en español, sin punto final"}')
        txt, _ = ia_generar(system, f"Número: {numero}\nReporte: {descripcion}", tipo="clasificar", json_mode=True,
                            temperatura=0, num_predict=140, timeout=45)
        res = json.loads(txt)
        cat = str(res.get("categoria", "otro")).lower().strip()
        cat = cat if cat in CATEGORIAS else "otro"
        with pool.connection(timeout=4) as conn:
            conn.execute("update reportes set categoria=%s, clasificado_por='ia' where id=%s and categoria is null", (cat, reporte_id))
            conn.execute("update numeros set resumen_ia=%s where numero=%s", (str(res.get("resumen", ""))[:280], numero))
            recalcular(conn, numero)
    except SinIA: pass
    except Exception as e: log.warning("Clasificación IA falló: %s", e)
