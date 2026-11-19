#!/usr/bin/env bash
# =====================================================================
#  Paso 7 · Credenciales para que JP llegue a Cloud SQL
#  Crea una llave de la cuenta centinela-jp (rol único: cloudsql.client).
#  Uso:  bash nube/07_llave_jp.sh
# =====================================================================
source "$(dirname "$0")/config.sh"
LLAVE="$HOME/centinela-jp.json"
umask 077
gcloud iam service-accounts keys create "$LLAVE" --iam-account="$SA_JP"
verde "✅ Llave creada: $LLAVE"
cat <<TXT

  1. Descárgala:            cloudshell download $LLAVE
  2. Pásala a JP por un canal privado (nunca al grupo ni a GitHub).
  3. JP necesita también la clave de la BD; muéstrala SOLO cuando JP esté listo:
        gcloud secrets versions access latest --secret=centinela-db-clave-jp; echo
  4. En la VM de JP:
        sudo bash servidor/conectar_cloudsql.sh /ruta/centinela-jp.json $CONEXION
  5. Cuando JP confirme, bórrala de Cloud Shell:   rm $LLAVE
  Para revocarla:  gcloud iam service-accounts keys list --iam-account=$SA_JP
                   gcloud iam service-accounts keys delete ID --iam-account=$SA_JP
TXT
