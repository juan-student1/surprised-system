# =====================================================================
#  CENTINELA · Variables comunes de los scripts de nube/ (Cloud Shell)
#  No se ejecuta solo: lo cargan los demás scripts con `source`.
# =====================================================================
set -euo pipefail
PROYECTO="${PROYECTO:-$(gcloud config get-value project 2>/dev/null)}"
[[ -n "$PROYECTO" ]] || { echo "❌ Primero: gcloud config set project ID_DEL_PROYECTO"; exit 1; }
gcloud auth print-access-token >/dev/null 2>&1 || {
  echo "❌ La sesión de gcloud se cerró (Cloud Shell se reconectó). Corre:  gcloud auth login"; exit 1; }
REGION=us-east1                 # misma región de la VM, del nivel gratis y cerca de Colombia
ZONA_VM=us-east1-b
VM=centinela-je                 # VM vieja (se borra al final con 99_borrar_vm.sh)
SERVICIO=centinela-je           # servicio de Cloud Run (nodo JE)
SQL=centinela-db                # instancia de Cloud SQL
BD=centinela                    # base de datos
CONEXION="$PROYECTO:$REGION:$SQL"
# Cuentas de servicio (una por función = privilegio mínimo)
SA_RUN="centinela-run@$PROYECTO.iam.gserviceaccount.com"        # identidad de la API en Cloud Run
SA_TAREAS="centinela-tareas@$PROYECTO.iam.gserviceaccount.com"  # firma el latido de Cloud Scheduler
SA_JP="centinela-jp@$PROYECTO.iam.gserviceaccount.com"          # el nodo JP llega a Cloud SQL
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROXY_VERSION=v2.14.1

verde(){ echo -e "\e[1;32m$*\e[0m"; }
azul(){ echo -e "\n\e[1;34m▶ $*\e[0m"; }
amarillo(){ echo -e "\e[1;33m$*\e[0m"; }

existe_secreto(){ gcloud secrets describe "$1" >/dev/null 2>&1; }

# guardar_secreto NOMBRE VALOR [SA_LECTORA]
# Crea el secreto (o una versión nueva solo si cambió) sin imprimir el valor.
guardar_secreto(){
  local nombre="$1" valor="$2" lector="${3:-}"
  if existe_secreto "$nombre"; then
    if [[ "$(gcloud secrets versions access latest --secret="$nombre" 2>/dev/null)" != "$valor" ]]; then
      printf '%s' "$valor" | gcloud secrets versions add "$nombre" --data-file=- >/dev/null
      echo "  ↻ $nombre (versión nueva)"
    else echo "  = $nombre (sin cambios)"; fi
  else
    printf '%s' "$valor" | gcloud secrets create "$nombre" --replication-policy=user-managed \
      --locations="$REGION" --labels=app=centinela --data-file=- >/dev/null
    echo "  ✔ $nombre"
  fi
  if [[ -n "$lector" ]]; then
    gcloud secrets add-iam-policy-binding "$nombre" --member="serviceAccount:$lector" \
      --role=roles/secretmanager.secretAccessor --condition=None >/dev/null
  fi
}

# Proxy de Cloud SQL (para migrar desde Cloud Shell)
asegurar_proxy(){
  if ! command -v cloud-sql-proxy >/dev/null; then
    mkdir -p "$HOME/.local/bin"
    curl -fsSLo "$HOME/.local/bin/cloud-sql-proxy" \
      "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/$PROXY_VERSION/cloud-sql-proxy.linux.amd64"
    chmod +x "$HOME/.local/bin/cloud-sql-proxy"; export PATH="$HOME/.local/bin:$PATH"
  fi
}
