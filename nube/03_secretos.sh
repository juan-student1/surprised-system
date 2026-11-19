#!/usr/bin/env bash
# =====================================================================
#  Paso 3 · Secretos en Secret Manager (sin que se vean en pantalla)
#  Los copia del .env de la VM actual por SSH/IAP. Si la VM no responde, los pide ocultos.
#  Uso:  bash nube/03_secretos.sh
# =====================================================================
source "$(dirname "$0")/config.sh"
CLAVES=(SAL_HASH CONTROL_TOKEN TELEGRAM_TOKEN TELEGRAM_CHAT_ID LLAMADAS_TOKEN GATEWAY_SECRET BOT_SECRET)
nombre_de(){ echo "centinela-$(echo "$1" | tr 'A-Z_' 'a-z-')"; }

azul "Leyendo /opt/centinela/.env de la VM $VM (por IAP; no se imprime)"
ENV_VM="$(gcloud compute ssh "$VM" --zone="$ZONA_VM" --tunnel-through-iap --quiet \
          --command='sudo cat /opt/centinela/.env' 2>/dev/null || true)"
[[ -n "$ENV_VM" ]] && verde "  leído" || amarillo "  No pude leer la VM: te pido cada valor (Enter = omitir)"

azul "Guardando secretos (solo centinela-run puede leerlos)"
for K in "${CLAVES[@]}"; do
  V="$(grep "^$K=" <<<"$ENV_VM" | tail -1 | cut -d= -f2- || true)"
  if [[ -z "$V" && -z "$ENV_VM" ]]; then read -rsp "  $K (no se ve al pegar): " V; echo; fi
  if [[ -n "$V" ]]; then guardar_secreto "$(nombre_de "$K")" "$V" "$SA_RUN"
  else echo "  - $K vacío, se omite"; fi
done
unset ENV_VM V

azul "Llave de Tailscale para Cloud Run (para llegar a la IA del Lenovo)"
echo "  Créala en https://login.tailscale.com/admin/settings/keys → Generate auth key:"
echo "  Reusable ✔  Ephemeral ✔  Pre-approved ✔  Expiración 90 días"
read -rsp "  Pega la llave tskey-auth-... (Enter = sin IA, el chat responde por reglas): " TS; echo
TS="$(printf '%s' "$TS" | tr -d '[:space:]')"
if [[ -n "$TS" && "$TS" != tskey-auth-* ]]; then
  echo "❌ Eso no es una auth key (debe empezar por tskey-auth-; las tskey-api- no sirven)"; exit 1; fi
if [[ -n "$TS" ]]; then guardar_secreto centinela-ts-authkey "$TS" "$SA_RUN"; fi
unset TS

verde "✅ Paso 3 listo. Sigue: bash nube/04_migrar_datos.sh"
