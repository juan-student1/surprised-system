"""Configuración común de los tests de la API.

La API lee su configuración del entorno AL IMPORTARSE, así que las variables se ponen aquí,
antes de importar nada de `servidor/app`. No hay base de datos real: DATABASE_URL queda vacío
(pool = None) y cada test simula lo que necesita con monkeypatch.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "servidor" / "app"))

_TMP = tempfile.mkdtemp(prefix="centinela-tests-")
os.environ.update({
    "DATABASE_URL": "",
    "LOCAL_DB": os.path.join(_TMP, "local.db"),
    "NODO_NOMBRE": "JE",
    "NODO_ROL": "principal",
    "SAL_HASH": "sal-de-prueba",
    # Valores de prueba (no son secretos reales)
    "GATEWAY_SECRET": "gw-prueba",
    "BOT_SECRET": "bot-prueba",
    "LLAMADAS_TOKEN": "llamadas-prueba",
    "CONTROL_TOKEN": "control-prueba",
    "TAREAS_SA": "centinela-tareas@proyecto.iam.gserviceaccount.com",
    "OLLAMA_URL": "http://127.0.0.1:9",   # puerto cerrado: nunca hay IA real en los tests
    "TELEGRAM_TOKEN": "",
})
os.environ.pop("K_SERVICE", None)
os.environ.pop("ADMIN_EN_NODO", None)

GW = {"x-centinela-gateway": "gw-prueba"}


@pytest.fixture
def app_mod():
    import main
    return main


@pytest.fixture
def cliente(app_mod, monkeypatch):
    """Cliente HTTP SIN lifespan (no arranca bucles de fondo ni toca la BD)."""
    from fastapi.testclient import TestClient
    from centinela import ia, rutas, servicios
    from centinela.config import MANTENIMIENTO

    # Sin IA en los tests (respuesta inmediata por reglas); Vertex está apagado (sin VERTEX_PROYECTO)
    monkeypatch.setattr(rutas, "ollama_disponible", lambda *a, **k: False)
    monkeypatch.setattr(rutas, "ia_disponible", lambda *a, **k: False)
    monkeypatch.setattr(servicios, "ollama_disponible", lambda *a, **k: False)
    monkeypatch.setattr(ia, "ollama_disponible", lambda *a, **k: False)
    # Límites de peticiones limpios en cada test
    servicios._baldes.clear()
    MANTENIMIENTO["on"] = False
    yield TestClient(app_mod.app)
    MANTENIMIENTO["on"] = False
    servicios._baldes.clear()


@pytest.fixture
def gw():
    return dict(GW)
