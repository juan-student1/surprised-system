#!/bin/sh
# Arranque del contenedor en Cloud Run:
#   1. Si hay llave de Tailscale (secreto TS_AUTHKEY), se une a la red privada en modo userspace
#      y abre un proxy HTTP en localhost:1055 que la API usa SOLO para hablar con Ollama.
#   2. Borra la llave del entorno y arranca la API en el puerto que pone Cloud Run ($PORT).
# Si Tailscale falla, la API arranca igual y el chatbot responde por reglas (degradación elegante).
set -u
if [ -n "${TS_AUTHKEY:-}" ]; then
  mkdir -p /tmp/tailscale
  tailscaled --tun=userspace-networking --statedir=/tmp/tailscale \
             --socket=/tmp/tailscale/tailscaled.sock \
             --outbound-http-proxy-listen=localhost:1055 >/tmp/tailscale/log 2>&1 &
  if timeout 20 tailscale --socket=/tmp/tailscale/tailscaled.sock up \
       --authkey="$TS_AUTHKEY" --hostname="${TS_HOSTNAME:-centinela-je-run}" >/dev/null 2>&1; then
    echo "Tailscale conectado (proxy http://localhost:1055 hacia centinela-ia)"
  else
    echo "Tailscale no conectó: la IA queda por reglas hasta el próximo arranque"
  fi
fi
unset TS_AUTHKEY
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 \
     --limit-concurrency 96 --timeout-keep-alive 5
