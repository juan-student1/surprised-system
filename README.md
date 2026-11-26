# CENTINELA 🛡️

Sistema distribuido y tolerante a fallos que identifica llamadas spam y estafas telefónicas con reportes de la comunidad, puntaje de riesgo e IA local.

**Grupo:** JE (Juan, arquitectura) · JP (seguridad) · JM (ventas) — Ingeniería de Sistemas, semestre 8.

```
Usuarios → Cloudflare Worker (failover) → JE principal (Cloud Run) ─────┐
                                        ↘ JP respaldo (VM de JP) ──────┴→ Cloud SQL Postgres (Google Cloud)
           Cloud Scheduler (latido OIDC) ┘   IAM: una cuenta de servicio por función
                         Tailscale ↔ Lenovo de Juan: Ollama + n8n + Telegram
```

## Empieza aquí
1. [`docs/00_PLAN_MAESTRO.md`](docs/00_PLAN_MAESTRO.md) — arquitectura, decisiones, fases
2. **[`docs/15_CLOUD_RUN_CLOUD_SQL_IAM.md`](docs/15_CLOUD_RUN_CLOUD_SQL_IAM.md) — JE en Cloud Run, BD en Cloud SQL, IAM (arquitectura actual)**
3. [`docs/04_NUBE.md`](docs/04_NUBE.md) — GitHub, Cloudflare (y Supabase, ya reemplazado)
4. [`docs/01_JE_SERVIDOR_PRINCIPAL.md`](docs/01_JE_SERVIDOR_PRINCIPAL.md) — histórico: JE en VM e2‑micro
4. [`docs/02_JP_SERVIDOR_RESPALDO.md`](docs/02_JP_SERVIDOR_RESPALDO.md)
5. [`docs/03_PC_PERSONAL_IA.md`](docs/03_PC_PERSONAL_IA.md) → ahora [`docs/11_LENOVO_IA.md`](docs/11_LENOVO_IA.md)
6. [`docs/05_PRUEBAS.md`](docs/05_PRUEBAS.md) — protocolo de pruebas y auditoría
7. [`docs/06_TELEGRAM_N8N.md`](docs/06_TELEGRAM_N8N.md) — bot de Telegram y automatizaciones n8n
8. [`docs/07_LLAMADAS_REALES.md`](docs/07_LLAMADAS_REALES.md) — detectar llamadas reales (Android / iPhone)
9. [`docs/08_CHECKLIST_FINAL.md`](docs/08_CHECKLIST_FINAL.md) — integrar a JP y guion de sustentación
10. [`docs/11_LENOVO_IA.md`](docs/11_LENOVO_IA.md) — IA en el Lenovo: Ollama + n8n + bot (paso a paso)
11. [`docs/12_PRUEBA_CON_JP.md`](docs/12_PRUEBA_CON_JP.md) — lo que falta con JP + prueba de failover
12. [`docs/14_AUDITORIA_Y_MEJORAS.md`](docs/14_AUDITORIA_Y_MEJORAS.md) — auditoría de seguridad, nota de la web y plan de mejoras
13. [`docs/ESTADO_ACTUAL.md`](docs/ESTADO_ACTUAL.md) — **tablero: hecho / en curso / pendiente**
14. Roles: [`JE · Arquitectura`](docs/roles/JE_ARQUITECTURA.md) · [`JP · Seguridad`](docs/roles/JP_SEGURIDAD.md) · [`JM · Ventas`](docs/roles/JM_VENTAS.md)

**En vivo:** https://centinela.juan-gallego-sec.workers.dev

## Estructura
```
db/schema.sql              Esquema PostgreSQL
servidor/app/              API FastAPI del nodo (igual en JE y JP)
servidor/app/Dockerfile    Imagen de JE para Cloud Run (API + Tailscale userspace)
servidor/instalar_nodo.sh  Debian/Mint/Arch → servidor (JP)
servidor/conectar_cloudsql.sh  JP → Cloud SQL por Auth Proxy (cuenta centinela-jp)
nube/                      Scripts de Cloud Shell: IAM, Cloud SQL, secretos, migración, Cloud Run, Scheduler
servidor/actualizar.sh     Actualizar la API desde GitHub
servidor/configurar_telegram.sh  Token del bot, chat_id y clave del celular
gateway/                   Cloudflare Worker con failover
ia/                        Ollama y n8n en el PC personal
web/                       Web responsive (se publica con el gateway)
ia/n8n/                    Flujos de n8n para importar (bot + avisos)
db/002_llamadas.sql        Migración: llamadas reales
db/003_cloudsql.sql        Migración: ajustes para Cloud SQL (RLS, permisos de centinela_jp)
db/004_leads_y_seguridad.sql  Migración: leads de empresas y métricas de seguridad por hora
tests/                     Tests de la API (pytest) · CI en .github/workflows/ci.yml
docs/                      Guías paso a paso
```

*Toda la gloria a Dios.*
