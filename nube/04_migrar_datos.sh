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
for _ in $(seq 1 20); do grep -q "ready for new connections" /tmp/proxy.log && break; sleep 1; done
grep -q "ready for new connections" /tmp/proxy.log || { echo "❌ El túnel no abrió:"; cat /tmp/proxy.log; exit 1; }

azul "Origen: el DATABASE_URL de Supabase que ya funciona en la VM $VM (no se imprime)"
S="$(gcloud compute ssh "$VM" --zone="$ZONA_VM" --tunnel-through-iap --quiet \
      --command='sudo grep "^DATABASE_URL=" /opt/centinela/.env' 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
if [[ "$S" == *pooler.supabase.com* ]]; then
  verde "  leído de la VM"
else
  amarillo "  No pude leerlo de la VM; pégalo a mano"
  read -rsp "Link COMPLETO del Session pooler de Supabase, con la contraseña (no se ve al pegar): " S; echo
  [[ "$S" == *pooler.supabase.com* ]] || { echo "❌ No es el Session pooler"; exit 1; }
  [[ "$S" == *YOUR-PASSWORD* ]] && { echo "❌ El link aún dice [YOUR-PASSWORD]: reemplázalo por la contraseña"; exit 1; }
  # Codifica los símbolos de la contraseña (/ # ? @ ...) para que no rompan la URL
  S="$(U="$S" python3 -c 'import os,urllib.parse as u;s=os.environ["U"].strip();e,r=s.split("://",1);c,h=r.rsplit("@",1);us,pw=c.split(":",1);print(f"{e}://{us}:{u.quote(u.unquote(pw),safe=str())}@{h}")')"
fi
export S
CLAVE_APP="$(gcloud secrets versions access latest --secret=centinela-db-clave-app)"
CLAVE_JP="$(gcloud secrets versions access latest --secret=centinela-db-clave-jp)"
export D="postgresql://centinela_app:$CLAVE_APP@127.0.0.1:6543/$BD" CLAVE_JP; unset CLAVE_APP

# psql/pg_dump 17 en Docker: Cloud Shell trae una versión vieja que no sirve contra Supabase
docker run --rm --network host -e S -e D -e CLAVE_JP \
  -v "$REPO/db:/db:ro" -v "$REPO/nube/_migrar_en_docker.sh:/migrar.sh:ro" postgres:17 bash /migrar.sh
unset S D CLAVE_JP
verde "✅ Paso 4 listo. Sigue: bash nube/05_desplegar.sh"
