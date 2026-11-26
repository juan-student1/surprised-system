# Estado actual de CENTINELA

> Tablero vivo. **Se actualiza al final de cada sesión** (en cualquiera de los dos equipos) con commit y push.
> Última actualización: **2026‑11‑25** · equipo: PC de mesa · rama: `chore/despliegue-fase2`

## Hecho ✅
| Qué | Cuándo | Responsable |
|---|---|---|
| Arquitectura JE en Cloud Run + Cloud SQL + IAM (cuentas de servicio por función) | 2026‑11‑18 | JE |
| Latido por Cloud Scheduler con OIDC | 2026‑11‑18 | JE |
| Gateway apuntando a Cloud Run; failover por IAM (`nube/08_failover.sh`) | 2026‑11‑18 | JE |
| Auditoría bloque 1 (privacidad, PWA, accesibilidad, multipart 0.0.32) desplegada | 2026‑11‑17 | JE |
| Auditoría bloque 2 en JE y gateway: `GATEWAY_SECRET` + `BOT_SECRET` (H1, M1) | 2026‑11‑17 | JE |
| Auditoría de la migración (C1‑C5): Tailscale 1.104.7, puerta única, llave TS fuera del proceso, OIDC con caché, requests 2.33.0 | 2026‑11‑20 | JE |
| Fase 0: diagnóstico del repo | 2026‑11‑25 | JE |
| **Fase 1 · Cimientos** (PR #1, merge): `CLAUDE.md`, este tablero, 72 tests, CI (ruff, pytest, shellcheck, gitleaks, trivy) | 2026‑11‑25 | JE |
| **Fase 2 · Roles e interfaces** (PR #2, merge) **desplegada**: migración `db/004` en Cloud SQL, JE v1.6.0 (revisión `centinela-je-00008`), gateway con pestañas Arquitectura / Seguridad / Ventas y web "Para empresas". Verificado: `/health` 1.6.0, `/api/interno` → 404 desde afuera, JE directo → 403, lead de prueba #1 guardado | 2026‑11‑25 | JE |

## En curso 🔄
| Qué | Rama / PR | Responsable |
|---|---|---|
| Revisar el panel con login: pestañas Arquitectura, Seguridad (los 403 de la verificación aparecen tras el siguiente latido) y Ventas (borrar el lead #1 "PRUEBA despliegue") | — | JE |
| Rol de solo lectura de JP: `PROYECTO=ID_DEL_PROYECTO CORREO_JP=… bash nube/09_lectura_jp.sh` | — | JE (correo de JP por privado) |
| JP actualiza su nodo a v1.6.0 cuando haga el bloque 2 (`sudo bash servidor/actualizar.sh`) | — | JP |

## Pendiente ⏳
| # | Qué | Origen | Responsable | Bloquea |
|---|---|---|---|---|
| 1 | Bloque 2 en JP: `GATEWAY_SECRET`, `BOT_SECRET`, misma `LLAMADAS_TOKEN` (comparar huellas) | doc 14 | JP (+ JE pasa secretos por privado) | Prueba de failover real |
| 2 | JP a Cloud SQL por Auth Proxy (`nube/07_llave_jp.sh` → `servidor/conectar_cloudsql.sh`) | doc 15 §3 | JE + JP | Prueba de failover real |
| 3 | Prueba de failover completa con JP (doc 12 §3) | doc 12 | JE + JP | Sustentación |
| 4 | C6: ACL de Tailscale con `tag:centinela-run` + llave con tag + `TS_TAGS=… nube/05_desplegar.sh` | doc 15 §2.6 | JE (panel de Tailscale) | — |
| 5 | B3: quitar el token por URL en `/api/llamada` cuando MacroDroid/Atajos usen encabezado | doc 14 | JP | — |
| 6 | B5: regla de Rate Limiting de Cloudflare para `/api/chat` y `/api/leads` | doc 14 | JP | — |
| 7 | B4: revisar correo noreply en el Lenovo; `chat_id` como variable en n8n | doc 14 | JE | — |
| 8 | JM: confirmar el enlace exacto del dato "71 % recibió un intento de fraude" (fuente [4] de `JM_VENTAS.md`) | Fase 2 | JM | Sustentación |
| 9 | API con llave por empresa (tabla de llaves con hash, cuota mensual) — solo cuando haya un piloto | `JM_VENTAS.md` §6 | JE | — |
| 10 | Doc 12 todavía explica actualizar JE en la VM (ya no existe) | Fase 0 | JE | — |
| 11 | Fase 3 · Vertex AI (Gemini) como respaldo de Ollama | plan | JE | "ok" de la Fase 2 |
| 12 | Fase 4 · BigQuery + Looker Studio | plan | JE | Fase 3 |
| 13 | Fase 5 · Pulir y vender | plan | todos | Fase 4 |
| 14 | **Cierre del curso:** revocar token del bot, llave JSON de `centinela-jp`, llave de Tailscale, roles de lectura de JP (`nube/09_lectura_jp.sh quitar`); cerrar proyecto GCP | doc 00 §7 | JE | Diciembre |

## Notas de la última sesión
- **Proyecto de Google Cloud:** el de nombre `centinela` (`gcloud projects list`; el ID no se sube al repo). Fuera de Cloud Shell los scripts se corren con `PROYECTO=ID_DEL_PROYECTO bash nube/…`; `config.sh` exporta `CLOUDSDK_CORE_PROJECT` para que ningún `gcloud` caiga en el proyecto por defecto del equipo (en el PC de mesa es otro proyecto).
- Migraciones nuevas: `PROYECTO=ID_DEL_PROYECTO bash nube/10_migracion.sh db/NNN_….sql` (Auth Proxy + psql, clave desde Secret Manager sin imprimirla).
- Permisos de Claude Code para desplegar: `.claude/settings.local.json` (local, no se sube), solo para estos scripts y `npx wrangler deploy`.
- Las métricas de seguridad se cuentan en memoria y se vuelcan en cada latido (nunca una escritura por petición). Si la migración 004 no está aplicada, JE solo registra un aviso en el log y conserva los conteos.
- `/api/interno/*` exige `GATEWAY_SECRET` **y** `CONTROL_TOKEN`; desde afuera del Worker responde 404.
- El aviso de Telegram de un lead nuevo no lleva datos personales (solo empresa, segmento y plan).
- Precios de la landing ($14.900 Pro, desde $790.000 Empresa) son hipótesis de piloto de JM, a validar con entrevistas.
