# Estado actual de CENTINELA

> Tablero vivo. **Se actualiza al final de cada sesión** (en cualquiera de los dos equipos) con commit y push.
> Última actualización: **2026‑11‑26** · equipo: PC de mesa · rama: `main` (las 5 fases mergeadas)

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
| **Fases 3 y 4 activadas en la nube** (2026‑11‑26): Vertex AI habilitado + `roles/aiplatform.user` para `centinela-run`, prueba de `gemini-3.8-flash` en `global` ✅; dataset `centinela_analitica` + IAM mínima; **JE v1.8.0** (revisión `centinela-je-00010`) con `vertex:true` y exportación encendida; trabajo `centinela-exportar` (01:15 diario) y primera exportación `200 OK` (8 tablas con datos); 10 vistas creadas y consultadas | 2026‑11‑26 | JE |
| **Fase 5 · Pulir y vender** (PR #7, merge y gateway desplegado 2026‑11‑26): auditoría final (0 secretos, 0 vulnerabilidades altas), web móvil corregida (menú visible a 360‑390 px), README como producto, pitch y guion por rol, doc 12 al día | 2026‑11‑26 | JE |
| **Fase 4 · Analítica** (PR #6, merge 2026‑11‑26): exportación a BigQuery, 8 tablas, 10 vistas, guía de Looker; pendiente de activar en la nube | 2026‑11‑26 | JE |
| **Fase 1 · Cimientos** (PR #1, merge): `CLAUDE.md`, este tablero, 72 tests, CI (ruff, pytest, shellcheck, gitleaks, trivy) | 2026‑11‑25 | JE |
| **Fase 2 · Roles e interfaces** (PR #2, merge) **desplegada**: migración `db/004` en Cloud SQL, JE v1.6.0 (revisión `centinela-je-00008`), gateway con pestañas Arquitectura / Seguridad / Ventas y web "Para empresas". Verificado: `/health` 1.6.0, `/api/interno` → 404 desde afuera, JE directo → 403, lead de prueba #1 guardado | 2026‑11‑25 | JE |

## En curso 🔄
| Qué | Rama / PR | Responsable |
|---|---|---|
| Fase 4 mergeada (PR #6) **sin activar** en la nube: falta `12_bigquery.sh preparar` → `05_desplegar.sh` → `programar` → `vistas` y el panel de Looker | — | Juan corre los `!` |
| Fase 3: Vertex sigue apagado (falta `11_vertex.sh dar` y `probar`, tras revisar el precio) | — | Juan |
| Borrar el lead de prueba #1; revisar las pestañas del panel con su usuario; correo de JP para `09_lectura_jp.sh` | — | JE |
| JP: bloque 2 + Cloud SQL + actualizar su nodo; prueba de failover real | — | JP |

### Para activar la Fase 4 (en orden, cada paso con "ok" de Juan)
1. `bash nube/12_bigquery.sh preparar` — dataset `centinela_analitica` (us-east1) + `bigquery.dataEditor` solo en el dataset y `bigquery.jobUser` para `centinela-run`.
2. `bash nube/05_desplegar.sh` — JE v1.8.0 con la exportación encendida (y Vertex si ya se activó).
3. `bash nube/12_bigquery.sh programar` — trabajo `centinela-exportar` (01:15 diario) + primera exportación.
4. `bash nube/12_bigquery.sh vistas` — 10 vistas.
5. Looker Studio: seguir `docs/17_LOOKER_STUDIO.md` §5 (lo hace Juan con su cuenta; 30‑45 min).

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

## ▶️ Próxima sesión (empezar aquí)
**Las 5 fases del plan están en `main`.** Lo que falta es operativo:
1. **Looker Studio:** armar el panel con `docs/17_LOOKER_STUDIO.md` §5 (Juan, con su cuenta; 30‑45 min). Opcional: cuando se conozca el precio de Gemini 3.8 Flash, poner `VERTEX_PRECIO_ENTRADA_M` y `VERTEX_PRECIO_SALIDA_M` en JE para que `uso_ia` estime el costo.
2. **JP:** bloque 2 + Cloud SQL + actualizar su nodo → prueba de failover real (`12_PRUEBA_CON_JP.md`).
3. **Ensayo de la sustentación** con `13_PITCH.md` (JE · JP · JM); JM confirma la fuente de cada cifra.
4. Pendientes chicos: borrar el lead de prueba #1, correo de JP para `09_lectura_jp.sh`, C6 (ACL de Tailscale), B3, B5.

## Notas de la última sesión
- Sesión 2026‑11‑26 (PC de mesa): merge de las Fases 4 y 5; gateway con la web corregida para celular; Vertex y BigQuery activados. En producción: JE v1.8.0 con IA híbrida y exportación diaria a BigQuery.
- Sesión 2026‑11‑25 (PC de mesa): Fases 0‑3 cerradas y desplegadas (Vertex aún apagado); Fase 4 en PR #6.
- Producción hoy: JE v1.7.0 (`centinela-je-00009`), gateway con pestañas Resumen/Arquitectura/Seguridad/Ventas/IA, migraciones 004 y 005 aplicadas.
- **Proyecto de Google Cloud:** el de nombre `centinela` (`gcloud projects list`; el ID no se sube al repo). Fuera de Cloud Shell los scripts se corren con `PROYECTO=ID_DEL_PROYECTO bash nube/…`; `config.sh` exporta `CLOUDSDK_CORE_PROJECT` para que ningún `gcloud` caiga en el proyecto por defecto del equipo (en el PC de mesa es otro proyecto).
- Migraciones nuevas: `PROYECTO=ID_DEL_PROYECTO bash nube/10_migracion.sh db/NNN_….sql` (Auth Proxy + psql, clave desde Secret Manager sin imprimirla).
- Permisos de Claude Code para desplegar: `.claude/settings.local.json` (local, no se sube), solo para estos scripts y `npx wrangler deploy`.
- Las métricas de seguridad se cuentan en memoria y se vuelcan en cada latido (nunca una escritura por petición). Si la migración 004 no está aplicada, JE solo registra un aviso en el log y conserva los conteos.
- `/api/interno/*` exige `GATEWAY_SECRET` **y** `CONTROL_TOKEN`; desde afuera del Worker responde 404.
- El aviso de Telegram de un lead nuevo no lleva datos personales (solo empresa, segmento y plan).
- Precios de la landing ($14.900 Pro, desde $790.000 Empresa) son hipótesis de piloto de JM, a validar con entrevistas.
