# JP · Seguridad de Centinela

> Responsable: **JP**. Interfaz: pestaña **Seguridad** del panel (`/admin/seguridad`): peticiones bloqueadas (401/403/429) por hora, rutas más atacadas, eventos y último escaneo del CI.
> Página pública del rol: **Seguridad** (https://centinela.juan-gallego-sec.workers.dev/seguridad), versión para clientes y jurado de este documento (sin detalles internos ni explotables).
> Este documento es **público**: describe riesgos y controles **sin detalles explotables**. Última revisión: 2026‑11‑25.

## 1. Modelo de amenazas (STRIDE)

Activos que protegemos: **(1)** la integridad del puntaje de riesgo (que nadie "hunda" o "limpie" un número), **(2)** la disponibilidad del servicio, **(3)** los datos personales (llamadas reales, leads de empresas), **(4)** los secretos e identidades de la nube.

Fronteras de confianza: Internet ↔ Worker · Worker ↔ nodos (JE/JP) · nodos ↔ Cloud SQL · nodos ↔ Lenovo (Tailscale) · n8n ↔ API · Scheduler ↔ JE.

| Amenaza | Dónde | Ejemplo | Controles | Estado |
|---|---|---|---|---|
| **S**uplantación | Reportes | Alguien se hace pasar por muchas personas para subir el riesgo de un número | El servidor decide quién reporta (IP real del Worker, hash con sal); la curva de riesgo necesita personas **distintas**; límite de 10 reportes / 10 min por IP | ✅ JE · ⏳ JP |
| | Bot de Telegram | Mandar al endpoint del bot un `chat_id` ajeno | `/api/bot` solo con `BOT_SECRET` (solo n8n lo tiene) | ✅ JE · ⏳ JP |
| | Latido | Falsificar a Cloud Scheduler | Token OIDC firmado por Google: firma + audiencia + correo exacto | ✅ |
| | Panel | Robo de sesión | Cookie `__Host-`, HttpOnly, SameSite=Strict, 20 min, atada al navegador; TOTP | ✅ |
| **T**ampering (alteración) | Tráfico | Saltarse el Worker para inventar la IP | Puerta única con `GATEWAY_SECRET`; encabezados de IP del cliente se borran en el Worker | ✅ JE · ⏳ JP |
| | Base de datos | Inyección SQL | Solo consultas parametrizadas, sin SQL dinámico; `centinela_jp` sin permisos de esquema | ✅ |
| | Código | Dependencia comprometida | CI con trivy y gitleaks; acciones fijadas por SHA; versiones fijas en `requirements.txt` | ✅ |
| **R**epudio | Panel y nodos | "Yo no detuve JE" | Tabla `eventos` (mantenimiento, reactivado, login_fallido, campañas) + logs de Cloud Run | ✅ (sin usuario por acción: un solo admin) |
| **I**nformation disclosure | Web pública | Ver números de llamadas reales o datos de nodos | Números enmascarados al público; `/api/cluster` solo columnas públicas; leads solo en el panel | ✅ |
| | Repo público | Secretos o datos personales en el historial | gitleaks en cada PR; correo noreply; secretos solo en Secret Manager / 1Password | ✅ secretos · ⏳ B4 (historial) |
| | Red privada | Si alguien ejecuta código en JE, ver toda la tailnet | ACL de Tailscale con `tag:centinela-run` limitado a `centinela-ia:11434` (C6) | ⏳ |
| **D**enial of service | Worker y nodos | Inundar la API o el chat (la IA es cara) | Cloudflare absorbe volumétrico; límites por IP en el Worker (200/min API, 20/min chat) y en el nodo (150/min); cuerpo máx. 4 KB; chat fuera de tema sin IA | ✅ · ⏳ B5 (límites globales) |
| | Panel | Bloquear el login de todos | Bloqueo global tras 20 fallos (aceptado: B6) | Aceptado |
| | Leads | Llenar la BD con spam | Trampa para bots + 3 por hora por IP + autorización obligatoria | ✅ |
| **E**levation of privilege | IAM | Una cuenta con más permisos de los necesarios | Una cuenta de servicio por función; secretos uno por uno; sin la cuenta por defecto de Compute; JP y el profesor solo lectura | ✅ |
| | Contenedor | Escapar como root | Usuario `centinela` (uid 10001), imagen slim, Tailscale 1.104.7 | ✅ |

## 2. Hallazgos abiertos de la auditoría (doc 14 y doc 15) y cómo cerrarlos

| ID | Resumen | Estado real | Qué falta | Quién |
|---|---|---|---|---|
| H1 | Identidad del reportero alterable | ✅ En JE, JP y gateway (JP desde 2026‑11‑26) | — | — |
| M1 | Nodos aceptaban tráfico directo | ✅ En JE y JP (acceso directo → 403) | — | — |
| M2, B1, B2, H2 | Privacidad de llamadas, `/api/cluster`, firma de sesión, multipart | ✅ Cerrados | — | — |
| B3 | Token de llamadas aceptado por URL | Parcial: tiempo constante ✅; la URL sigue por MacroDroid/Atajos | Pasar MacroDroid/Atajos a encabezado `x-centinela-token` y quitar `?token=` | JP |
| B4 | Datos personales menores en el historial | Commits nuevos con correo noreply ✅ | Revisar el correo en el Lenovo; `chat_id` como variable en n8n. No se reescribe el historial (riesgo bajo, rompería los clones) | JE |
| B5 | Límites en memoria; chat costoso | Mejorado (chat fuera de tema sin IA) | Regla de Rate Limiting de Cloudflare (gratis: 1 regla) para `/api/chat` y `/api/leads` | JP (+ JE confirma en Cloudflare) |
| B6 | Bloqueo global del login | Aceptado | Documentado | — |
| C6 | JE entra a Tailscale con identidad de usuario | Abierto | ACL con tag (doc 15 §2.6) | JE |

**Para cerrar H1/M1 en JP** (en la VM de JP, sin que los secretos se vean; los valores se pasan por privado, nunca por el repo):
```bash
cd ~/surprised-system && git pull && sudo bash servidor/actualizar.sh
# bloque `poner` de docs/14 → GATEWAY_SECRET, BOT_SECRET, LLAMADAS_TOKEN (los de JE)
for k in LLAMADAS_TOKEN GATEWAY_SECRET BOT_SECRET; do printf '%s ' $k; sudo grep "^$k=" /opt/centinela/.env | sha256sum | cut -c1-12; done
```
Las huellas deben coincidir con las de JE (las da `nube/03_secretos.sh`).

## 3. Guion de ataques controlados (`servidor/ataques.sh`)

Solo contra **nuestro** servicio. `bash servidor/ataques.sh [URL_DEL_GATEWAY] [URL_DIRECTA_DE_UN_NODO]`

| # | Ataque | Qué se espera | Qué demuestra |
|---|---|---|---|
| 1 | Cuerpo de 20 KB | `413` | El Worker corta payloads grandes |
| 2 | Registrar llamada sin token | `401` | Endpoints sensibles autenticados |
| 3 | Inyección SQL en el número | `422` y la BD intacta | Validación + consultas parametrizadas |
| 4 | Fuerza bruta al panel (como navegador: `Sec-Fetch-Site`) | `401` × 5 y luego `429` | Bloqueo de login (¡te bloquea a ti 15 min!) |
| 5 | Cabeceras de seguridad | 6 o más | CSP, HSTS, X‑Frame‑Options, nosniff, Referrer‑Policy, Permissions‑Policy |
| 6 | Entrar directo al nodo saltándose el Worker | `403` | Puerta única (M1) |
| 7 | Rutas internas del panel desde afuera | `404` | `/api/interno/*` y `/api/control` no existen fuera del Worker |
| 8 | Spam al formulario de empresas (con la trampa llena) | `200` × 3 y luego `429`; nada se guarda | Anti‑spam de leads |
| 9 | 250 peticiones en paralelo (va **al final**: agota el límite por IP ~1 min) | Muchas `429`, el servicio sigue en pie | Límites por IP (borde + nodo) |

Después de correrlo: panel → **Seguridad** → los 401/403/429 aparecen en la hora actual (se vuelcan en el siguiente latido, ≤ 1 min).

## 4. Checklist OWASP API Security Top 10 (2023)

| # | Riesgo | Estado | Evidencia |
|---|---|---|---|
| API1 | Autorización a nivel de objeto (BOLA) | ✅ | No hay objetos por usuario; lo sensible (llamadas completas, leads) exige token |
| API2 | Autenticación rota | ✅ | PBKDF2 + TOTP + bloqueo; tokens en encabezado con comparación en tiempo constante; OIDC en el latido · ⏳ B3 |
| API3 | Autorización a nivel de propiedad | ✅ | `reportero_id` del cliente se ignora; `/api/cluster` sin IPs ni hostnames; público enmascarado |
| API4 | Consumo de recursos sin límite | ✅ / ⏳ | Límites por IP, `max_length` en todos los campos, cuerpo 4 KB, `limite` acotado, IA solo para temas válidos · ⏳ B5 |
| API5 | Autorización a nivel de función | ✅ | `/api/control`, `/api/bot`, `/api/interno/*`, `/tareas/latido` con credencial propia; panel solo en el borde |
| API6 | Acceso sin límite a flujos de negocio sensibles | ✅ | Reportes: 10 / 10 min por IP y riesgo por personas distintas; leads: 3 / hora + trampa |
| API7 | SSRF | ✅ | La API no pide URLs que mande el usuario; destinos fijos (Ollama, Telegram, GitHub) |
| API8 | Configuración insegura | ✅ / ⏳ | CSP estricta, HSTS, sin root, Cloud SQL sin IP pública · ⏳ `CORS_ORIGINS=*` en JE (mitigado por la puerta única) · ⏳ C6 |
| API9 | Inventario de API | ✅ | Rutas en `servidor/app/centinela/rutas.py`; `/docs` de FastAPI no se publica (el Worker solo reenvía `/api/*` y `/health`, y el nodo directo responde 403); probado en `tests/` |
| API10 | Consumo inseguro de APIs | ✅ | Respuestas de Ollama validadas (categoría en lista cerrada, resumen truncado); timeouts en todas las llamadas salientes |

## 5. Acceso de JP a Google Cloud (solo lectura)

JP necesita ver logs, el estado de Cloud Run/Cloud SQL/Scheduler y la política de IAM, **sin poder cambiar nada**. Script: `nube/09_lectura_jp.sh` (lo corre JE en Cloud Shell, con confirmación):

| Rol | Para qué |
|---|---|
| `roles/logging.viewer` | Leer logs de JE (401/403/429, errores) |
| `roles/run.viewer` | Ver revisiones y configuración de Cloud Run |
| `roles/cloudsql.viewer` | Ver la instancia (no los datos) |
| `roles/cloudscheduler.viewer` | Ver el latido |
| `roles/iam.securityReviewer` | Leer las políticas de IAM para auditarlas |
| `roles/secretmanager.viewer` | Ver **qué** secretos existen y sus versiones (nunca el valor) |

## 6. Rutina de JP
- **Cada PR:** el CI corre gitleaks + trivy + tests; no se hace merge en rojo.
- **Cada semana:** revisar la pestaña Seguridad; correr `ataques.sh` antes de una demo.
- **Al cierre del curso:** revocar token del bot, llave JSON de `centinela-jp`, llave de Tailscale y roles de lectura (`nube/09_lectura_jp.sh quitar`).
