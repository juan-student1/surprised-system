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
  umask 077; mkdir -p /tmp/tailscale
  # La llave va en un archivo temporal (600) y no en la línea de comandos ni en el entorno de
  # tailscaled: así no se puede leer en /proc/<pid>/cmdline ni /proc/<pid>/environ.
  printf '%s' "$1" > /tmp/tailscale/llave
  env -u TS_AUTHKEY tailscaled --tun=userspace-networking --statedir=/tmp/tailscale --socket="$TS_SOCK" \
             --outbound-http-proxy-listen=localhost:1055 >/tmp/tailscale/tailscaled.log 2>&1 &
  i=0; while [ ! -S "$TS_SOCK" ] && [ $i -lt 50 ]; do sleep 0.2; i=$((i+1)); done
  # TS_TAGS (opcional, ej. tag:centinela-run): con tag, las ACL de Tailscale limitan a JE a la IA y nada más.
  # La llave debe haberse creado con ese mismo tag, si no, Tailscale la rechaza.
  if salida=$(timeout 60 tailscale --socket="$TS_SOCK" up --auth-key="file:/tmp/tailscale/llave" \
                --hostname="${TS_HOSTNAME:-centinela-je-run}" ${TS_TAGS:+--advertise-tags="$TS_TAGS"} 2>&1); then
    rm -f /tmp/tailscale/llave
    echo "Tailscale conectado como $(tailscale --socket="$TS_SOCK" ip -4 2>/dev/null) (proxy http://localhost:1055)"
  else
    rm -f /tmp/tailscale/llave
    echo "Tailscale no conectó: $(echo "$salida" | tail -3 | tr '\n' ' ')"
    echo "Últimas líneas de tailscaled: $(tail -5 /tmp/tailscale/tailscaled.log | tr '\n' ' ')"
  fi
}

if [ -n "${TS_AUTHKEY:-}" ]; then
  LLAVE_TS="$TS_AUTHKEY"; unset TS_AUTHKEY
  conectar_tailscale "$LLAVE_TS" &
  unset LLAVE_TS
fi
unset TS_AUTHKEY
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 \
     --limit-concurrency 96 --timeout-keep-alive 5
