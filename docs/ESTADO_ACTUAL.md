# Estado actual de CENTINELA

> Tablero vivo. **Se actualiza al final de cada sesión** (en cualquiera de los dos equipos) con commit y push.
> Última actualización: **2026‑11‑25** · equipo: PC de mesa · rama: `chore/cimientos` (Fase 1)

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

## En curso 🔄
| Qué | Rama / PR | Responsable |
|---|---|---|
| **Fase 1 · Cimientos:** `CLAUDE.md`, este tablero, 72 tests de la API con pytest, CI (ruff, pytest, shellcheck, gitleaks, trivy fs) | `chore/cimientos` | JE |

## Pendiente ⏳
| # | Qué | Origen | Responsable | Bloquea |
|---|---|---|---|---|
| 1 | Bloque 2 en JP: `GATEWAY_SECRET`, `BOT_SECRET`, misma `LLAMADAS_TOKEN` (comparar huellas) | doc 14 | JP (+ JE pasa secretos por privado) | Prueba de failover real |
| 2 | JP a Cloud SQL por Auth Proxy (`nube/07_llave_jp.sh` → `servidor/conectar_cloudsql.sh`) | doc 15 §3 | JE + JP | Prueba de failover real |
| 3 | Prueba de failover completa con JP (doc 12 §3) | doc 12 | JE + JP | Sustentación |
| 4 | C6: ACL de Tailscale con `tag:centinela-run` + llave con tag + `TS_TAGS=… nube/05_desplegar.sh` | doc 15 §2.6 | JE (panel de Tailscale) | — |
| 5 | B3: quitar el token por URL en `/api/llamada` cuando MacroDroid/Atajos usen encabezado | doc 14 | JP | — |
| 6 | B5: Cloudflare Rate Limiting + cola para la IA | doc 14 | JP | — |
| 7 | B4: correo noreply en commits (ya configurado en el PC de mesa; revisar el Lenovo) y `chat_id` como variable en n8n | doc 14 | JE | — |
| 8 | Actualizar la tabla de hallazgos de la doc 14 (H1/M1 figuran "Abierto" pero están en código) | Fase 0 | JP (Fase 2) | — |
| 9 | Docs desactualizadas: README sin JM, docstrings de `main.py`/`db.py` hablan de Supabase, doc 12 habla de la VM de JE | Fase 0 | JE | — |
| 10 | Fase 2 · Roles (JE arquitectura, JP seguridad, JM ventas) + interfaces | plan | JE/JP/JM | "ok" de la Fase 1 |
| 11 | Fase 3 · Vertex AI (Gemini) como respaldo de Ollama | plan | JE | Fase 2 |
| 12 | Fase 4 · BigQuery + Looker Studio | plan | JE | Fase 3 |
| 13 | Fase 5 · Pulir y vender | plan | todos | Fase 4 |
| 14 | **Cierre del curso:** revocar token del bot, llave JSON de `centinela-jp`, llave de Tailscale; cerrar proyecto GCP | doc 00 §7 | JE | Diciembre |

## Notas de la última sesión
- CI nuevo: acciones fijadas por SHA; gitleaks 8.30.1 y trivy 0.76.1 con checksum verificado.
- Lint: se quitaron 5 imports sin uso y variables de bucle sin uso en los `.sh` (sin cambio de comportamiento).
- `ruff.toml` tolera el estilo compacto del proyecto (varias sentencias por línea).
