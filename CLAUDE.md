# CLAUDE.md · CENTINELA

Guía para cualquier sesión de Claude Code (o persona) que trabaje en este repo. Es la **memoria compartida**
entre los dos equipos de JE (PC de mesa en casa y Lenovo portátil): lo importante vive aquí y en
[`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md), nunca solo en la conversación.

## Contexto
Sistema distribuido y tolerante a fallos que identifica llamadas spam y estafas telefónicas en Colombia con
reportes de la comunidad, puntaje de riesgo e IA local. Proyecto de Ingeniería de Sistemas, semestre 8.

| Integrante | Rol | Responde por |
|---|---|---|
| **JE** (Juan) | Arquitectura | Nube (GCP, Cloudflare), nodo JE, IA en el Lenovo, este repo |
| **JP** | Seguridad | Nodo de respaldo (VM de JP), auditoría, amenazas |
| **JM** | Ventas | Mercado, propuesta de valor, pitch y demo |

**Repo público:** `juan-student1/surprised-system`. **En vivo:** https://centinela.juan-gallego-sec.workers.dev

## Arquitectura actual (2026‑11)
```
Usuarios (web · Telegram · app Android)
   └─► Cloudflare Worker  (gateway/worker.js: failover, límites por IP, web estática, panel /admin)
         ├─► JE · Cloud Run centinela-je (us-east1, 0-1 instancias, SA centinela-run) ─┐
         └─► JP · VM de JP por Tailscale Funnel (respaldo)  ── Cloud SQL Auth Proxy ──┴─► Cloud SQL Postgres 17 (centinela-db)
Cloud Scheduler ──(OIDC, SA centinela-tareas)──► POST /tareas/latido en JE (cada minuto)
JE/JP ──Tailscale──► Lenovo "centinela-ia": Ollama (modelo `centinela`) + n8n (bot de Telegram y avisos)
JE ──(si Ollama no responde, con topes)──► Vertex AI Gemini (docs/16_VERTEX_AI.md)
Secretos: Secret Manager (uno por secreto, permiso secreto por secreto)
```
- **API** (`servidor/app/`): FastAPI, la misma en JE y JP. Capas en `centinela/`: `config` → `utilidades` (dominio puro)
  → `db` (Postgres + SQLite local para el modo degradado) → `ia` (Ollama) → `servicios` → `auth` → `rutas`.
- **Puerta única:** con `GATEWAY_SECRET` el nodo rechaza (403) lo que no venga del Worker, salvo `/`, `/ping`, `/health`,
  `/tareas/latido` (OIDC) y `/api/control` (token).
- **Panel `/admin`:** vive en el **gateway** (`worker.js`), no en el nodo (en el nodo da 404).
- Detalle y decisiones: [`docs/15_CLOUD_RUN_CLOUD_SQL_IAM.md`](docs/15_CLOUD_RUN_CLOUD_SQL_IAM.md). Hallazgos: [`docs/14_AUDITORIA_Y_MEJORAS.md`](docs/14_AUDITORIA_Y_MEJORAS.md).

## Reglas (obligatorias)
1. **Español** en código nuevo, comentarios, docs, commits y mensajes al usuario.
2. **Conventional Commits:** `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`, `refactor:`, `security:` (con alcance opcional, p. ej. `fix(gateway): …`).
3. **Nunca secretos en el repo: es PÚBLICO.** Ni tokens, ni llaves, ni `DATABASE_URL`, ni IPs de Tailscale, ni chat_id,
   ni correos personales, ni el reporte técnico de la auditoría (vive solo en local). Los secretos van en Secret Manager,
   `wrangler secret`, 1Password o `/opt/centinela/.env` (JP). Para comparar secretos entre equipos se usa la **huella**
   (`sha256sum | cut -c1-12`), nunca el valor. CI corre `gitleaks` y `trivy` en cada PR.
4. **Antes de cualquier `gcloud`, `wrangler`, `bq`, `terraform` o similar que cree, cambie o borre recursos o que cueste
   dinero: mostrar el comando exacto, explicar qué hace y cuánto cuesta, y pedir confirmación.** Los comandos de solo
   lectura (`describe`, `list`, `logs`) se pueden correr. Nada de `--quiet` para saltarse preguntas destructivas.
5. **Nunca hacer `gcloud auth login`, `wrangler login`, ni tocar facturación, presupuestos o cuentas por Juan.**
   Si hace falta, se le pide que lo corra él (`! gcloud auth login`).
6. **Privilegio mínimo** en IAM: una cuenta de servicio por función, roles a nivel de recurso cuando se pueda.
7. **Una fase = una rama = un PR.** No se hace merge a `main` sin el "ok" de Juan. No se avanza de fase sin su "ok".
8. **`max-instances=1` en Cloud Run** se mantiene: el modo mantenimiento y los límites viven en memoria.
9. La IA **nunca** corre en bucles automáticos que cuesten dinero (Vertex/Gemini solo a demanda y con tope).

## Flujo de dos equipos
**Al empezar** (en cualquiera de los dos equipos):
```bash
git checkout main && git pull
cat docs/ESTADO_ACTUAL.md        # qué está hecho, en curso y pendiente
```
**Al terminar la sesión:**
1. Actualizar `docs/ESTADO_ACTUAL.md` (fecha, qué se hizo, qué sigue, en qué equipo quedó algo a medias).
2. `git add -A && git commit -m "docs(estado): …" && git push` (en la rama de la fase si hay una abierta).
3. Nada importante queda solo en el equipo local: si es un secreto → 1Password; si es conocimiento → este repo.

## Comandos útiles
```bash
# Entorno de desarrollo (Python 3.12, igual que el Dockerfile)
python3 -m venv .venv && . .venv/bin/activate
pip install -r servidor/app/requirements.txt -r requirements-dev.txt
pytest                         # tests de la API (BD simulada, sin red)
ruff check .                   # lint de Python
shellcheck -S warning $(git ls-files '*.sh')
gitleaks git . && trivy fs --severity HIGH,CRITICAL .
uvicorn --app-dir servidor/app main:app --reload   # API local (sin DATABASE_URL entra en modo degradado)

# Gateway (wrangler va por npx dentro de gateway/)
cd gateway && npx wrangler dev                      # local
# Despliegues (SIEMPRE con confirmación de Juan): nube/05_desplegar.sh (JE), npx wrangler deploy (gateway)
```

## Mapa del repo
| Ruta | Qué es |
|---|---|
| `servidor/app/` | API FastAPI (nodo JE/JP) + `Dockerfile` de Cloud Run + `arranque.sh` (Tailscale userspace) |
| `servidor/*.sh` | Instalar/actualizar el nodo JP, Telegram, panel, Cloud SQL Auth Proxy, `ataques.sh` |
| `gateway/` | Cloudflare Worker (failover, límites, panel admin, sirve `web/`) |
| `web/` | Web pública + PWA |
| `nube/` | Scripts de Cloud Shell en orden (01 IAM … 08 failover, 99 borrar VM) |
| `ia/` | Ollama y n8n del Lenovo; `ia/n8n/*.json` flujos para importar |
| `db/` | Esquema y migraciones de Postgres |
| `android/` | App "Centinela llamadas" |
| `tests/` | pytest de la API |
| `docs/` | Guías numeradas 00‑15 + `ESTADO_ACTUAL.md` + `roles/` |
