#!/bin/sh
# Arranque del contenedor en Cloud Run:
#   1. Si hay llave de Tailscale (secreto TS_AUTHKEY), se une a la red privada en modo userspace
#      EN SEGUNDO PLANO (la API no espera) y abre un proxy HTTP en localhost:1055 que la API usa
#      SOLO para hablar con Ollama.
#   2. Borra la llave del entorno de la API y la arranca en el puerto que pone Cloud Run ($PORT).
# Si Tailscale falla, la API funciona igual y el chatbot responde por reglas (degradación elegante).
set -u
TS_SOCK=/tmp/tailscale/tailscaled.sock

conectar_tailscale() {
  mkdir -p /tmp/tailscale
  tailscaled --tun=userspace-networking --statedir=/tmp/tailscale --socket="$TS_SOCK" \
             --outbound-http-proxy-listen=localhost:1055 >/tmp/tailscale/tailscaled.log 2>&1 &
  i=0; while [ ! -S "$TS_SOCK" ] && [ $i -lt 50 ]; do sleep 0.2; i=$((i+1)); done
  if salida=$(timeout 60 tailscale --socket="$TS_SOCK" up --authkey="$1" \
                --hostname="${TS_HOSTNAME:-centinela-je-run}" 2>&1); then
    echo "Tailscale conectado como $(tailscale --socket="$TS_SOCK" ip -4 2>/dev/null) (proxy http://localhost:1055)"
  else
    echo "Tailscale no conectó: $(echo "$salida" | tail -3 | tr '\n' ' ')"
    echo "Últimas líneas de tailscaled: $(tail -5 /tmp/tailscale/tailscaled.log | tr '\n' ' ')"
  fi
}

if [ -n "${TS_AUTHKEY:-}" ]; then
  conectar_tailscale "$TS_AUTHKEY" &
fi
unset TS_AUTHKEY
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 \
     --limit-concurrency 96 --timeout-keep-alive 5
