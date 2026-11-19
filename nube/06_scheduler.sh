#!/usr/bin/env bash
# =====================================================================
#  Paso 6 · Cloud Scheduler: latido de JE cada minuto (con token OIDC)
#  Uso:  bash nube/06_scheduler.sh
# =====================================================================
source "$(dirname "$0")/config.sh"
URL="$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)')"
NUM="$(gcloud projects describe "$PROYECTO" --format='value(projectNumber)')"

azul "Permiso: el agente de Cloud Scheduler puede firmar tokens SOLO como centinela-tareas"
gcloud iam service-accounts add-iam-policy-binding "$SA_TAREAS" \
  --member="serviceAccount:service-$NUM@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountTokenCreator --condition=None >/dev/null && echo "  ✔"

azul "Trabajo centinela-latido (* * * * *)"
ARGS=(--location="$REGION" --schedule="* * * * *" --time-zone="America/Bogota"
      --uri="$URL/tareas/latido" --http-method=POST --attempt-deadline=60s
      --oidc-service-account-email="$SA_TAREAS" --oidc-token-audience=centinela-tareas)
if gcloud scheduler jobs describe centinela-latido --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http centinela-latido "${ARGS[@]}" >/dev/null; echo "  ↻ actualizado"
else
  gcloud scheduler jobs create http centinela-latido "${ARGS[@]}" >/dev/null; echo "  ✔ creado"
fi
gcloud scheduler jobs run centinela-latido --location="$REGION"
sleep 8
azul "Resultado del último latido"
gcloud scheduler jobs describe centinela-latido --location="$REGION" --format='value(lastAttemptTime,status)'
curl -s "$URL/api/cluster" | python3 -c 'import json,sys;[print("  ",n["nombre"],n["rol"],"online" if n["online"] else "OFFLINE",n["version"]) for n in json.load(sys.stdin)["nodos"]]'
verde "✅ Paso 6 listo. Sigue: cambiar el gateway (ver docs/15) y bash nube/07_llave_jp.sh"
