"""Panel /admin del nodo: PBKDF2, TOTP (RFC 6238) y sesión firmada."""
import hashlib
import time

from centinela import auth


def _hash(clave: str, salt: bytes = b"\x01" * 16) -> str:
    return "pbkdf2$" + salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", clave.encode(), salt, 200_000).hex()


def test_clave_ok():
    guardado = _hash("correcta")
    assert auth.clave_ok("correcta", guardado)
    assert not auth.clave_ok("incorrecta", guardado)
    assert not auth.clave_ok("correcta", "basura")


def test_totp_vector_rfc6238(monkeypatch):
    # RFC 6238, apéndice B: secreto ASCII "12345678901234567890", T=59 s → 94287082 (6 dígitos: 287082)
    secreto = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # gitleaks:allow (vector público del RFC, no es un secreto)
    monkeypatch.setattr(auth.time, "time", lambda: 59)
    assert auth.totp_ok(secreto, "287082")
    assert auth.totp_ok(secreto, "287 082")       # tolera espacios
    assert not auth.totp_ok(secreto, "000000")


def test_totp_sin_secreto_no_bloquea():
    assert auth.totp_ok("", "")


def test_sesion_firmada_valida_y_alterada():
    cookie = auth.firmar_sesion("admin")
    assert auth.sesion_valida(cookie)
    cuerpo, firma = cookie.rsplit(".", 1)
    assert not auth.sesion_valida(cuerpo + "." + ("0" * len(firma)))
    assert not auth.sesion_valida(None)
    assert not auth.sesion_valida("sin-punto")


def test_sesion_expira(monkeypatch):
    cookie = auth.firmar_sesion("admin")
    ahora = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: ahora + auth.SESION_MIN * 60 + 1)
    assert not auth.sesion_valida(cookie)


def test_bloqueo_tras_5_fallos(monkeypatch):
    monkeypatch.setattr(auth, "_login_fallos", auth.defaultdict(list))
    ip = "203.0.113.9"
    for _ in range(auth.INTENTOS_MAX):
        assert not auth.login_bloqueado(ip)
        auth._login_fallos[ip].append(time.time())
    assert auth.login_bloqueado(ip)


def test_panel_del_nodo_apagado_por_defecto(cliente, gw):
    # El panel vive en el gateway; en el nodo /admin responde 404 salvo ADMIN_EN_NODO=1
    assert cliente.get("/admin", headers=gw).status_code == 404
    assert cliente.get("/admin/login", headers=gw).status_code == 404
