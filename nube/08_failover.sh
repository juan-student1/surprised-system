#!/usr/bin/env bash
# =====================================================================
#  Demo de failover con IAM: se le quita a "allUsers" el permiso de invocar JE.
#  Cloud Run responde 403 (sin X-Centinela-Nodo) y el gateway salta a JP.
#  Uso:  bash nube/08_failover.sh apagar | prender | estado
# =====================================================================
source "$(dirname "$0")/config.sh"
GATEWAY="${GATEWAY:-https://centinela.juan-gallego-sec.workers.dev}"
case "${1:-estado}" in
  apagar)  gcloud run services remove-iam-policy-binding "$SERVICIO" --region "$REGION" \
             --member=allUsers --role=roles/run.invoker >/dev/null
           amarillo "JE ya no acepta peticiones públicas (403). Espera ~30-60 s a que IAM propague." ;;
  prender) gcloud run services add-iam-policy-binding "$SERVICIO" --region "$REGION" \
             --member=allUsers --role=roles/run.invoker >/dev/null
           verde "JE vuelve a ser público. El gateway lo retoma en ≤30 s." ;;
  estado)  ;;
  *) echo "Uso: $0 apagar|prender|estado"; exit 1 ;;
esac
curl -s "$GATEWAY/gateway/estado" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("Activo:",d["activo"]);[print(" ",n["nombre"],"online" if n["online"] else "caído ("+n.get("error","")+")") for n in d["nodos"]]'
