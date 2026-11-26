# Estado actual de CENTINELA

> Tablero vivo. **Se actualiza al final de cada sesión** (en cualquiera de los dos equipos) con commit y push.
> Última actualización: **2026‑11‑26** (noche) · rama: `feat/apartados-por-rol` · **expo: martes 2026‑12‑01** → [`18_EXPO.md`](18_EXPO.md)

## Hecho ✅
| Qué | Cuándo | Responsable |
|---|---|---|
| Arquitectura JE en Cloud Run + Cloud SQL + IAM (cuentas de servicio por función) | 2026‑11‑18 | JE |
| Latido por Cloud Scheduler con OIDC | 2026‑11‑18 | JE |
| Gateway apuntando a Cloud Run; failover por IAM (`nube/08_failover.sh`) | 2026‑11‑18 | JE |
| Auditoría bloque 1 (privacidad, PWA, accesibilidad, multipart 0.0.32) desplegada | 2026‑11‑17 | JE |
| Auditoría bloque 2 en JE y gateway: `GATEWAY_SECRET` + `BOT_SECRET` (H1, M1) | 2026‑11‑17 | JE |
| Auditoría de la migración (C1‑C5): Tailscale 1.104.7, puerta única, llave TS fuera del proceso, OIDC con caché, requests 2.33.0 | 2026‑11‑20 | JE |
| **JP listo** (2026‑11‑26): v1.8.0, Cloud SQL por el Auth Proxy, huellas de `GATEWAY_SECRET`/`BOT_SECRET`/`LLAMADAS_TOKEN` iguales a JE, acceso directo → 403, `/gateway/estado` con JE y JP en línea y `db:true`. Causa del `db:false` inicial: hora de la VM sin sincronizar (`tls: bad certificate`), anotado en doc 12. Failover ya probado | 2026‑11‑26 | JP + JE |
| Precio de Gemini en JE (`VERTEX_PRECIO_*` 0,75/3,75 USD por M tokens, revisión `centinela-je-00011`, PR #9) | 2026‑11‑26 | JE |
| Fase 0: diagnóstico del repo | 2026‑11‑25 | JE |
| **Fases 3 y 4 activadas en la nube** (2026‑11‑26): Vertex AI habilitado + `roles/aiplatform.user` para `centinela-run`, prueba de `gemini-3.8-flash` en `global` ✅; dataset `centinela_analitica` + IAM mínima; **JE v1.8.0** (revisión `centinela-je-00010`) con `vertex:true` y exportación encendida; trabajo `centinela-exportar` (01:15 diario) y primera exportación `200 OK` (8 tablas con datos); 10 vistas creadas y consultadas | 2026‑11‑26 | JE |
| **Fase 5 · Pulir y vender** (PR #7, merge y gateway desplegado 2026‑11‑26): auditoría final (0 secretos, 0 vulnerabilidades altas), web móvil corregida (menú visible a 360‑390 px), README como producto, pitch y guion por rol, doc 12 al día | 2026‑11‑26 | JE |
| **Fase 4 · Analítica** (PR #6, merge 2026‑11‑26): exportación a BigQuery, 8 tablas, 10 vistas, guía de Looker; pendiente de activar | 2026‑11‑26 | JE |
| Guía de la expo [`18_EXPO.md`](18_EXPO.md) (PR #10, merge) | 2026‑11‑26 | JE |

## En curso 🔄
| Qué | Rama / PR | Responsable |
|---|---|---|
| **Apartados por rol en la web pública:** `/arquitectura` (JE), `/seguridad` (JP), `/empresas` (JM), con índice, estado en vivo, diagrama, STRIDE/OWASP, planes y piloto; portada enlazada. Falta: revisión visual de Juan y `wrangler deploy` con su ok | `feat/apartados-por-rol` | JE (+ JP y JM revisan su página) |

## Pendiente ⏳
| # | Qué | Origen | Responsable | Bloquea |
|---|---|---|---|---|
| 1 | **Panel de Looker Studio** (`17_LOOKER_STUDIO.md` §5) + enlace de solo lectura | Fase 4 | JE | Expo |
| 2 | **Verificación final en el PC de mesa**: `auditar .`, Lighthouse, Observatory (`18_EXPO.md` §4); hallazgos a doc 14 | Fase 5 | JE | Expo |
| 3 | Cabecera `Permissions-Policy` en la web (aviso menor de los analizadores) | 2026‑11‑26 | JE | — |
| 4 | Borrar el lead de prueba #1; correo de JP para `09_lectura_jp.sh` (opcional) | Fase 2 | JE | — |
| 5 | C6: ACL de Tailscale con `tag:centinela-run` + llave con tag + `TS_TAGS=… nube/05_desplegar.sh` | doc 15 §2.6 | JE | — |
| 6 | B3: quitar el token por URL en `/api/llamada`; B5: Rate Limiting de Cloudflare para `/api/chat` y `/api/leads` | doc 14 | JP | — |
| 7 | B4: revisar correo noreply en el Lenovo; `chat_id` como variable en n8n | doc 14 | JE | — |
| 8 | API con llave por empresa — solo cuando haya un piloto | `JM_VENTAS.md` §6 | JE | — |
| 9 | **Cierre del curso:** revocar token del bot, llave JSON de `centinela-jp`, llave de Tailscale, roles de lectura de JP; cerrar proyecto GCP | doc 00 §7 | JE | Diciembre |

## ▶️ Próxima sesión (empezar aquí)
**Todo el sistema está en producción y JP está listo.** Falta para la expo del martes 2026‑12‑01 ([`18_EXPO.md`](18_EXPO.md)):
1. **Apartados por rol:** revisar `/arquitectura`, `/seguridad` y `/empresas` en local (`cd gateway && npx wrangler dev`), merge del PR y `npx wrangler deploy` con el ok de Juan. JP y JM revisan el texto de su página.
2. **PC de mesa:** verificación final (`18_EXPO.md` §4: `auditar .`, Lighthouse, Observatory) y anotar resultados en doc 14 (incluye la cabecera `Permissions-Policy`).
3. **Looker Studio** (`17_LOOKER_STUDIO.md` §5) y su enlace de solo lectura en README y doc 13.

## Notas de la última sesión
- Sesión 2026‑11‑26 noche (PC de mesa): apartados profesionales por rol en la web (páginas estáticas servidas por el mismo Worker, misma CSP, sin dependencias nuevas): `web/arquitectura.html`, `web/seguridad.html`, `web/empresas.html`, `web/paginas.css`, `web/paginas.js`. La página de seguridad es pública: describe controles sin detalles explotables.
- Sesión 2026‑11‑26 tarde: JP conectado y verificado (v1.8.0, Cloud SQL, secretos, 403 directo). Guía de la expo en `18_EXPO.md`. Doc 08 marcado como histórico. JP confirmó la hora sincronizada. Sin ensayo formal (decisión de Juan).
- Sesión 2026‑11‑26 (PC de mesa): merge de las Fases 4 y 5; gateway con la web corregida para celular; Vertex y BigQuery activados. En producción: JE v1.8.0 con IA híbrida y exportación diaria a BigQuery.
- Sesión 2026‑11‑25 (PC de mesa): Fases 0‑3 cerradas y desplegadas (Vertex aún apagado); Fase 4 en PR #6.
- Producción hoy: JE v1.8.0 (`centinela-je-00011`, Vertex + BigQuery + precio de Gemini), JP v1.8.0, gateway con pestañas Resumen/Arquitectura/Seguridad/Ventas/IA, migraciones 004 y 005 aplicadas.
- **Proyecto de Google Cloud:** el de nombre `centinela` (`gcloud projects list`; el ID no se sube al repo). Fuera de Cloud Shell los scripts se corren con `PROYECTO=ID_DEL_PROYECTO bash nube/…`; `config.sh` exporta `CLOUDSDK_CORE_PROJECT` para que ningún `gcloud` caiga en el proyecto por defecto del equipo (en el PC de mesa es otro proyecto).
- Migraciones nuevas: `PROYECTO=ID_DEL_PROYECTO bash nube/10_migracion.sh db/NNN_….sql` (Auth Proxy + psql, clave desde Secret Manager sin imprimirla).
- Permisos de Claude Code para desplegar: `.claude/settings.local.json` (local, no se sube), solo para estos scripts y `npx wrangler deploy`.
- Las métricas de seguridad se cuentan en memoria y se vuelcan en cada latido (nunca una escritura por petición). Si la migración 004 no está aplicada, JE solo registra un aviso en el log y conserva los conteos.
- `/api/interno/*` exige `GATEWAY_SECRET` **y** `CONTROL_TOKEN`; desde afuera del Worker responde 404.
- El aviso de Telegram de un lead nuevo no lleva datos personales (solo empresa, segmento y plan).
- Precios de la landing ($14.900 Pro, desde $790.000 Empresa) son hipótesis de piloto de JM, a validar con entrevistas.
