# 16 · IA híbrida: Ollama local + Vertex AI Gemini

> Fase 3 · Responsable: **JE**. Código: `servidor/app/centinela/ia.py` (híbrido) y `analisis.py` (análisis profundo).
> Interfaz: pestaña **IA** del panel (`/admin/ia`). Última revisión: 2026‑11‑25.

## 1. Qué hace

| Situación | Quién responde |
|---|---|
| Chat o clasificación de un reporte, con el Lenovo prendido | **Ollama** (modelo `centinela`, local) |
| Igual, pero Ollama no responde o falla | **Gemini** en Vertex AI (si queda cupo) |
| Ninguna de las dos (o sin cupo) | **Reglas** (respuesta inmediata, nunca un error) |
| Botón **Detectar campañas** o **Resumen semanal** del panel | **Gemini** primero (más contexto); si no hay cupo, Ollama |

**Nunca hay bucles automáticos hacia Gemini.** Cada llamada nace de una acción de una persona: un mensaje en el chat o en Telegram, un reporte con descripción o un botón del panel. El latido de Cloud Scheduler **no** llama a Gemini.

## 2. Por qué es híbrida

| Criterio | Ollama (Lenovo) | Vertex AI Gemini | Decisión |
|---|---|---|---|
| **Costo** | 0 (equipo propio) | Se paga por token | Ollama primero; Gemini solo de respaldo y con topes |
| **Privacidad** | Los reportes no salen de nuestra red | Los textos van a Google (sin entrenamiento con datos de clientes, según los términos de Vertex) | Lo sensible se procesa local; al análisis profundo solo llegan datos agregados y descripciones con los números borrados |
| **Disponibilidad** | Depende de que el Lenovo esté prendido y en Tailscale | Servicio administrado de Google | Gemini cubre los apagones del Lenovo (antes el chat bajaba a reglas) |
| **Capacidad** | Modelo pequeño (7B), contexto corto | Modelo grande, contexto largo | El análisis profundo (muchos reportes juntos) va a Gemini |

## 3. Configuración

| Variable (JE) | Valor | Para qué |
|---|---|---|
| `VERTEX_PROYECTO` | el proyecto `centinela` | Sin esta variable Vertex queda **apagado** (así corre JP) |
| `VERTEX_MODELO` | `gemini-3.8-flash` | Gemini Flash GA más reciente (lanzado 2026‑09‑02, retiro no antes de 2027‑09‑02) según *Model versions* de Vertex. Los `gemini-2.5-*` ya se retiraron (2026‑10‑20) |
| `VERTEX_REGION` | `global` | Endpoint global: documentado para `gemini-3.8-flash`. No se pudo confirmar en la documentación que el modelo esté en `us-east1`; si se confirma, basta `VERTEX_REGION=us-east1` al desplegar |
| `VERTEX_MAX_HORA` | 20 | Tope de llamadas a Gemini por hora (por instancia; JE tiene máx. 1) |
| `VERTEX_MAX_DIA` | 100 | Tope por día |
| `VERTEX_MAX_PROFUNDO_DIA` | 10 | Análisis profundos por día |
| `VERTEX_TIMEOUT` | 20 s (60 s en profundo) | Nadie espera más que eso |
| `VERTEX_CACHE_SEG` | 3600 | La misma pregunta se responde de la caché durante 1 h (el análisis profundo, 15 min) |

**Identidad:** JE llama a Vertex con su cuenta de servicio `centinela-run` (credenciales temporales de Cloud Run, **sin llaves JSON**). Rol: `roles/aiplatform.user` (incluye `aiplatform.endpoints.predict`, el permiso de predicción; `roles/aiplatform.viewer` no lo trae). Es el rol predefinido más pequeño que permite llamar al modelo.

## 4. Costo

**Precio de `gemini-3.8-flash`** (consola de Vertex AI, revisado por JE el 2026‑11‑26): **0,75 USD por millón de tokens de entrada** y **3,75 USD por millón de tokens de salida**. JE lo recibe en `VERTEX_PRECIO_ENTRADA_M` / `VERTEX_PRECIO_SALIDA_M` (lo pone `nube/05_desplegar.sh`) y así la tabla `uso_ia` y la vista `v_ia_diaria` muestran el **costo estimado real**.

| Escenario | Llamadas/mes | Tokens aprox. por llamada | Tokens/mes (entrada / salida) | Costo |
|---|---|---|---|---|
| Normal (el Lenovo casi siempre prendido) | ~300 | 1.500 / 400 | 0,45 M / 0,12 M | **≈ 0,80 USD/mes** |
| Peor caso (Lenovo apagado todo el mes y los topes llenos) | 3.000 chat + 300 profundos | 1.500 / 1.000 (chat), 8.000 / 3.000 (profundo) | 6,9 M / 3,9 M | **≈ 20 USD/mes** (5,2 entrada + 14,6 salida) |

El peor caso supera la alerta de presupuesto de 15 USD (doc 15 §6), que **avisaría a tiempo**. Si se quiere un techo más bajo, basta bajar `VERTEX_MAX_DIA` (con 50/día el peor caso queda en ≈ 10 USD/mes) y redesplegar.

## 5. Activar (en orden, con confirmación de Juan)

```bash
bash nube/10_migracion.sh db/005_ia_uso.sql   # tabla ia_uso_hora (uso por hora para el panel y la analítica)
bash nube/11_vertex.sh dar                     # API de Vertex + roles/aiplatform.user para centinela-run
bash nube/11_vertex.sh probar                  # una llamada mínima con tu identidad: confirma modelo y región
bash nube/05_desplegar.sh                      # detecta la API y despliega JE con VERTEX_* (v1.7.0)
cd gateway && npx wrangler deploy              # pestaña IA del panel
```
Fuera de Cloud Shell, anteponer `PROYECTO=<id del proyecto centinela>`.

**Comprobar:** panel → **IA**: Gemini con su modelo y cupo `0/20`. Apagar Ollama en el Lenovo (`sudo systemctl stop ollama`) → preguntar en el chat de la web → la respuesta llega con `"fuente":"vertex"` → el contador sube a `1/20`. Prender Ollama de nuevo.

**Apagar Vertex** (por costo o al cerrar el curso): `bash nube/11_vertex.sh quitar` y `gcloud services disable aiplatform.googleapis.com`, luego `bash nube/05_desplegar.sh`.

## 6. Privacidad de lo que se envía
- **Chat:** el mensaje del usuario y las fichas de los números consultados (que ya son públicos en la web).
- **Clasificación:** el número reportado y la descripción del reporte (solo cuando el Lenovo no responde).
- **Análisis profundo:** conteos, categorías, prefijos y números reportados; descripciones recortadas a 160 caracteres y con **toda secuencia de dígitos reemplazada por `[número]`**. Nunca IPs, hashes de reporteros, leads ni llamadas reales.

## 7. Qué se registra
Tabla `ia_uso_hora` (migración 005): por hora, nodo, proveedor (`ollama`/`vertex`), tipo (`chat`, `clasificar`, `profundo_campanas`, `profundo_semanal`) y resultado (`ok`, `error`, `cache`, `sin_cupo`, `apagado`): llamadas y tokens. Sin textos. Sirve para la pestaña IA y para la analítica de la Fase 4.
