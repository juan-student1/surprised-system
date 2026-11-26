# 12 · Lo que falta para probar con JP (failover completo)

> Todo lo de **nuestro lado** (Lenovo, gateway, JE en Cloud Run, código) ya está hecho. Esto es lo único pendiente:
> 1) conectar JP a Cloud SQL (`nube/07_llave_jp.sh` + `servidor/conectar_cloudsql.sh`, doc 15 §3), 2) dejar JP igual que JE, 3) probar juntos.

## Qué se arregló (2026‑11‑17)
| Problema | Causa | Arreglo |
|---|---|---|
| Con JP atendiendo, la llamada del celular **no aparecía** en la web | `configurar_telegram.sh` generaba una `LLAMADAS_TOKEN` **distinta** en JP si se dejaba vacía → JP respondía 401 al celular | En JP ahora es obligatorio pegar la de JE. Y si Supabase falla, la llamada se guarda en el nodo y la web la ve igual |
| Todo **muy lento** con JE caído | El gateway esperaba hasta 8 s a JE en **cada** petición antes de pasar a JP | Cortacircuito: JE caído se recuerda 30 s y todo va directo a JP (≈0,2 s). Se revisa en segundo plano y vuelve solo |
| Chat lento / respuestas raras | Toda pregunta iba a la IA | Números solos y temas ajenos responden **al instante** sin IA; solo las preguntas de estafas van a la IA |
| Panel con clave `profe2024` | Clave débil y panel también abierto directo en el Funnel de JE | Clave nueva fuerte (1Password), sesión de 20 min atada al navegador, anti‑CSRF, bloqueo compartido, panel **solo** en el gateway (en los nodos da 404) |
| Bot de Telegram mudo | El dominio público del Funnel del Lenovo no existía | `sudo bash ia/reparar_lenovo.sh` en el Lenovo |

## 1 · JE ya está al día (Cloud Run)
Desde el 2026‑11‑18 JE corre en **Cloud Run** y se actualiza con `bash nube/05_desplegar.sh` (ver `15_CLOUD_RUN_CLOUD_SQL_IAM.md`). Comprobar:
```bash
curl -s https://centinela.juan-gallego-sec.workers.dev/health        # "nodo":"JE" y la versión actual
curl -s -o /dev/null -w "%{http_code}\n" https://centinela.juan-gallego-sec.workers.dev/api/interno/leads   # 404: rutas internas cerradas
```

## 2 · Dejar JP igual que JE (lo hace JP)
```bash
cd ~/surprised-system && sudo bash servidor/actualizar.sh
sudo bash servidor/configurar_telegram.sh      # pegar la MISMA LLAMADAS_TOKEN de JE (1Password)
```
En `/opt/centinela/.env` de JP deben estar (mismos valores que JE salvo el nombre):
```
NODO_NOMBRE=JP
NODO_ROL=respaldo
DATABASE_URL=<lo pone servidor/conectar_cloudsql.sh: Cloud SQL por el Auth Proxy local>
OLLAMA_URL=http://centinela-ia:11434
OLLAMA_MODEL=centinela
LLAMADAS_TOKEN=<la misma de JE>
CONTROL_TOKEN=<opcional en JP: el panel solo detiene a JE>
GATEWAY_SECRET=<el mismo del Worker y de JE>
BOT_SECRET=<el mismo de n8n y de JE>
```
Los dos últimos (auditoría, bloque 2) se ponen **sin que se vean** con el bloque `poner` de `docs/14_AUDITORIA_Y_MEJORAS.md` → *Despliegue del bloque 2*.

**Comprobar que los secretos coinciden sin mostrarlos** (en JE y en JP deben salir iguales):
```bash
for k in LLAMADAS_TOKEN GATEWAY_SECRET BOT_SECRET; do printf '%s ' $k; sudo grep "^$k=" /opt/centinela/.env | sha256sum | cut -c1-12; done
```
**Comprobar que la clave del celular es la misma sin mostrarla** (correr en JE y en JP, deben salir iguales):
```bash
sudo grep '^LLAMADAS_TOKEN=' /opt/centinela/.env | sha256sum | cut -c1-12
```
Y que JP esté publicado: `sudo tailscale funnel status` debe mostrar `https://centinela-jp.tailaf5c0b.ts.net` → `127.0.0.1:8000`.

## 3 · Prueba juntos (5 min)
1. `https://centinela.juan-gallego-sec.workers.dev/gateway/estado` → JE y JP `"online": true`.
2. Panel `/admin` → **⏸ Detener JE**.
3. Llamar al celular con la app *Centinela llamadas* → en la web debe aparecer **la llamada animada en ≤ 8 s**, y en el celular la notificación de riesgo.
4. Chat de la web y Telegram `/estado` → *Te atendió: JP*, respuesta rápida.
5. **▶ Reactivar JE** → en ≤ 30 s vuelve a atender JE.

## Si algo falla
| Síntoma | Revisa |
|---|---|
| Celular: `HTTP 401 … Token invalido` con JP | La `LLAMADAS_TOKEN` de JP no es la de JE (comparar con el `sha256sum` de arriba) |
| `/gateway/estado` → JP `online:false` | En JP: `systemctl status centinela`, `sudo tailscale funnel status` |
| La llamada no sale en la web pero el celular sí avisa | `curl -s https://centinela.juan-gallego-sec.workers.dev/api/llamadas?limite=1` debe mostrar la llamada con `"nodo":"JP"` |
