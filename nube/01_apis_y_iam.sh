#!/usr/bin/env bash
# =====================================================================
#  Paso 1 · APIs y cuentas de servicio (IAM)
#  Uso:  bash nube/01_apis_y_iam.sh
#  Opcional: CORREO_PROFE=x@y.com CORREO_JP=z@y.com bash nube/01_apis_y_iam.sh
# =====================================================================
source "$(dirname "$0")/config.sh"

azul "Habilitando APIs (tarda 1-2 min la primera vez)"
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com iam.googleapis.com

azul "Cuentas de servicio (una por función)"
crear_sa(){ gcloud iam service-accounts describe "$1@$PROYECTO.iam.gserviceaccount.com" >/dev/null 2>&1 \
  && echo "  = $1" || { gcloud iam service-accounts create "$1" --display-name="$2" >/dev/null; echo "  ✔ $1"; }; }
crear_sa centinela-run    "Centinela · API en Cloud Run (nodo JE)"
crear_sa centinela-tareas "Centinela · firma el latido de Cloud Scheduler"
crear_sa centinela-jp     "Centinela · nodo JP hacia Cloud SQL"
sleep 5   # IAM tarda unos segundos en ver las cuentas nuevas

azul "Roles a nivel de proyecto (solo los indispensables)"
rol(){ gcloud projects add-iam-policy-binding "$PROYECTO" --member="$1" --role="$2" --condition=None >/dev/null; echo "  ✔ $1 → $2"; }
rol "serviceAccount:$SA_RUN" roles/cloudsql.client     # conectarse a Cloud SQL (no administrarlo)
rol "serviceAccount:$SA_JP"  roles/cloudsql.client     # JP solo se conecta, nada más
# centinela-tareas NO recibe roles de proyecto: solo sirve para firmar tokens OIDC.
# Los secretos se dan uno por uno a centinela-run en 02/03 (no secretAccessor de todo el proyecto).

if [[ -n "${CORREO_PROFE:-}" ]]; then
  rol "user:$CORREO_PROFE" roles/viewer                 # el profesor ve todo, no cambia nada
fi
if [[ -n "${CORREO_JP:-}" ]]; then
  for r in roles/run.viewer roles/cloudsql.viewer roles/logging.viewer roles/cloudscheduler.viewer; do
    rol "user:$CORREO_JP" "$r"; done
fi

verde "✅ Paso 1 listo. Sigue: bash nube/02_cloud_sql.sh"
