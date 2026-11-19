#!/usr/bin/env bash
# =====================================================================
#  Paso final · Borrar la VM vieja (solo cuando JE en Cloud Run ya esté probado)
#  Borra la VM, su disco y libera la IP efímera (deja de cobrar ~3,6 USD/mes).
#  Uso:  bash nube/99_borrar_vm.sh
# =====================================================================
source "$(dirname "$0")/config.sh"
URL="$(gcloud run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)' 2>/dev/null || true)"
[[ -n "$URL" ]] && curl -sf "$URL/health" >/dev/null || { echo "❌ JE en Cloud Run no responde: NO borro la VM"; exit 1; }
amarillo "Se borrará la VM $VM ($ZONA_VM) con su disco. No se puede deshacer."
read -rp "Escribe el nombre de la VM para confirmar: " C
[[ "$C" == "$VM" ]] || { echo "Cancelado"; exit 1; }
gcloud compute instances delete "$VM" --zone="$ZONA_VM" --delete-disks=all --quiet
verde "✅ VM borrada. Falta a mano: borrar la máquina centinela-je vieja en https://login.tailscale.com/admin/machines"
