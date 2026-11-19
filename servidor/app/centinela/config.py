"""CENTINELA · configuración central del nodo.

Todo lo que antes estaba suelto en main.py vive aquí: variables de entorno,
constantes del dominio (categorías, países, prefijos wangiri) y utilidades
básicas. Ningún otro módulo importa de main.py; todos importan de aquí.
"""

import logging
import os
from datetime import datetime, timezone

VERSION = "1.5.0"
# v1.5.0 = puede correr en Cloud Run (tareas por Cloud Scheduler + IA por proxy de Tailscale) con Cloud SQL.
# v1.4.0 = misma API que antes, solo reorganizada en capas (config/utils/db/ia/servicios/auth/rutas).
NODO = os.getenv("NODO_NOMBRE", "JE")
ROL = os.getenv("NODO_ROL", "principal")
DATABASE_URL = os.getenv("DATABASE_URL", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://centinela-ia:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
LOCAL_DB = os.getenv(
    "LOCAL_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "local.db"),
)
SAL = os.getenv("SAL_HASH", "centinela")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_API = os.getenv("TELEGRAM_API", "https://api.telegram.org")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # a quién avisar de llamadas reales
LLAMADAS_TOKEN = os.getenv("LLAMADAS_TOKEN", "")  # clave que usa el celular para avisar
CONTROL_TOKEN = os.getenv("CONTROL_TOKEN", "")
# Bloque 2 de la auditoría (vacíos = comportamiento anterior, para desplegar sin cortes):
GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "")  # solo si llega este secreto se cree la IP que reenvía el gateway
BOT_SECRET = os.getenv("BOT_SECRET", "")          # /api/bot solo acepta peticiones de n8n con este secreto  # clave que usa el gateway para detener/reactivar el nodo
MANTENIMIENTO = {"on": False}  # el panel puede "detener" (simular caida) este nodo para demostrar el failover

# Neon (plan gratis) apaga la BD tras 5 min sin uso y cobra horas de cómputo:
# con Neon se late cada 15 min y no se dejan conexiones abiertas.
ES_NEON = "neon.tech" in DATABASE_URL
# Cloud Run define K_SERVICE. Ahí la CPU se congela sin peticiones: los bucles de fondo
# no sirven y el latido lo dispara Cloud Scheduler cada minuto (POST /tareas/latido).
EN_CLOUD_RUN = bool(os.getenv("K_SERVICE"))
LATIDO_SEG = int(os.getenv("LATIDO_SEG", "900" if ES_NEON else "60" if EN_CLOUD_RUN else "20"))
# Un nodo se ve "en línea" si latió en los últimos 3 minutos (sirve para latidos de 20 s y de 60 s)
UMBRAL_ONLINE_SEG = int(os.getenv("UMBRAL_ONLINE_SEG", str(max(LATIDO_SEG, 60) * 3)))
# /tareas/latido solo acepta tokens OIDC firmados por Google para esta cuenta de servicio y audiencia
TAREAS_SA = os.getenv("TAREAS_SA", "")
TAREAS_AUDIENCIA = os.getenv("TAREAS_AUDIENCIA", "centinela-tareas")
# En Cloud Run la IA del Lenovo se alcanza por el proxy HTTP de Tailscale (modo userspace)
OLLAMA_PROXY = os.getenv("OLLAMA_PROXY", "") or None
TS_SOCKET = os.getenv("TS_SOCKET", "")
POOL_MIN = int(os.getenv("POOL_MIN", "0" if ES_NEON else "1"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LIMITE_GLOBAL = int(os.getenv("LIMITE_GLOBAL", "150"))  # peticiones/min por IP a este nodo
CAMPANA_REPORTEROS = int(os.getenv("CAMPANA_REPORTEROS", "3"))
CAMPANA_VENTANA_MIN = int(os.getenv("CAMPANA_VENTANA_MIN", "15"))
INICIO = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("centinela")

CATEGORIAS = [
    "estafa",
    "telemarketing",
    "cobranza",
    "encuesta",
    "wangiri",
    "suplantacion",
    "extorsion",
    "otro",
]

# Prefijos frecuentes en estafas de "llamada perdida" (wangiri) y tarificación premium
PREFIJOS_RIESGO = [
    "+225", "+233", "+234", "+216", "+232", "+222", "+882", "+883",
    "+1268", "+1284", "+1473", "+1649", "+1767", "+1809", "+1829",
    "+1849", "+1876",
]

PAISES = {
    "+57": "Colombia", "+1": "EE. UU. / Caribe", "+52": "México", "+34": "España",
    "+44": "Reino Unido", "+51": "Perú", "+58": "Venezuela", "+593": "Ecuador",
    "+591": "Bolivia", "+56": "Chile", "+54": "Argentina", "+55": "Brasil",
    "+225": "Costa de Marfil", "+233": "Ghana", "+234": "Nigeria", "+216": "Túnez",
    "+232": "Sierra Leona", "+222": "Mauritania", "+882": "Red internacional",
    "+883": "Red internacional",
}

CAT_TXT = {
    "estafa": "estafa", "suplantacion": "falso banco o entidad", "cobranza": "cobranza",
    "telemarketing": "ventas / telemarketing", "wangiri": "llamada perdida internacional",
    "extorsion": "extorsión", "encuesta": "encuesta", "otro": "otro",
}

EMOJI = {"alto": "🔴", "medio": "🟠", "bajo": "🟢"}

CONSEJOS = [
    "Tu banco nunca te pide claves ni el código que llega por SMS. Si te lo piden, cuelga.",
    "No devuelvas llamadas perdidas de números extranjeros: pueden cobrarte tarifa premium.",
    "Si te meten prisa (\"tu cuenta se bloquea hoy\"), es una señal de estafa. Cuelga y verifica.",
    "\"Tu familiar está detenido y necesita plata\": cuelga y llama tú a tu familiar.",
    "Reporta aunque no hayas caído: tres reportes ponen un número en riesgo alto para todos.",
]
