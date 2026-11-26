# Estado actual de CENTINELA

> Tablero vivo. **Se actualiza al final de cada sesión** (en cualquiera de los dos equipos) con commit y push.
> Última actualización: **2026‑11‑25** · equipo: PC de mesa · rama: `feat/roles` (Fase 2)

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

## En curso 🔄
| Qué | Rama / PR | Responsable |
|---|---|---|
| **Fase 2 · Roles e interfaces** (código listo, **sin desplegar**): docs `roles/JE_ARQUITECTURA.md`, `roles/JP_SEGURIDAD.md`, `roles/JM_VENTAS.md`; web "Para empresas" + formulario de leads; panel con pestañas Arquitectura / Seguridad / Ventas; API v1.6.0 (`/api/leads`, `/api/interno/*`, métricas 401/403/429 por hora); migración `db/004`; `nube/09_lectura_jp.sh`; `ataques.sh` con 3 pruebas nuevas; 86 tests | `feat/roles` | JE (+ JP y JM revisan su doc) |

### Para desplegar la Fase 2 (en este orden, cada paso con "ok" de Juan)
1. **Migración** (Cloud SQL Studio, usuario `centinela_app`, base `centinela`): pegar `db/004_leads_y_seguridad.sql` → Run. Sin costo.
2. **JE** (Cloud Shell): `cd ~/surprised-system && git pull && bash nube/05_desplegar.sh` → nueva revisión v1.6.0. Sin costo adicional (nivel gratis).
3. **Gateway** (PC): `cd gateway && npx wrangler deploy`. Requiere `CONTROL_TOKEN` en el Worker (ya existe: lo usa el botón "Detener JE"). Sin costo.
4. **JP** (cuando haga lo del bloque 2): `sudo bash servidor/actualizar.sh` (la misma BD, no necesita migración).
5. **Rol de lectura de JP** (Cloud Shell, correo de JP por privado): `CORREO_JP=… bash nube/09_lectura_jp.sh`. Sin costo.
6. **Comprobar:** web → "Para empresas" → enviar un lead de prueba → panel → Ventas; panel → Seguridad (correr `bash servidor/ataques.sh` y esperar 1 min); panel → Arquitectura en verde.

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
- Las métricas de seguridad se cuentan en memoria y se vuelcan en cada latido (nunca una escritura por petición). Si la migración 004 no está aplicada, JE solo registra un aviso en el log y conserva los conteos.
- `/api/interno/*` exige `GATEWAY_SECRET` **y** `CONTROL_TOKEN`; desde afuera del Worker responde 404.
- El aviso de Telegram de un lead nuevo no lleva datos personales (solo empresa, segmento y plan).
- Precios de la landing ($14.900 Pro, desde $790.000 Empresa) son hipótesis de piloto de JM, a validar con entrevistas.
