#!/usr/bin/env bash
# =====================================================================
#  CENTINELA · Conectar el nodo JP a Cloud SQL (Google Cloud)
#  Instala Cloud SQL Auth Proxy como servicio: túnel cifrado y autenticado con IAM
#  (cuenta centinela-jp, rol cloudsql.client). Cloud SQL no acepta conexiones por IP directa.
#
#  Uso (en la VM de JP, desde la carpeta del proyecto):
#     sudo bash servidor/conectar_cloudsql.sh /ruta/centinela-jp.json PROYECTO:us-east1:centinela-db
# =====================================================================
set -euo pipefail
LLAVE="${1:-}"; CONEXION="${2:-}"
[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo"; exit 1; }
[[ -f "$LLAVE" && "$CONEXION" == *:*:* ]] || { echo "Uso: sudo bash $0 /ruta/centinela-jp.json PROYECTO:REGION:INSTANCIA"; exit 1; }
VERSION=v2.14.1; PUERTO=6432; ENV=/opt/centinela/.env
id centinela >/dev/null 2>&1 || { echo "❌ Primero instala el nodo: sudo bash servidor/instalar_nodo.sh JP"; exit 1; }

case "$(uname -m)" in x86_64) ARQ=amd64 ;; aarch64|arm64) ARQ=arm64 ;; *) echo "Arquitectura no soportada"; exit 1 ;; esac
if [[ ! -x /usr/local/bin/cloud-sql-proxy ]]; then
  echo "▶ Descargando Cloud SQL Auth Proxy $VERSION ($ARQ)"
  curl -fsSLo /usr/local/bin/cloud-sql-proxy \
    "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/$VERSION/cloud-sql-proxy.linux.$ARQ"
  chmod 755 /usr/local/bin/cloud-sql-proxy
fi

echo "▶ Guardando la llave en /etc/centinela (solo la lee el usuario centinela)"
install -d -m 750 -o root -g centinela /etc/centinela
install -m 640 -o root -g centinela "$LLAVE" /etc/centinela/sa-jp.json

cat > /etc/systemd/system/cloudsql-proxy.service <<UNIT
[Unit]
Description=Cloud SQL Auth Proxy (Centinela JP -> $CONEXION)
After=network-online.target
Wants=network-online.target

[Service]
User=centinela
ExecStart=/usr/local/bin/cloud-sql-proxy --credentials-file /etc/centinela/sa-jp.json --address 127.0.0.1 --port $PUERTO $CONEXION
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
mkdir -p /etc/systemd/system/centinela.service.d
printf '[Unit]\nWants=cloudsql-proxy.service\nAfter=cloudsql-proxy.service\n' > /etc/systemd/system/centinela.service.d/cloudsql.conf
systemctl daemon-reload
systemctl enable --now cloudsql-proxy
sleep 3; systemctl is-active --quiet cloudsql-proxy || { journalctl -u cloudsql-proxy -n 20 --no-pager; exit 1; }

read -rsp "Clave de centinela_jp (te la da Juan; no se ve al pegar): " CLAVE; echo
[[ "$CLAVE" =~ ^[A-Za-z0-9]+$ ]] || { echo "❌ La clave debe ser solo letras y números"; exit 1; }
cp -p "$ENV" "$ENV.supabase.bak"          # respaldo de la configuración vieja (600, solo root/centinela)
sed -i '/^DATABASE_URL=/d' "$ENV"
printf 'DATABASE_URL=postgresql://centinela_jp:%s@127.0.0.1:%s/centinela\n' "$CLAVE" "$PUERTO" >> "$ENV"
unset CLAVE
systemctl restart centinela

for i in $(seq 1 30); do
  if curl -sf localhost:8000/health | grep -q '"db":true'; then echo "✅ JP conectado a Cloud SQL"; exit 0; fi; sleep 1
done
echo "✘ La API no ve la BD. Revisa: journalctl -u cloudsql-proxy -n 30 --no-pager"
echo "   Volver a Supabase: sudo cp $ENV.supabase.bak $ENV && sudo systemctl restart centinela"; exit 1
