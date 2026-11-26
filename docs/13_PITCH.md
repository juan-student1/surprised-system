# 13 · Pitch y guion de sustentación de Centinela 🛡️

> **En vivo:** https://centinela.juan-gallego-sec.workers.dev · **Duración:** 12 min + preguntas
> **Quién habla:** **JE** arquitectura · **JP** seguridad · **JM** ventas. Cada bloque dice quién lo explica y qué muestra.
> Actualizado: 2026‑11‑26 (Cloud Run, Cloud SQL, IAM, IA híbrida con Gemini, analítica en BigQuery/Looker).

---

## 0. Apertura (30 s) — [JM]
*"¿A quién le han llamado esta semana de un número que no conocía? ¿Contestaron? Centinela responde justo eso: quién te está llamando y si debes contestar, antes de levantar el teléfono."*

## 1. El problema y el mercado (1,5 min) — [JM]
- En Colombia contestar un número desconocido es una apuesta: **falso banco** (*"dígame el código que le llegó por SMS"*), **wangiri** (llamada perdida internacional para que la devuelvas a tarifa premium), extorsión, cobranza y telemarketing.
- Las denuncias de fraude telefónico ante la Policía subieron **18 % en 2024** (13.600 casos), y el fraude por voz es el que más dinero cuesta a las víctimas. Hay **92,5 millones de líneas móviles** activas (MinTIC, 1T 2025).
- **Cada víctima lo vive sola:** lo que aprende una persona no le sirve a la siguiente, y los bancos y cooperativas se enteran tarde de que los están suplantando.
- **Clientes que pagan:** 172 cooperativas de ahorro y crédito con más de 4,4 millones de asociados, bancos pequeños y fintech, la industria de contact center (~750.000 empleos) y los operadores. Fuentes en [`roles/JM_VENTAS.md`](roles/JM_VENTAS.md).

## 2. La solución (1 min) — [JM]
| Canal | Qué hace |
|---|---|
| 🌐 **Web / PWA** | Consultas un número: riesgo 0‑100, reportes y tipo de fraude. Reportas en 10 s. Chat con IA. |
| 🤖 **Telegram** | Le mandas el número al bot, reportas con `/reportar`, resumen a las 7:00. |
| 📱 **Android** | Al sonar la llamada, notificación de riesgo; la llamada aparece en vivo en la web. |

**Riesgo por personas distintas:** `100·(1 − e^(−0,35·n))` → 1 → 30, 2 → 50, **3 → 65 (alto)**, 5 → 83; +25 para prefijos de wangiri; baja con el tiempo. Una sola persona **no puede hundir** un número. **3 personas en 15 min = alerta de campaña.**

**Modelo de negocio:** Gratis · **Pro** $14.900 COP/mes · **Empresa** desde $790.000 COP/mes (API con llave, alertas contra su marca, reporte mensual). Piloto de un mes sin costo para 3 cooperativas.

## 3. Arquitectura (2,5 min) — [JE]
```
Usuarios (web · Telegram · Android)
        │
   ☁️ Cloudflare Worker ── failover + límites por IP + web + panel /admin
        │ 1º                       ╲ si JE falla (< 1 s)
   🟢 JE · Google Cloud Run         🟠 JP · VM de JP (otra red)
        ╲                          ╱
   🗄️ Cloud SQL Postgres 17 ── solo con identidad IAM (conector obligatorio)
   ⏰ Cloud Scheduler (OIDC) → latido cada minuto · exportación diaria → 📊 BigQuery → Looker Studio
   🧠 IA: Ollama en el Lenovo (Tailscale) → ✨ Gemini en Vertex AI solo de respaldo, con topes
```
**Decisiones para defender** (ADR completos en [`roles/JE_ARQUITECTURA.md`](roles/JE_ARQUITECTURA.md)):
1. **Failover en el gateway, no en el DNS:** el DNS tarda minutos; el Worker cambia de nodo en la misma petición y recuerda la caída 30 s (cortacircuito).
2. **Cloud Run con 0‑1 instancias:** costo ~0 y sin servidor que parchar. Los bucles se reemplazaron por **Cloud Scheduler con OIDC** (Google firma el token, no hay contraseña compartida).
3. **Cloud SQL con conector obligatorio:** una contraseña robada sola no sirve; hace falta identidad de Google. La alta disponibilidad la da el clúster JE/JP, no una réplica cara.
4. **Respaldo heterogéneo:** JP está en otra máquina y otro internet; si cae Google Cloud Run, JP sigue.
5. **IA híbrida:** primero local (gratis y privada); Gemini solo si el Lenovo no responde, con tope de 20 llamadas/hora y 100/día.
6. **Analítica aparte de producción:** Looker no toca la base; JE exporta agregados anónimos a BigQuery una vez al día (costo 0).
7. **Costo total ≈ 11 USD/mes** (casi todo es la base de datos).

**Muestra:** panel `/admin` → pestaña **Arquitectura** (todas las piezas en verde, con su explicación).

## 4. Tolerancia a fallos (1 min) — [JE]
| Si se cae… | Qué pasa | El usuario nota |
|---|---|---|
| **JE** | El gateway lo marca caído 30 s y manda todo a JP; vuelve solo | Nada |
| **Base de datos** | Reportes a SQLite local, consultas desde caché, sincroniza al volver | Respuestas desde caché |
| **Lenovo (IA)** | Responde Gemini con topes; si no hay cupo, reglas | Nada / respuestas simples |
| **Ataque de tráfico** | Cloudflare lo absorbe; límites por IP en el borde y en el nodo | Nada |

## 5. Seguridad (2 min) — [JP]
- **Modelo de amenazas STRIDE** y **OWASP API Top 10** revisados punto por punto ([`roles/JP_SEGURIDAD.md`](roles/JP_SEGURIDAD.md)).
- **Puerta única:** los nodos solo atienden lo que trae el secreto del gateway (403 si alguien entra directo a la URL de Cloud Run).
- **Nunca confiar en el cliente:** quién reporta lo decide el servidor (IP real vía gateway, hash con sal); el bot solo acepta a n8n.
- **Panel solo en el borde:** PBKDF2 + 2FA (Aegis), sesión de 20 min atada al navegador, anti‑CSRF, bloqueo tras 5 intentos. En los nodos `/admin` da 404.
- **IAM con privilegio mínimo:** una cuenta de servicio por función, secretos uno por uno, sin llaves JSON en Cloud Run; JP y el profesor con solo lectura.
- **Privacidad:** números enmascarados en público; leads bajo la Ley 1581; lo que va a Gemini o a BigQuery va agregado y sin números completos.
- **Auditoría propia y continua:** gitleaks + semgrep + trivy en cada PR (CI); revisión final 2026‑11‑26: **0 secretos, 0 vulnerabilidades altas/críticas**, solo 2 falsos positivos conocidos.

**Muestra:** `bash servidor/ataques.sh` (flood → 429, cuerpo gigante → 413, sin token → 401, inyección SQL → nada, saltarse el gateway → 403, spam de leads → 429) y luego el panel → pestaña **Seguridad** con los bloqueos por hora.

## 6. Demo en vivo (3 min)
| # | Qué se muestra | Quién |
|---|---|---|
| 1 | Web en el celular: consultar `300 123 4567`; reportar uno nuevo con descripción → la IA lo clasifica | JM |
| 2 | Chat: *"me llamaron diciendo que eran de Bancolombia y pidieron mi clave"* → respuesta de la IA; luego *"¿cuánto es 2+2?"* → rechazo al instante | JM |
| 3 | Telegram: el profesor le escribe un número al bot y luego `/estado` | JM |
| 4 | **Llamada real:** alguien llama al celular con la app → notificación + la llamada aparece en la web | JE |
| 5 | **Failover:** panel → *Detener JE* → web, chat y bot siguen, atendidos por **JP**; pestaña Arquitectura en rojo/verde; *Reactivar JE* | JE + JP |
| 6 | Panel → **IA** → *Detectar campañas* (análisis profundo a demanda) | JE |
| 7 | **Looker Studio:** portada con KPIs, mapa y tipos de fraude, explicados para no técnicos | JM |
| 8 | Panel → **Ventas**: el lead que entró por "Para empresas" | JM |

**Plan B:** celular con datos como hotspot; video grabado del failover del día anterior; capturas del panel de Looker.

## 7. Cierre (30 s) — [JE]
*"Cada reporte protege a la siguiente persona. Centinela convierte una mala experiencia individual en un aviso para todos, cuesta 11 dólares al mes y no se cae."* → Preguntas.

---

## Quién responde qué en las preguntas
| Tema | Responde | Debe dominar |
|---|---|---|
| Por qué Cloud Run / Cloud SQL / Cloudflare, costos, failover, Scheduler, BigQuery | **JE** | `roles/JE_ARQUITECTURA.md`, `15_CLOUD_RUN_CLOUD_SQL_IAM.md`, `16_VERTEX_AI.md`, `17_LOOKER_STUDIO.md` |
| Ataques, IAM, secretos, privacidad, OWASP, auditoría | **JP** | `roles/JP_SEGURIDAD.md`, `14_AUDITORIA_Y_MEJORAS.md` |
| Mercado, clientes, precios, competencia (Truecaller, filtro del teléfono), demo | **JM** | `roles/JM_VENTAS.md` |
| La IA (qué modelo, por qué local, cuándo Gemini) | **JE** (técnico) · **JM** (valor para el cliente) | `16_VERTEX_AI.md` |

**Preguntas probables y respuesta corta:**
- *¿Y si alguien reporta falsamente a un número legítimo?* → El riesgo exige **personas distintas** (una sola no lo sube a alto), decae con el tiempo y existe la lista de números **verificados** (riesgo 0). [JP]
- *¿Por qué no Truecaller?* → Es genérico y no sirve a cooperativas; nosotros somos locales, explicamos el porqué del riesgo y detectamos campañas en 15 min. [JM]
- *¿Qué pasa si se cae Google Cloud?* → JP está fuera de Cloud Run y sigue atendiendo; la base es lo único compartido y tiene modo degradado. [JE]
- *¿Cuánto cuesta escalar?* → Hoy ~11 USD/mes; el techo es `max-instances=1` por el estado en memoria, que se movería a Memorystore si hubiera clientes (ADR‑011). [JE]
- *¿Los datos personales van a Google o a la IA?* → No: la IA primero es local; a Gemini y a BigQuery solo van datos agregados y números enmascarados. [JP]

## Antes de exponer (checklist)
- [ ] `/gateway/estado` con JE y JP `online: true` (JP con bloque 2 y Cloud SQL, `12_PRUEBA_CON_JP.md`).
- [ ] Lenovo prendido, cargando y sin suspenderse (`11_LENOVO_IA.md` paso 8).
- [ ] Vertex encendido y probado (`16_VERTEX_AI.md` §5) y cupo de Gemini en el panel.
- [ ] Looker Studio con datos del día (`17_LOOKER_STUDIO.md`) y enlace de solo lectura listo.
- [ ] Ensayo completo del failover el día anterior, grabado.
- [ ] JM confirmó la fuente de cada cifra que va a decir.
