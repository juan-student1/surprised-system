#!/usr/bin/env bash
# =====================================================================
#  Paso 9 · Acceso de SOLO LECTURA para JP (rol de seguridad)
#  JP puede ver logs, Cloud Run, Cloud SQL, Scheduler, políticas de IAM y la lista de secretos
#  (nunca su valor). No puede crear, cambiar ni borrar nada.
#  Uso:   CORREO_JP=correo@dejp bash nube/09_lectura_jp.sh            # dar
#         CORREO_JP=correo@dejp bash nube/09_lectura_jp.sh quitar     # quitar (cierre del curso)
#  El correo de JP NO se escribe en el repo: se pasa como variable al correr.
# =====================================================================
source "$(dirname "$0")/config.sh"
[[ -n "${CORREO_JP:-}" ]] || { echo "❌ Falta CORREO_JP=… (la cuenta de Google de JP)"; exit 1; }
ACCION="${1:-dar}"
ROLES=(roles/logging.viewer roles/run.viewer roles/cloudsql.viewer roles/cloudscheduler.viewer
       roles/iam.securityReviewer roles/secretmanager.viewer)

azul "$([[ $ACCION == quitar ]] && echo Quitando || echo Dando) roles de lectura a $CORREO_JP en $PROYECTO"
for r in "${ROLES[@]}"; do
  if [[ $ACCION == quitar ]]; then
    gcloud projects remove-iam-policy-binding "$PROYECTO" --member="user:$CORREO_JP" --role="$r" --condition=None >/dev/null 2>&1 \
      && echo "  ✖ $r" || echo "  = $r (no lo tenía)"
  else
    gcloud projects add-iam-policy-binding "$PROYECTO" --member="user:$CORREO_JP" --role="$r" --condition=None >/dev/null \
      && echo "  ✔ $r"
  fi
done

azul "Roles actuales de $CORREO_JP"
gcloud projects get-iam-policy "$PROYECTO" --flatten="bindings[].members" \
  --filter="bindings.members:user:$CORREO_JP" --format="value(bindings.role)"
verde "✅ Listo. JP entra a https://console.cloud.google.com con su cuenta y elige el proyecto $PROYECTO."
