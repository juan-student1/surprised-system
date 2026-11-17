# 14 · Auditoría y plan de mejoras

> Fecha: 2026‑11‑17 · Commit auditado: `0de43f3`, re‑revisado sobre `b97a9c3` (cambios del Lenovo: failover rápido, admin reforzado).
> Este documento es **público**: resume hallazgos y el plan, **sin detalles explotables**. El reporte técnico completo (pasos de reproducción y código) vive solo en local, fuera del repo.

## Cómo se hizo
- **Seguridad:** revisión manual de `servidor/app`, `gateway/worker.js`, `web/`, `ia/n8n`, scripts y `db/`; `gitleaks git .` (historial), `auditar .` (gitleaks + semgrep + trivy) y un **verificador independiente** que intentó refutar cada hallazgo principal. Solo lectura de código: no se atacó el sistema desplegado.
- **Web moderna:** skill *modern-web-guidance* (incluido `legacy-scan`) + revisión de accesibilidad, rendimiento, PWA, seguridad del cliente y móvil.

## Resultado en una línea
- Seguridad: **0 críticos, 1 alto, 2 medios, 6 bajos** (1 ya resuelto en `b97a9c3`). La base es sólida (RLS, CSP estricta, sin XSS, SQL parametrizado, panel con PBKDF2 + cookie segura + TOTP, cero puertos públicos en la nube); lo que falta es **confiar menos en lo que manda el cliente** y **no depender solo del gateway**.
- Web: **7/10**. Segura y clara; le faltan menú en celular, PWA instalable y carga diferida de la sala 3D.

## Hallazgos (resumen sin detalles explotables)

| ID | Sev. | Área | Resumen | Estado |
|---|---|---|---|---|
| H1 | Alto | API | La identidad de quien reporta se puede alterar y eso afecta el puntaje de riesgo | Abierto |
| H2 | Bajo (era Alto) | Dependencias | `python-multipart` desactualizado con CVE de denegación de servicio | Mitigado: el panel del nodo quedó apagado y ya no se alcanza; falta subir la versión |
| M1 | Medio | Arquitectura | Los nodos aceptan tráfico directo sin pasar por el gateway y confían en encabezados de IP | Abierto |
| M2 | Medio | Privacidad | El registro de llamadas reales expone más datos de los necesarios al público | Abierto |
| B1 | Bajo | Privacidad | Un endpoint público muestra datos internos de los nodos | Abierto |
| B2 | Bajo | Autenticación | La firma de sesión tenía un valor por defecto si faltaba la clave | ✅ Resuelto en el gateway (`b97a9c3`); en el nodo el panel quedó apagado |
| B3 | Bajo | API | Un token se acepta por URL y se compara sin tiempo constante | Abierto |
| B4 | Bajo | Repo público | Datos personales menores en el repo/historial | Abierto |
| B5 | Bajo | Disponibilidad | Límites de peticiones en memoria; chat costoso hacia la IA (mejorado: el chat responde al instante lo que no es del tema) | Abierto |
| B6 | Bajo | Autenticación | El bloqueo global del login (nuevo) permite que un tercero bloquee temporalmente el panel | Aceptable para la demo; documentar |

Falsos positivos descartados: 2 de semgrep (actividad *launcher* de Android, favicon `data:`), 4 de gitleaks (archivo local excluido) y 1 de `legacy-scan`.

## Plan priorizado

### Antes de la prueba de failover y la sustentación

**Bloque 1 · Arreglos de código sin secretos nuevos** (un deploy del Worker + `actualizar.sh` en JE y JP)

| # | Qué | Hallazgo | Esfuerzo |
|---|---|---|---|
| 1 | Subir `python-multipart` a la versión corregida | H2 | ✅ hecho (0.0.32) |
| 2 | `/api/cluster` devuelve solo columnas públicas | B1 | ✅ hecho |
| 3 | Registro de llamadas: público enmascarado, completo solo con token | M2 | ✅ hecho |
| 4 | Comparación en tiempo constante (el token por URL se mantiene por compatibilidad con MacroDroid/Atajos) | B3 | ✅ hecho (parcial) |
| 5 | ~~Panel falla cerrado si falta la clave~~ | B2 | ✅ hecho |
| 6 | Web: textos actualizados (JE en Google Cloud, IA en el Lenovo, link de GitHub) | Web #4 | ✅ hecho |
| 7 | Web: menú en celular con `popover` | Web #1 | ✅ hecho |
| 8 | Web: sala 3D se carga al verla + textura WebP (1,47 MB → 185 KB) + fuera de la precarga del SW | Web #2 | ✅ hecho |
| 9 | Web: accesibilidad fina (`aria-label`, `role="img"`, saltar al contenido, `aria-live` acotado) | Web #5 | ✅ hecho |
| 10 | PWA: íconos 192/512/maskable, `id`, `scope`, `lang` | Web #3 | ✅ hecho |
| | **Bloque 1** | | **✅ en código (`main`); falta desplegar** |

**Bloque 2 · Confianza gateway → nodos** (requiere secretos nuevos coordinados en Worker, JE, JP y n8n; se despliega en orden para no cortar el bot)

| # | Qué | Hallazgo | Esfuerzo |
|---|---|---|---|
| 11 | Secreto compartido gateway→nodo; el nodo solo cree la IP del cliente si llega del gateway | M1 | ✅ en código |
| 12 | El servidor decide la identidad de quien reporta (el campo del cliente se ignora) | H1 | ✅ en código |
| 13 | El endpoint del bot solo acepta peticiones de n8n | H1 | ✅ en código (+ credencial en n8n) |
| | **Bloque 2** | | **✅ en código; falta desplegar en orden** |

#### Despliegue del bloque 2 (en este orden, no corta nada)
El código es compatible hacia atrás: un nodo **sin** los secretos funciona como antes. Por eso el orden importa:

1. **Generar los dos secretos** (en el Lenovo) y guardarlos en 1Password como `GATEWAY_SECRET` y `BOT_SECRET`:
   ```bash
   openssl rand -hex 32 | wl-copy     # → 1Password: GATEWAY_SECRET
   openssl rand -hex 32 | wl-copy     # → 1Password: BOT_SECRET
   ```
2. **Worker** (Lenovo): `cd gateway && npx wrangler secret put GATEWAY_SECRET` (pegar) → `npx wrangler deploy`.
3. **n8n** (Lenovo): *Credentials → Add credential → Header Auth* · Name `x-centinela-bot` · Value = `BOT_SECRET` · nombre de la credencial `Centinela Bot (x-centinela-bot)`. Reimportar `ia/n8n/centinela_bot.json` (o en el nodo **Preguntar a Centinela**: *Authentication → Generic → Header Auth* → esa credencial) → **Save**.
4. **JE** (Cloud Shell → VM): actualizar y poner los secretos sin que se vean:
   ```bash
   cd ~/surprised-system && sudo bash servidor/actualizar.sh
   poner(){ read -rsp "$1 (no se ve al pegar): " V; echo; sudo sed -i "/^$1=/d" /opt/centinela/.env; printf '%s=%s\n' "$1" "$V" | sudo tee -a /opt/centinela/.env >/dev/null; unset V; }
   poner GATEWAY_SECRET
   poner BOT_SECRET
   clear; sudo systemctl restart centinela
   ```
5. **JP**: lo mismo que JE (ver `12_PRUEBA_CON_JP.md`).

**Comprobar:** la web consulta y reporta normal; el bot responde en Telegram; un POST directo al bot sin la credencial devuelve `401`.

### Después de la sustentación (opcional)
| # | Qué | Origen | Esfuerzo |
|---|---|---|---|
| 14 | Chat como `<dialog popover>` | Web #6 | 1 h |
| 15 | Fuente Archivo alojada en el propio sitio | Web #7 | 30 min |
| 16 | CSS moderno con propósito: `content-visibility`, `text-wrap: balance`, `@container`, `light-dark()`, View Transitions | Web #8 | 2 h |
| 17 | `Permissions-Policy`, `Cross-Origin-Opener-Policy`; estilos inline al CSS | Web #9 | 20 min |
| 18 | Rate Limiting de Cloudflare + cola para la IA | B5 | 1,5 h |
| 19 | Correo *noreply* para commits y `chat_id` como variable en n8n | B4 | 15 min |
| 20 | **Cierre del curso:** revocar el token del bot y rotar tokens (ver `00_PLAN_MAESTRO.md` §7) | — | 15 min |

## Qué le toca a JP
Después de los bloques 1 y 2: `sudo bash servidor/actualizar.sh` en su VM y poner los secretos nuevos del bloque 2 (se le envían por privado, nunca por el repo).

## Para la sustentación
- Mostrar esta tabla como evidencia de **auditoría propia**: herramientas (gitleaks, semgrep, trivy), revisión manual y verificación independiente.
- Explicar el principio aprendido: *"nunca confiar en lo que manda el cliente"* y *"defensa en profundidad: el gateway no es la única barrera"*.
