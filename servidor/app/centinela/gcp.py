"""CENTINELA · credenciales de Google Cloud del propio nodo (sin llaves JSON).

En Cloud Run, google.auth.default() entrega tokens temporales de la cuenta de servicio
centinela-run. Lo usan Vertex AI (ia.py) y BigQuery (exportar.py).
"""
import threading

_lock = threading.Lock()
_cred = {"c": None}


def token() -> str:
    import google.auth
    from google.auth.transport.requests import Request
    with _lock:
        if _cred["c"] is None:
            _cred["c"], _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _cred["c"].valid:
            _cred["c"].refresh(Request())
        return _cred["c"].token
