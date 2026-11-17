# 13 · Pitch de Centinela 🛡️ (JE · JP · JM)

> **En vivo:** https://centinela.juan-gallego-sec.workers.dev
> **Duración:** 8‑10 min · **Quién habla** en cada bloque entre corchetes.

---

## 1. El problema (1 min) — [JE]
- En Colombia contestar un número desconocido es una apuesta:
  - **Falso banco:** "dígame el código que le llegó por SMS".
  - **Wangiri:** llamada perdida desde el extranjero para que la devuelvas y te cobren tarifa premium.
  - **Cobranza, telemarketing y encuestas** que no pediste.
- Cada persona lo sufre sola: lo que sabe una víctima **no le sirve a la siguiente**.

**Frase de apertura:** *"¿A quién le han llamado esta semana de un número que no conocía? Centinela responde justo eso: quién te está llamando y si debes contestar."*

## 2. La solución (1 min) — [JE]
La comunidad reporta y Centinela **avisa antes de contestar**, por tres canales:

| Canal | Qué hace |
|---|---|
| 🌐 **Web** | Consultas un número y ves su riesgo, sus reportes y el tipo de fraude. Chat con la IA. |
| 🤖 **Telegram** | Le escribes el número al bot, reportas con `/reportar` y recibes un resumen cada mañana a las 7:00. |
| 📱 **App Android** | Cuando suena la llamada, el celular avisa solo con una notificación de riesgo y la llamada aparece **en vivo** en la web. |

**Riesgo de 0 a 100** según cuántas **personas distintas** reportan: 1 → 30, 2 → 50, 3 → 65 (alto), 5 → 83. Los prefijos de wangiri (+225, +233, +1 809…) suman +25.
La curva `100·(1 − e^(−0,35·n))` evita que **una sola persona "hunda"** un número.

## 3. Arquitectura (2 min) — [JP]
```
Usuarios (web · Telegram · Android)
        │
   ☁️ Cloudflare Worker  ── gateway con failover + límite por IP + panel admin
        │ 1º               ╲ si JE falla
   🟢 JE principal          🟠 JP respaldo
   (VM Google Cloud)        (VM de JP)
        ╲                  ╱
      🗄️ Supabase PostgreSQL (compartida, con RLS)
        ⋮  Tailscale (red privada)
   🧠 Lenovo: Ollama + n8n + bot de Telegram
```
**Decisiones de ingeniería para defender:**
1. **Servidores sin estado:** todo vive en Supabase, así que cualquiera de los dos atiende cualquier petición.
2. **El failover está en el gateway, no en el DNS:** el DNS tarda minutos en cambiar; el gateway de Cloudflare cambia en la misma petición.
3. **Tailscale Funnel:** HTTPS público gratis y **cero puertos abiertos**. SSH a la VM solo por IAP de Google.
4. **JE en una VM e2‑micro y no en Cloud Run:** necesita un proceso siempre encendido (latidos, sincronización) y Tailscale. Además entra en el nivel gratis.

## 4. Tolerancia a fallos (1 min) — [JP]
| Si se cae… | Qué pasa | El usuario nota |
|---|---|---|
| **JE** | El gateway lo marca caído **30 s** y manda todo a JP. Lo revisa en segundo plano y JE vuelve solo. | Nada (~0,2 s) |
| **Supabase** | Cada nodo guarda en SQLite local (reportes y llamadas) y sincroniza al volver. | Respuestas desde caché |
| **Lenovo (IA)** | El chat responde por reglas; los reportes se clasifican después. | Respuestas más simples |
| **Ataque de tráfico** | Cloudflare lo absorbe; hay límite por IP en el gateway y en cada nodo. | Nada |

Mejora reciente: antes, con JE caído, **cada** petición esperaba 8 s; ahora el gateway recuerda la caída (cortacircuito) y va directo a JP.

## 5. IA local (1 min) — [JM]
- Modelo **"centinela"**: Ollama con **qwen2.5:3b** en el Lenovo. Responde corto y solo sobre llamadas y estafas.
- **Filtro previo en el servidor:** números solos, saludos y temas ajenos (*"¿cuánto es 2+2?"*) se responden **al instante, sin la IA**. Solo las preguntas sobre estafas llegan al modelo, que tarda unos 2‑6 s.
- **Clasifica cada reporte:** falso banco, estafa, extorsión, wangiri, cobranza, telemarketing…
- **Privacidad:** los datos nunca salen a una IA en la nube; no guardamos la IP, solo un hash anónimo.

## 6. Seguridad (1 min) — [JM]
- **Panel admin solo en el borde (Cloudflare):**
  - Contraseña con PBKDF2‑SHA256.
  - Sesión de 20 min firmada con HMAC y atada al navegador.
  - Protección anti‑CSRF.
  - Bloqueo tras 5 intentos por IP.
  - 2FA opcional (Aegis).
- En los nodos, `/admin` da **404**: nadie puede atacar el login entrando directo a JE o JP.
- **RLS** activado en Supabase; `ufw` y `fail2ban` en las VMs; tokens distintos para el celular y para el panel.

## 7. Demo en vivo (3 min)
| # | Qué se muestra | Quién |
|---|---|---|
| 1 | Web: consultar `300 123 4567` y luego reportar uno nuevo con descripción → la IA lo clasifica | JE |
| 2 | Chat: *"me llamaron diciendo que eran de Bancolombia y pidieron mi clave"* y luego *"¿cuánto es 2+2?"* (rechazo al instante) | JM |
| 3 | Telegram: el profesor le escribe un número al bot y luego `/estado` | JM |
| 4 | **Llamada real:** alguien llama al celular con la app → notificación + la llamada aparece en la web | JE |
| 5 | **Failover:** panel `/admin` → *Detener JE* → otra llamada, el chat y el bot siguen funcionando, atendidos por **JP**; llega la alerta a Telegram. Luego *Reactivar JE* | JP |

**Plan B:** si falla el internet del salón, usar el celular con datos como hotspot. Tener grabado el video del failover del día anterior.

## 8. Resultados y cierre (1 min) — [los tres]
- **Failover en ~0,2 s**, sin perder peticiones.
- **Costo:** ~4‑6 USD de los 300 de crédito de Google Cloud; Cloudflare, Supabase, Tailscale y la IA son gratis.
- **RAM:** PC viejo 63 % → 17 % al pasar a consola; la VM de 1 GB queda en ~46 %.
- **Cierre [JE]:** *"Cada reporte protege a la siguiente persona. Centinela convierte una mala experiencia individual en un aviso para todos, y no se cae."* → Preguntas.

---

### Quién hace qué (resumen)
| | Bloques | Qué domina para las preguntas |
|---|---|---|
| **JE** | Problema, solución, riesgo, demo web + llamada, cierre | Idea, puntaje, app Android, VM de Google Cloud |
| **JP** | Arquitectura, tolerancia a fallos, demo de failover | Cloudflare, Tailscale, Supabase, nodo de respaldo |
| **JM** | IA local, seguridad, demo de chat y Telegram | Ollama, n8n, panel admin, privacidad |

### Antes de exponer
- [ ] JP online: `/gateway/estado` debe mostrar JE y JP con `online: true` (ver `docs/12_PRUEBA_CON_JP.md`).
- [ ] Lenovo prendido, conectado a la corriente y con la tapa configurada para no dormirse (paso 8 de `11_LENOVO_IA.md`).
- [ ] La clave nueva del profesor guardada en 1Password.
- [ ] Ensayo completo del failover una vez el día anterior, grabado.
