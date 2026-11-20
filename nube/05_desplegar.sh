#!/usr/bin/env bash
# =====================================================================
#  Paso 5 · Desplegar la API (nodo JE) en Cloud Run
#  Construye la imagen con Cloud Build desde servidor/app (Dockerfile) y la publica.
#  Se usa también para ACTUALIZAR después de un git pull.
#  Uso:  bash nube/05_desplegar.sh
# =====================================================================
source "$(dirname "$0")/config.sh"

SECRETOS="DATABASE_URL=centinela-database-url:latest"
for K in SAL_HASH CONTROL_TOKEN TELEGRAM_TOKEN TELEGRAM_CHAT_ID LLAMADAS_TOKEN GATEWAY_SECRET BOT_SECRET TS_AUTHKEY; do
  n="centinela-$(echo "$K" | tr 'A-Z_' 'a-z-')"
  existe_secreto "$n" && SECRETOS+=",$K=$n:latest"
done
VARS="NODO_NOMBRE=JE|NODO_ROL=principal|LOCAL_DB=/tmp/local.db|CORS_ORIGINS=*"
VARS+="|OLLAMA_URL=http://centinela-ia.tailaf5c0b.ts.net:11434|OLLAMA_MODEL=centinela"   # nombre completo para el proxy de Tailscale; modelo acotado del Lenovo
VARS+="|TAREAS_SA=$SA_TAREAS|TAREAS_AUDIENCIA=centinela-tareas"
VARS+="|TS_HOSTNAME=centinela-je-run|TS_SOCKET=/tmp/tailscale/tailscaled.sock"
# Con TS_TAGS=tag:centinela-run (y una llave creada con ese tag) las ACL limitan a JE a la IA. Ver docs/15 §2.6
[[ -n "${TS_TAGS:-}" ]] && VARS+="|TS_TAGS=$TS_TAGS"
existe_secreto centinela-ts-authkey && VARS+="|OLLAMA_PROXY=http://localhost:1055"

azul "Desplegando $SERVICIO en $REGION (la primera vez tarda ~4 min)"
# max-instances=1: el modo mantenimiento (demo de failover) vive en memoria de UNA instancia.
# --set-env-vars usa el separador | porque los correos de las cuentas de servicio llevan @.
# min-instances=0 + facturación por petición = casi gratis; Scheduler la mantiene caliente.
gcloud run deploy "$SERVICIO" --source "$REPO/servidor/app" --region "$REGION" --quiet \
  --service-account "$SA_RUN" --allow-unauthenticated \
  --add-cloudsql-instances "$CONEXION" \
  --set-secrets "$SECRETOS" --set-env-vars "^|^$VARS" \
  --execution-environment gen2 --cpu 1 --memory 512Mi --cpu-boost \
  --min-instances 0 --max-instances 1 --concurrency 40 --timeout 120 \
  --labels app=centinela

URL="$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)')"
azul "Probando $URL/health"
curl -s "$URL/health"; echo
verde "✅ Paso 5 listo. URL de JE: $URL"
echo "   Sigue: bash nube/06_scheduler.sh"
