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
| 1 | Subir `python-multipart` a la versión corregida | H2 | 10 min |
| 2 | `/api/cluster` devuelve solo columnas públicas | B1 | 10 min |
| 3 | Registro de llamadas: público enmascarado, completo solo con token | M2 | 30 min |
| 4 | Token solo por encabezado + comparación en tiempo constante | B3 | 15 min |
| 5 | ~~Panel falla cerrado si falta la clave~~ | B2 | ✅ hecho |
| 6 | Web: textos actualizados (JE en Google Cloud, IA en el Lenovo, link de GitHub) | Web #4 | 20 min |
| 7 | Web: menú en celular con `popover` | Web #1 | 45 min |
| 8 | Web: sala 3D se carga al verla + textura WebP/AVIF + fuera de la precarga del SW | Web #2 | 1 h |
| 9 | Web: accesibilidad fina (`aria-label`, `role="img"`, saltar al contenido, `aria-live` acotado) | Web #5 | 30 min |
| 10 | PWA: íconos 192/512/maskable, `id`, `scope`, `lang` | Web #3 | 30 min |
| | **Total bloque 1** | | **≈ 3,5 h** |

**Bloque 2 · Confianza gateway → nodos** (requiere secretos nuevos coordinados en Worker, JE, JP y n8n; se despliega en orden para no cortar el bot)

| # | Qué | Hallazgo | Esfuerzo |
|---|---|---|---|
| 11 | Secreto compartido gateway→nodo; el nodo solo cree la IP del cliente si llega del gateway | M1 | 1 h |
| 12 | El servidor decide la identidad de quien reporta + límite por número | H1 | 1 h |
| 13 | El endpoint del bot solo acepta peticiones de n8n | H1 | 30 min (+ ajuste en n8n) |
| | **Total bloque 2** | | **≈ 2,5 h** |

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
