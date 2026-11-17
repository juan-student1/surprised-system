#!/usr/bin/env bash
# =====================================================================
#  CENTINELA · Reparación rápida del Lenovo (centinela-ia)
#  - Ollama: 1 petición a la vez, se descarga a los 10 min (límites del paso 3)
#  - Tailscale Funnel: vuelve a publicar /webhook para que Telegram llegue a n8n
#  - Reinicia n8n para que le vuelva a decir a Telegram dónde entregar los mensajes
#
#  Uso:  sudo bash ia/reparar_lenovo.sh
# =====================================================================
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo: sudo bash ia/reparar_lenovo.sh"; exit 1; }
verde(){ echo -e "\e[1;32m$*\e[0m"; }
azul(){ echo -e "\n\e[1;34m▶ $*\e[0m"; }
rojo(){ echo -e "\e[1;31m$*\e[0m"; }

azul "1/4 Límites de Ollama"
mkdir -p /etc/systemd/system/ollama.service.d
tee /etc/systemd/system/ollama.service.d/centinela.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=10m"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
EOF
systemctl daemon-reload
systemctl restart ollama
for i in $(seq 1 30); do curl -sf localhost:11434/api/tags >/dev/null && break; sleep 1; done
verde "   Ollama: 1 petición a la vez, 10 min en memoria"
ufw status | grep 11434 || echo "   (ufw sin reglas para 11434: corre bash ia/instalar_ollama.sh qwen2.5:3b)"

azul "2/4 Tailscale Funnel (solo /webhook y /webhook-test)"
# Para que en el futuro no haga falta sudo con 'tailscale funnel/serve'
[[ -n "${SUDO_USER:-}" ]] && tailscale set --operator="$SUDO_USER" || true
PUERTO="$(docker port centinela-n8n 5678/tcp 2>/dev/null | head -1 | sed 's/.*://')"
[[ -n "$PUERTO" ]] || { rojo "No encuentro el contenedor centinela-n8n. Corre: bash ia/instalar_n8n.sh"; exit 1; }
echo "   n8n de Centinela en el puerto $PUERTO"
tailscale funnel reset || true
tailscale funnel --bg --set-path /webhook "http://127.0.0.1:$PUERTO/webhook"
tailscale funnel --bg --set-path /webhook-test "http://127.0.0.1:$PUERTO/webhook-test"

DNS="$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
azul "3/4 Esperando a que $DNS exista en Internet (hasta 5 min)"
OK=0
for i in $(seq 1 60); do
  if curl -s -m 5 -H 'accept: application/dns-json' "https://cloudflare-dns.com/dns-query?name=$DNS&type=A" | grep -q '"Answer"'; then OK=1; break; fi
  sleep 5
done
if [[ $OK = 1 ]]; then verde "   $DNS ya es público"; else
  rojo "   $DNS todavía NO es público."
  echo "   Revisa en https://login.tailscale.com/admin/machines que centinela-ia tenga la etiqueta 'Funnel'"
  echo "   y en Access controls que exista: \"nodeAttrs\": [{\"target\": [\"autogroup:member\"], \"attr\": [\"funnel\"]}]"
fi

azul "4/4 Reiniciando n8n (vuelve a registrar el webhook de Telegram)"
docker restart centinela-n8n >/dev/null
for i in $(seq 1 60); do curl -sf "localhost:$PUERTO/healthz" >/dev/null && break; sleep 2; done
sleep 5
tailscale funnel status
verde "\n============================================================"
verde "  Listo. Escríbele /start al bot en Telegram."
verde "============================================================"
