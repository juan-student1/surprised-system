#!/usr/bin/env bash
# =====================================================================
#  Paso 4 · Migrar los datos de Supabase a Cloud SQL
#  Se puede correr VARIAS veces: vacía el destino y vuelve a copiar.
#  Córrelo una vez para probar y OTRA justo antes de cambiar el gateway (paso 6).
#  Uso:  bash nube/04_migrar_datos.sh
# =====================================================================
source "$(dirname "$0")/config.sh"
asegurar_proxy

azul "Abriendo túnel seguro a Cloud SQL (Auth Proxy, autenticado con tu cuenta)"
cloud-sql-proxy --gcloud-auth --address 127.0.0.1 --port 6543 "$CONEXION" >/tmp/proxy.log 2>&1 &
PID_PROXY=$!; trap 'kill $PID_PROXY 2>/dev/null' EXIT
for i in $(seq 1 20); do grep -q "ready for new connections" /tmp/proxy.log && break; sleep 1; done

read -rsp "Link COMPLETO del Session pooler de Supabase (no se ve al pegar): " S; echo
[[ "$S" == *pooler.supabase.com* ]] || { echo "❌ No es el Session pooler"; exit 1; }
export S
export D="postgresql://centinela_app:$(gcloud secrets versions access latest --secret=centinela-db-clave-app)@127.0.0.1:6543/$BD"
export CLAVE_JP="$(gcloud secrets versions access latest --secret=centinela-db-clave-jp)"

# psql/pg_dump 17 en Docker: Cloud Shell trae una versión vieja que no sirve contra Supabase
docker run --rm --network host -e S -e D -e CLAVE_JP \
  -v "$REPO/db:/db:ro" -v "$REPO/nube/_migrar_en_docker.sh:/migrar.sh:ro" postgres:17 bash /migrar.sh
unset S D CLAVE_JP
verde "✅ Paso 4 listo. Sigue: bash nube/05_desplegar.sh"
