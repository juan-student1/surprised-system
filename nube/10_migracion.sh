#!/usr/bin/env bash
# =====================================================================
#  Paso 10 · Aplicar una migración SQL de db/ a Cloud SQL (como centinela_app)
#  Abre el Auth Proxy con tu identidad de gcloud, lee la clave de Secret Manager
#  (sin imprimirla), corre el archivo en una transacción y cierra el túnel.
#  Las migraciones son idempotentes (if not exists): se pueden correr varias veces.
#  Uso:  bash nube/10_migracion.sh db/004_leads_y_seguridad.sql
# =====================================================================
source "$(dirname "$0")/config.sh"
ARCHIVO="${1:-}"
[[ "$ARCHIVO" =~ ^db/[0-9]{3}_[a-z0-9_]+\.sql$ && -f "$REPO/$ARCHIVO" ]] || {
  echo "❌ Uso: bash nube/10_migracion.sh db/NNN_nombre.sql (un archivo de db/)"; exit 1; }
command -v psql >/dev/null || { echo "❌ Falta psql (cliente de PostgreSQL)"; exit 1; }
asegurar_proxy

azul "Túnel a $CONEXION (Auth Proxy, autenticado con tu cuenta de gcloud)"
LOG="$(mktemp)"
cloud-sql-proxy --gcloud-auth --address 127.0.0.1 --port 6544 "$CONEXION" >"$LOG" 2>&1 &
PID_PROXY=$!; trap 'kill $PID_PROXY 2>/dev/null' EXIT
for _ in $(seq 1 20); do grep -q "ready for new connections" "$LOG" && break; sleep 1; done
grep -q "ready for new connections" "$LOG" || { echo "❌ El túnel no abrió:"; cat "$LOG"; exit 1; }

azul "Aplicando $ARCHIVO como centinela_app (una sola transacción)"
PGPASSWORD="$(gcloud secrets versions access latest --secret=centinela-db-clave-app --project "$PROYECTO")" \
  psql "host=127.0.0.1 port=6544 dbname=$BD user=centinela_app sslmode=disable" \
       -v ON_ERROR_STOP=1 -q --single-transaction -f "$REPO/$ARCHIVO"

azul "Tablas del esquema public"
PGPASSWORD="$(gcloud secrets versions access latest --secret=centinela-db-clave-app --project "$PROYECTO")" \
  psql "host=127.0.0.1 port=6544 dbname=$BD user=centinela_app sslmode=disable" -At \
       -c "select string_agg(table_name, ', ' order by table_name) from information_schema.tables where table_schema='public'"
verde "✅ Migración $ARCHIVO aplicada."
