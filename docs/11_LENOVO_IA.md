# 11 · Lenovo de Juan — IA (`centinela-ia`): Ollama + n8n + bot de Telegram

> Desde 2026‑11‑17 el Lenovo reemplaza al PC de mesa como **cerebro IA**. JE (Google Cloud) y JP lo buscan por Tailscale como `centinela-ia`, así que **ellos no cambian nada** (`OLLAMA_URL=http://centinela-ia:11434`, `OLLAMA_MODEL=centinela`).
> Si el Lenovo está apagado, el sistema **sigue funcionando**: el chat responde por reglas y los reportes quedan sin clasificar.

**Tiempo:** 40‑60 min (la descarga del modelo es lo que más tarda).
**Agente sugerido:** ornith/pi local para lo rutinario; Claude si algo sale en rojo.
**Reglas:** secretos solo en 1Password. Nada de tokens en capturas ni en el chat del agente.

**Qué tener a mano (1Password):** el token del bot de Telegram y tu `chat_id`.

---

## Paso 0 · Revisar el equipo
```bash
grep PRETTY /etc/os-release
free -h | head -2
lspci | grep -iE 'vga|3d'
```
| Si ves… | Modelo base que usaremos |
|---|---|
| **NVIDIA** en `lspci` | `qwen2.5:7b` por GPU (mejor calidad) |
| Solo AMD/Intel integrada | `qwen2.5:3b` por CPU (rápido y suficiente) |

Necesitas al menos ~8 GB de RAM y ~10 GB libres en disco.

**Solo si hay NVIDIA:**
```bash
sudo pacman -S --needed nvidia-utils ollama-cuda
nvidia-smi        # debe mostrar la tarjeta
```

## Paso 1 · Bajar el proyecto
```bash
mkdir -p ~/Projects/juan && cd ~/Projects/juan
gh repo clone juan-student1/surprised-system || git clone https://github.com/juan-student1/surprised-system.git
cd surprised-system
```

## Paso 2 · Tailscale + Ollama (sin bajar modelos dos veces)
Elige el modelo base según el paso 0:
```bash
bash ia/instalar_ollama.sh qwen2.5:3b      # sin NVIDIA
# bash ia/instalar_ollama.sh qwen2.5:7b    # con NVIDIA
```
| Cuando aparezca… | Haz esto |
|---|---|
| Link `login.tailscale.com/...` | Ábrelo y entra con la **cuenta de la red del grupo** (juanSecuri / GitHub), la misma de `centinela-je` y `centinela-jp` |
| `ufw no está activo` | `sudo pacman -S --needed ufw && sudo ufw enable` y vuelve a correr el comando |

**Qué debes ver:**
- **IA LISTA**.
- En <https://login.tailscale.com/admin/machines> aparece **`centinela-ia`** en verde, sin `-1`. Si sale con `-1`, borra el `centinela-ia` viejo del panel y corre `sudo tailscale set --hostname=centinela-ia`.

## Paso 3 · Crear el modelo acotado `centinela`
JE y JP piden el modelo llamado **`centinela`** (solo habla de llamadas y estafas, respuestas cortas):
```bash
bash servidor/ia/configurar_ia.sh
```
- Detecta GPU o CPU, deja Ollama escuchando en la red, atendiendo **1 petición a la vez** y descargándose a los 10 min sin uso.
- **Qué debes ver:** "Modelo 'centinela' listo". En la prueba "cuánto es 2+2?" debe **negarse**: *"Solo puedo ayudarte con Centinela…"*.
- **Ignora el bloque "AHORA, en JE y en JP…"** del final: JE ya tiene esos valores (y JP los pone con su guía).

Prueba local:
```bash
ollama list                         # debe aparecer centinela
ollama run centinela "me llamaron diciendo que eran de Bancolombia y pidieron mi clave"
sudo ufw status | grep 11434        # 11434 abierto solo en tailscale0 y 172.16.0.0/12 (Docker)
```

## Paso 4 · Confirmar que JE ve la IA
Desde **Cloud Shell → dentro de la VM** (`gcloud compute ssh centinela-je --zone=us-east1-b --tunnel-through-iap`):
```bash
curl -s -m 5 http://centinela-ia:11434/api/tags | head -c 200; echo
```
Desde cualquier lado (espera ~20 s, JE revisa la IA cada 20 s):
```bash
curl -s https://centinela.juan-gallego-sec.workers.dev/health; echo
curl -s https://centinela.juan-gallego-sec.workers.dev/api/chat -H 'Content-Type: application/json' \
  -d '{"mensaje":"me llamó el 3001234567 diciendo que era del banco y pidió mi clave"}'; echo
```
**Qué debes ver:** `"ollama":true` en `/health` y `"fuente":"ollama"` en la respuesta del chat. 🎉 La IA quedó conectada.

## Paso 5 · n8n (Docker) con webhook público
```bash
bash ia/instalar_n8n.sh
```
- Instala Docker si falta y corre n8n en el contenedor `centinela-n8n`, que arranca solo con el PC.
- El **editor** queda privado en <http://localhost:5678> (o en el puerto que diga el script si el 5678 está ocupado).
- **Solo `/webhook`** queda público por Tailscale Funnel: `https://centinela-ia.<tailnet>.ts.net/webhook/...`.

**Qué debes ver:** **n8n LISTO**, y `sudo tailscale funnel status` lista `/webhook` y `/webhook-test`.

Abre <http://localhost:5678> → crea la **cuenta de dueño** (guárdala en 1Password) → *Skip* en la encuesta.

## Paso 6 · Bot de Telegram en n8n
1. **Credencial:** *Credentials* → **Add credential** → *Telegram API* → pega el **token del bot** (desde 1Password) → nombre `Telegram Centinela` → **Save**.
2. **Importar el bot:** *Workflows* → **Create workflow** → `⋯` → **Import from file…** → `~/Projects/juan/surprised-system/ia/n8n/centinela_bot.json`.
3. En los nodos **Telegram Trigger**, **Escribiendo…** y **Responder** → *Credential* = `Telegram Centinela`.
4. **Save** → interruptor **Active**.
   - Al activarlo, n8n le dice a Telegram que ahora los mensajes llegan al **Lenovo**. Esto reemplaza al webhook viejo del PC de mesa.
   - Si sale *"Bad webhook"*: `sudo tailscale funnel status` debe listar `/webhook`; si no, vuelve a correr `bash ia/instalar_n8n.sh`.

**Probar en Telegram:**
| Envías | Esperado |
|---|---|
| `/start` | Menú |
| `3001234567` | Ficha 🔴/🟠/🟢 |
| `/estado` | *Te atendió: JE* |
| `¿cómo sé si una llamada es estafa?` | Responde la IA |

## Paso 7 · Avisos automáticos (resumen 7:00 a. m. + alerta de failover)
1. Importa `ia/n8n/centinela_avisos.json` igual que en el paso 6.
2. En **Enviar resumen** y **Enviar alerta**: credencial `Telegram Centinela` y en *Chat ID* reemplaza `TU_CHAT_ID` por tu chat_id (de 1Password, o envía `/miid` al bot).
3. **Save** → **Active**.
4. Para probar ya: abre **Enviar resumen** → **Execute step** → debe llegarte el resumen a Telegram.

## Paso 8 (opcional, para la sustentación) · Que el Lenovo no se duerma con la tapa cerrada
Solo cuando esté conectado a la corriente:
```bash
sudo mkdir -p /etc/systemd/logind.conf.d
printf "[Login]\nHandleLidSwitchExternalPower=ignore\n" | sudo tee /etc/systemd/logind.conf.d/centinela-ia.conf
sudo systemctl kill -s HUP systemd-logind
```
Para deshacerlo: `sudo rm /etc/systemd/logind.conf.d/centinela-ia.conf && sudo systemctl kill -s HUP systemd-logind`.

---

## Checklist final
- [ ] `centinela-ia` en verde en Tailscale (sin `-1`).
- [ ] `ollama list` muestra `centinela`.
- [ ] Gateway `/health` → `"ollama":true`; `/api/chat` → `"fuente":"ollama"`.
- [ ] n8n: flujos **bot** y **avisos** en *Active*.
- [ ] El bot responde `/start`, un número y `/estado`.
- [ ] El resumen de prueba llegó a Telegram.

## Si algo falla
| Síntoma | Revisa |
|---|---|
| `ollama:false` en el gateway | ¿Lenovo prendido y en Tailscale? `systemctl status ollama`; desde la VM `curl http://centinela-ia:11434/api/tags` |
| `model "centinela" not found` | Correr el paso 3 (`configurar_ia.sh`) |
| La IA tarda mucho (más de ~20 s) | Pasar al modelo liviano: `ollama pull qwen2.5:3b && sed 's/^FROM .*/FROM qwen2.5:3b/' servidor/ia/Modelfile > /tmp/M && ollama create centinela -f /tmp/M` |
| El bot no responde | n8n → *Executions*: ¿llegó el mensaje? Si no, revisa el Funnel (`sudo tailscale funnel status`) y que el flujo esté *Active* |
| "Bad webhook" al activar | El Funnel no publica `/webhook`: vuelve a correr `bash ia/instalar_n8n.sh` |
| Puerto 5678 ocupado | Normal si tienes otro n8n: el script usa el siguiente libre y lo muestra al final |
