"""
CENTINELA · API del nodo (punto de entrada)
-------------------------------------------
Corre igual en JE (principal) y JP (respaldo). Ambos comparten Supabase.
Si Supabase no responde, entra en MODO DEGRADADO (SQLite local + sincronización).

Arquitectura limpia (paquete `centinela/`):
  config.py    → constantes y entorno
  utilidades.py→ dominio puro (normalizar, score, formato…)
  db.py        → acceso a datos (Supabase + SQLite)
  ia.py        → Ollama local
  servicios.py → reportes, campañas, Telegram, tareas de fondo, rate limiting
  auth.py      → panel /admin autenticado (PBKDF2 + HMAC + TOTP)
  rutas.py     → contrato HTTP (FastAPI)

Este archivo solo compone la app FastAPI, el middleware y el lifespan.
Mantiene `app` expuesto para uvicorn (`uvicorn main:app`) sin que JE/JP cambien nada.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from centinela.config import VERSION, CORS_ORIGINS, LIMITE_GLOBAL, NODO, MANTENIMIENTO, EN_CLOUD_RUN
from centinela.db import pool, local, evento
from centinela.servicios import latido, sincronizador, vigilar_ia, latir_una_vez, _exceso
from centinela.utilidades import ip_cliente, viene_del_gateway
from centinela import rutas


@asynccontextmanager
async def lifespan(app: FastAPI):
    if pool:
        pool.open(wait=False)
    local().close()
    await __import__("asyncio").to_thread(evento, "arranque", f"Nodo {NODO} ({os.getenv('NODO_ROL', 'principal')}) v{VERSION} iniciado")
    import asyncio
    if EN_CLOUD_RUN:
        # Cloud Run: sin bucles (la CPU se congela entre peticiones). Un latido al arrancar
        # y el resto lo dispara Cloud Scheduler cada minuto en /tareas/latido.
        tareas = [asyncio.create_task(asyncio.to_thread(latir_una_vez))]
    else:
        tareas = [
            asyncio.create_task(latido()),
            asyncio.create_task(sincronizador()),
            asyncio.create_task(vigilar_ia()),
        ]
    yield
    for t in tareas:
        t.cancel()
    await asyncio.to_thread(evento, "apagado", f"Nodo {NODO} detenido")
    if pool:
        pool.close()


app = FastAPI(title="Centinela API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Centinela-Nodo"],
)


@app.middleware("http")
async def guardia(request: Request, call_next):
    # Modo mantenimiento: el panel puede "detener" este nodo para demostrar el failover.
    # Devuelve 503 en todo (menos /api/control, para poder reactivarlo) -> el gateway salta al otro nodo.
    if MANTENIMIENTO["on"] and request.url.path not in ("/api/control", "/tareas/latido"):
        r = Response('{"error":"Nodo en mantenimiento","nodo":"' + NODO + '"}', status_code=503, media_type="application/json")
        r.headers["X-Centinela-Nodo"] = NODO
        return r
    # Puerta única: con GATEWAY_SECRET, lo que no venga del Worker se rechaza (la URL de Cloud Run y la del
    # Funnel son públicas). Excepciones: salud (la usa el gateway), latido (token OIDC) y control (token propio).
    if not viene_del_gateway(request) and request.url.path not in ("/health", "/ping", "/", "/tareas/latido", "/api/control"):
        return Response('{"error":"Acceso solo por el gateway"}', status_code=403, media_type="application/json")
    # Escudo por IP en el propio nodo: si el gateway cae o atacan por el Funnel directo,
    # ninguna IP puede inundar la API. /health, /ping y / quedan libres (los usa el clúster).
    if request.url.path not in ("/health", "/ping", "/", "/tareas/latido"):
        if _exceso("global", ip_cliente(request), LIMITE_GLOBAL, 60):
            r = Response('{"error":"Demasiadas peticiones"}', status_code=429, media_type="application/json")
            r.headers["Retry-After"] = "60"
            r.headers["X-Centinela-Nodo"] = NODO
            return r
    resp = await call_next(request)
    resp.headers["X-Centinela-Nodo"] = NODO
    return resp


rutas.registrar(app)

__all__ = ["app"]
