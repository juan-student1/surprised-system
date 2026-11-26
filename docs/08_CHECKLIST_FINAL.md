# 08 · Checklist final: cuando JP esté listo + sustentación

> ⚠️ **Histórico (era de las VM y Supabase).** Para la exposición usar [`18_EXPO.md`](18_EXPO.md) y [`13_PITCH.md`](13_PITCH.md).

## A · Integrar a JP (15 min, cuando su laptop diga "NODO JP LISTO")
- [ ] JP manda foto de `curl -s localhost:8000/health` con `"db":true`.
- [ ] Juan, desde su PC: `tailscale ping centinela-jp` responde.
- [ ] En JP (Juan puede hacerlo por `ssh USUARIO_JP@centinela-jp`):
  ```bash
  cd ~/surprised-system && sudo bash servidor/actualizar.sh        # "version":"1.3.0"
  sudo bash servidor/configurar_telegram.sh                        # MISMO token, chat_id y clave que JE
  ```
- [ ] `curl -s https://centinela.juan-gallego-sec.workers.dev/gateway/estado` → JE y JP `online:true`, `activo:"JE"`.
- [ ] En la web, sección *El clúster, en vivo*: JE "Atendiendo", JP "En espera, listo".
- [ ] Bot: `/estado` muestra 🟢 JE y 🟢 JP.

## B · Ensayo de failover (antes de la sustentación)
1. PC personal, terminal 1 (monitor):
   ```bash
   GW=https://centinela.juan-gallego-sec.workers.dev
   while true; do printf "%s  " "$(date +%T)"; curl -s -o /dev/null -D - $GW/health | grep -i x-centinela-nodo || echo "SIN RESPUESTA"; sleep 1; done
   ```
2. Web abierta en la sección del clúster y Telegram a la mano.
3. **Apagar la VM de JE**: consola de Google Cloud → Instancias de VM → `centinela-je` → **Detener** (o en Cloud Shell `gcloud compute instances stop centinela-je --zone=us-east1-b`).
4. Esperado: el monitor cambia `JE → JP` sin `SIN RESPUESTA`; la web muestra el aviso ámbar; a los ≤2 min llega a Telegram *"⚠️ JE dejó de responder…"*.
5. Consultar un número y reportar otro **con JE apagado** → funciona ("Respondió el servidor JP").
6. **Iniciar** la VM de JE → vuelve sola como principal (~1 min); llega *"✅ JE volvió…"*.
7. Anotar: hora de corte, segundos hasta que respondió JP, peticiones perdidas (meta: 0).

## C · Guion de sustentación (8‑10 min)
| Min | Qué se muestra | Quién |
|---|---|---|
| 0‑1 | El problema: llamadas de falsos bancos, cobranza, wangiri. "¿Quién te está llamando?" | JE |
| 1‑3 | Arquitectura (diagrama mermaid de `00_PLAN_MAESTRO.md`): JE en una VM gratis de Google Cloud, JP de respaldo, Tailscale, Cloudflare, Supabase, IA local en el Lenovo. Por qué VM y no Cloud Run; cero puertos públicos (SSH solo por IAP) | JP |
| 3‑4 | Web en vivo: consultar `300 123 4567` → celular rojo. Reportar uno nuevo con descripción → la IA lo clasifica | JE |
| 4‑5 | Telegram: el profesor le escribe un número al bot / `/estado` | JP |
| 5‑6 | **Llamada real:** alguien llama al celular sensor → notificación + Telegram + web en vivo | JE |
| 6‑8 | **Failover:** **detener la VM de JE en Google Cloud** frente a todos; la web y el bot siguen por JP; llega la alerta. Luego iniciarla y ver que vuelve sola | JP |
| 8‑10 | Resultados: RAM (PC viejo 63 % → 17 %; VM de 1 GB ~46 % con zram), latencias, 0 peticiones perdidas, **costo en Google Cloud (~4‑6 USD de 300)**, seguridad (RLS, ufw, IAP, tokens, hashes). Preguntas | Ambos |

**Plan B si falla internet en el salón:** JE está en la nube y no depende del salón; basta un celular con datos para el portátil que proyecta. Tener capturas y un video corto del failover grabado el día anterior.

## D · Evidencias para el informe
- [ ] `free -h` en JE con escritorio (antes) y en consola (después); `free -h` en la VM de Google Cloud.
- [ ] Captura del firewall de Google Cloud (solo `default-allow-internal` y SSH desde `35.235.240.0/20`) y del presupuesto con su gasto (tapar el ID de facturación).
- [ ] Captura de **Facturación → Informes** con el gasto final del crédito.
- [ ] Captura de `tailscale status` con los 3 nodos y latencias de `tailscale ping`.
- [ ] Tabla de failover del punto B.
- [ ] Captura de Supabase con RLS activado en las 5 tablas.
- [ ] `sudo ufw status verbose` de JE y JP.
- [ ] Capturas: web (escritorio y celular), bot, notificación del celular, flujos de n8n, bitácora del clúster.
- [ ] `docs/05_PRUEBAS.md` ejecutado con resultados.

## E · Pendientes opcionales (si sobra tiempo)
- Dominio propio barato (.com.co) apuntando a Cloudflare.
- Página `/acerca` con el informe técnico.
- Tercer nodo de emergencia en el PC personal.
