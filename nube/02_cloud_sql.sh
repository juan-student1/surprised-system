#!/usr/bin/env bash
# =====================================================================
#  Paso 2 · Cloud SQL (PostgreSQL 17) — tarda ~5-10 min en crearse
#  Uso:  bash nube/02_cloud_sql.sh
# =====================================================================
source "$(dirname "$0")/config.sh"

azul "Instancia $SQL"
if gcloud sql instances describe "$SQL" >/dev/null 2>&1; then
  echo "  = ya existe"
else
  # --edition=ENTERPRISE: sin esto PG17 crea "Enterprise Plus" (mucho más cara)
  # db-f1-micro + HDD 10 GB + zonal = lo más barato. Conector obligatorio = nadie entra
  # por IP directa: solo Cloud Run y el Auth Proxy, ambos autenticados con IAM.
  gcloud sql instances create "$SQL" \
    --database-version=POSTGRES_17 --edition=ENTERPRISE --tier=db-f1-micro \
    --region="$REGION" --availability-type=zonal \
    --storage-type=HDD --storage-size=10 --no-storage-auto-increase \
    --backup-start-time=08:00 --retained-backups-count=7 \
    --connector-enforcement=REQUIRED --ssl-mode=ENCRYPTED_ONLY \
    --deletion-protection
fi

azul "Base de datos $BD"
gcloud sql databases describe "$BD" --instance="$SQL" >/dev/null 2>&1 && echo "  = ya existe" \
  || { gcloud sql databases create "$BD" --instance="$SQL" >/dev/null; echo "  ✔ creada"; }

azul "Usuario centinela_app (dueño de las tablas, lo usa JE)"
if existe_secreto centinela-db-clave-app; then
  CLAVE_APP="$(gcloud secrets versions access latest --secret=centinela-db-clave-app)"; echo "  = clave ya guardada"
else
  CLAVE_APP="$(openssl rand -hex 24)"     # solo letras y números: no rompe la URL
  gcloud sql users create centinela_app --instance="$SQL" --password="$CLAVE_APP" >/dev/null
  guardar_secreto centinela-db-clave-app "$CLAVE_APP"
fi
# centinela_jp se crea por SQL en el paso 4 (así NO queda como cloudsqlsuperuser)
existe_secreto centinela-db-clave-jp || guardar_secreto centinela-db-clave-jp "$(openssl rand -hex 24)"

azul "DATABASE_URL de JE (socket Unix de Cloud Run, nunca por IP)"
guardar_secreto centinela-database-url \
  "postgresql://centinela_app:$CLAVE_APP@/$BD?host=/cloudsql/$CONEXION" "$SA_RUN"
unset CLAVE_APP

verde "✅ Paso 2 listo ($CONEXION). Sigue: bash nube/03_secretos.sh"
