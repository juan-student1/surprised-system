# =====================================================================
#  CENTINELA · Imagen del nodo JE para Cloud Run
#  La misma API de siempre + Tailscale en modo userspace (sin /dev/net/tun),
#  que solo sirve para que la API llegue a la IA del Lenovo (centinela-ia).
# =====================================================================
FROM docker.io/tailscale/tailscale:v1.76.6 AS tailscale

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080
WORKDIR /app

# Binarios estáticos de Tailscale (método oficial de Tailscale para Cloud Run)
COPY --from=tailscale /usr/local/bin/tailscaled /usr/local/bin/tailscaled
COPY --from=tailscale /usr/local/bin/tailscale  /usr/local/bin/tailscale

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py arranque.sh ./
COPY centinela ./centinela

# Nunca como root: el usuario del contenedor no puede tocar nada fuera de /app y /tmp
RUN useradd --system --uid 10001 --home /tmp centinela \
    && chmod -R a+rX,go-w /app && chmod 755 arranque.sh
USER centinela

EXPOSE 8080
CMD ["./arranque.sh"]
