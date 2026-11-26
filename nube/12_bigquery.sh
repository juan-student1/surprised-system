#!/usr/bin/env bash
# =====================================================================
#  Paso 12 · Analítica: BigQuery + exportación diaria (Fase 4 · docs/17_LOOKER_STUDIO.md)
#  preparar : dataset centinela_analitica (us-east1) + permisos mínimos para centinela-run
#             (bigquery.dataEditor SOLO en el dataset, bigquery.jobUser en el proyecto)
#  programar: trabajo de Cloud Scheduler centinela-exportar (diario 01:15 Colombia, OIDC) + una corrida ya
#  vistas   : crea o actualiza las vistas de analitica/vistas.sql
#  Orden:  preparar → bash nube/05_desplegar.sh → programar → vistas
#  Usa la API REST de BigQuery con curl (sirve en Cloud Shell y en cualquier equipo con gcloud).
# =====================================================================
source "$(dirname "$0")/config.sh"
DATASET="${BQ_DATASET:-centinela_analitica}"
UBICACION="${BQ_UBICACION:-us-east1}"
API="https://bigquery.googleapis.com/bigquery/v2/projects/$PROYECTO"

consulta(){   # consulta "SQL" → corre una sentencia de BigQuery (DDL/DCL) y muestra errores si los hay
  local sql="$1"
  SQL="$sql" UBI="$UBICACION" python3 -c 'import json,os;print(json.dumps({"query":os.environ["SQL"],"useLegacySql":False,"location":os.environ["UBI"],"timeoutMs":60000}))' \
  | curl -sS -X POST "$API/queries" -H "Authorization: Bearer $(gcloud auth print-access-token)" \
      -H "content-type: application/json" --data-binary @- \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("error"); print("  ❌", e["message"]) if e else print("  ✔"); sys.exit(1 if e else 0)'
}

case "${1:-}" in
  preparar)
    azul "Dataset $DATASET en $UBICACION"
    CODIGO=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$API/datasets" -H "Authorization: Bearer $(gcloud auth print-access-token)" \
      -H "content-type: application/json" \
      -d "{\"datasetReference\":{\"datasetId\":\"$DATASET\"},\"location\":\"$UBICACION\",\"description\":\"Centinela: datos AGREGADOS y ANONIMIZADOS para Looker Studio\",\"labels\":{\"app\":\"centinela\"}}")
    case "$CODIGO" in 200) echo "  ✔ creado";; 409) echo "  = ya existía";; *) echo "  ❌ HTTP $CODIGO"; exit 1;; esac
    azul "centinela-run puede escribir SOLO en este dataset (bigquery.dataEditor)"
    consulta "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$PROYECTO.$DATASET\` TO \"serviceAccount:$SA_RUN\""
    azul "centinela-run puede lanzar trabajos de carga (bigquery.jobUser, nivel proyecto: así lo exige BigQuery)"
    gcloud projects add-iam-policy-binding "$PROYECTO" --member="serviceAccount:$SA_RUN" \
      --role=roles/bigquery.jobUser --condition=None >/dev/null && echo "  ✔"
    verde "✅ Listo. Sigue: bash nube/05_desplegar.sh  (detecta el dataset y enciende la exportación en JE)" ;;
  programar)
    URL="$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)')"
    azul "Trabajo centinela-exportar (todos los días 01:15 hora Colombia, OIDC como centinela-tareas)"
    ARGS=(--location="$REGION" --schedule="15 1 * * *" --time-zone="America/Bogota"
          --uri="$URL/tareas/exportar" --http-method=POST --attempt-deadline=180s
          --oidc-service-account-email="$SA_TAREAS" --oidc-token-audience=centinela-tareas
          --max-retry-attempts=2 --min-backoff=300s)
    if gcloud scheduler jobs describe centinela-exportar --location="$REGION" >/dev/null 2>&1; then
      gcloud scheduler jobs update http centinela-exportar "${ARGS[@]}" >/dev/null; echo "  ↻ actualizado"
    else
      gcloud scheduler jobs create http centinela-exportar "${ARGS[@]}" >/dev/null; echo "  ✔ creado"
    fi
    azul "Primera exportación ahora (carga toda la historia)"
    gcloud scheduler jobs run centinela-exportar --location="$REGION"
    for _ in $(seq 1 12); do sleep 10
      E="$(gcloud scheduler jobs describe centinela-exportar --location="$REGION" --format='value(lastAttemptTime,status.code)')"
      [[ -n "${E%%[[:space:]]*}" ]] && break; done
    echo "  último intento: ${E:-sin datos aún} (código vacío = OK)"
    verde "✅ Listo. Sigue: bash nube/12_bigquery.sh vistas" ;;
  vistas)
    azul "Vistas de analitica/vistas.sql en $PROYECTO.$DATASET"
    N=0
    while IFS= read -r -d $'\x1e' SENTENCIA; do
      [[ -z "${SENTENCIA//[[:space:]]/}" ]] && continue
      NOMBRE="$(grep -o 'VIEW `[^`]*`' <<<"$SENTENCIA" | head -1 | cut -d. -f3 | tr -d '`')"
      printf '  %s' "$NOMBRE"; consulta "$SENTENCIA" || exit 1; N=$((N+1))
    done < <(P="$PROYECTO" D="$DATASET" python3 -c '
import os, re, sys
sql = open(sys.argv[1]).read().replace("{{P}}", os.environ["P"]).replace("{{D}}", os.environ["D"])
sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
for s in re.split(r";\s*\n\s*\n", sql):
    if s.strip(): sys.stdout.write(s.strip().rstrip(";") + "\x1e")' "$REPO/analitica/vistas.sql")
    verde "✅ $N vistas listas. Sigue: docs/17_LOOKER_STUDIO.md" ;;
  *) echo "Uso: bash nube/12_bigquery.sh preparar|programar|vistas"; exit 1 ;;
esac
