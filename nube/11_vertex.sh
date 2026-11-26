#!/usr/bin/env bash
# =====================================================================
#  Paso 11 · Vertex AI (Gemini) como respaldo de la IA local — docs/16_VERTEX_AI.md
#  dar    : habilita la API de Vertex AI y da roles/aiplatform.user SOLO a centinela-run
#  probar : una llamada mínima a Gemini con TU identidad (confirma modelo y región; cuesta centavos)
#  quitar : retira el rol (la API puede quedar habilitada; sin rol nadie la usa)
#  Después de "dar": bash nube/05_desplegar.sh (detecta la API y enciende Vertex en JE).
#  Uso:  bash nube/11_vertex.sh dar|probar|quitar
# =====================================================================
source "$(dirname "$0")/config.sh"
MODELO="${VERTEX_MODELO:-gemini-3.8-flash}"
UBICACION="${VERTEX_REGION:-global}"
case "${1:-}" in
  dar)
    azul "Habilitando la API de Vertex AI (aiplatform.googleapis.com)"
    gcloud services enable aiplatform.googleapis.com && echo "  ✔"
    azul "Rol mínimo para llamar a Gemini: roles/aiplatform.user → $SA_RUN"
    gcloud projects add-iam-policy-binding "$PROYECTO" --member="serviceAccount:$SA_RUN" \
      --role=roles/aiplatform.user --condition=None >/dev/null && echo "  ✔"
    verde "✅ Listo. Sigue: bash nube/11_vertex.sh probar  y luego  bash nube/05_desplegar.sh" ;;
  probar)
    if [[ "$UBICACION" == global ]]; then HOST=aiplatform.googleapis.com; else HOST="$UBICACION-aiplatform.googleapis.com"; fi
    azul "Probando $MODELO en $UBICACION (una llamada de ~20 tokens)"
    curl -sS -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "content-type: application/json" \
      "https://$HOST/v1/projects/$PROYECTO/locations/$UBICACION/publishers/google/models/$MODELO:generateContent" \
      -d '{"contents":[{"role":"user","parts":[{"text":"Responde solo: ok"}]}],"generationConfig":{"maxOutputTokens":256}}' \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  respuesta:", "".join(p.get("text","") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought")).strip() if "candidates" in d else d)' ;;
  quitar)
    gcloud projects remove-iam-policy-binding "$PROYECTO" --member="serviceAccount:$SA_RUN" \
      --role=roles/aiplatform.user --condition=None >/dev/null && verde "✔ Rol retirado. Redesplegar JE apaga Vertex si la API se deshabilita." ;;
  *) echo "Uso: bash nube/11_vertex.sh dar|probar|quitar"; exit 1 ;;
esac
