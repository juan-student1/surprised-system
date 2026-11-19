# 01 · JE — Servidor principal (VM e2‑micro en Google Cloud)

> ⚠️ **Histórico.** Desde 2026‑11‑18 JE corre en **Cloud Run** con la BD en **Cloud SQL**: ver [`15_CLOUD_RUN_CLOUD_SQL_IAM.md`](15_CLOUD_RUN_CLOUD_SQL_IAM.md). Esta guía queda como registro y sirve hasta borrar la VM (`nube/99_borrar_vm.sh`). El paso 2 (alerta de presupuesto) sigue vigente.

> Desde 2026‑11‑17 el nodo JE corre en **Google Cloud** (crédito del curso) y no en el PC de mesa.
> **Antes de empezar:** proyecto en Supabase con `schema.sql` (`04_NUBE.md`) y la cadena *Session pooler* a mano.
> La guía para Mint/Arch en un PC físico sigue sirviendo para JP: `02_JP_SERVIDOR_RESPALDO.md`.

**Regla del curso:** gastar lo mínimo de los 300 USD. Solo debe cobrar la IP pública efímera (~3,6 USD/mes).

## Paso 1 · Cuenta y prueba gratis
1. Tarjeta débito virtual (Nu o Lulo) con **compras internacionales** activas y algo de saldo. Google hace una retención temporal (en nuestro caso ~98.000 COP) y la devuelve.
2. <https://console.cloud.google.com> → **Comenzar gratis** → país Colombia → verificación por SMS → cuenta *Individual* → tarjeta → **Iniciar prueba gratuita**.
3. **Nunca** dar clic en "Activar cuenta completa".

## Paso 2 · Alerta de presupuesto (día 1)
**Facturación → Presupuestos y alertas → Crear presupuesto**
- Nombre `centinela-presupuesto`, mensual, todos los proyectos y servicios.
- **Créditos: desmarcar "Promociones y otros"** (si no, el gasto se ve en 0 y la alerta nunca suena).
- Importe 5‑10 USD; umbrales 50 %, 90 %, 100 % reales y 100 % previsto.

## Paso 3 · Proyecto y API
Selector de proyectos → **Proyecto nuevo** → `centinela` → Crear y seleccionarlo. Buscar **Compute Engine API** → **Habilitar**.

## Paso 4 · Crear la VM (casillas que ahorran dinero)
**Compute Engine → Instancias de VM → Crear instancia**

| Sección | Valor |
|---|---|
| Nombre | `centinela-je` |
| Región / zona | `us-east1` / `us-east1-b` (nivel gratis y cerca de Colombia) |
| Máquina | E2 → **e2-micro** (el estimado de ~7 USD no descuenta el nivel gratis) |
| SO | **Debian 12 (bookworm)** x86/64 — más liviano que Ubuntu (sin snapd) |
| Disco | **Disco persistente estándar**, 20 GB ⚠️ el "equilibrado" cobra |
| Protección de datos | **Sin copias de seguridad** (los snapshots cobran) |
| Firewall | **No** marcar HTTP ni HTTPS |
| IPv4 externa | **Efímera** (nunca IP estática) |
| Observabilidad | **Desmarcar** Ops Agent |

## Paso 5 · Firewall de la nube: cero puertos al mundo
Buscar **Firewall** (Red de VPC):
- **Borrar** `default-allow-rdp` y `default-allow-icmp`.
- **Editar** `default-allow-ssh`: origen `0.0.0.0/0` → **`35.235.240.0/20`** (túnel IAP de Google: exige login en la cuenta).
- Queda solo `default-allow-internal` y SSH por IAP. La web entra por **Tailscale Funnel**, no por el firewall.

Entrar a la VM desde **Cloud Shell** (ícono `>_`, gratis):
```bash
gcloud config set project ID_DEL_PROYECTO
gcloud compute ssh centinela-je --zone=us-east1-b --tunnel-through-iap
```

## Paso 6 · Tailscale: liberar el nombre
En <https://login.tailscale.com/admin/machines> borrar el `centinela-je` viejo (PC de mesa). Así la VM toma el mismo nombre y **la URL del Funnel no cambia** (si no, queda `centinela-je-1` y habría que cambiar `gateway/wrangler.toml`).

## Paso 7 · Instalar el nodo (dentro de la VM)
```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/juan-student1/surprised-system.git
cd surprised-system
sudo bash servidor/instalar_nodo.sh JE
```

| Cuando aparezca… | Haz esto |
|---|---|
| `Google Cloud detectado…` | Nada: el script deja SSH por IAP también en `ufw` (si no, Cloud Shell quedaría bloqueado) |
| Link `login.tailscale.com/...` | Abrirlo e iniciar sesión con la cuenta de la red del grupo |
| `DATABASE_URL:` | Cadena *Session pooler* de Supabase |
| `Nombre Tailscale del PC con Ollama [centinela-ia]` | Enter |
| `Frase secreta` | La **misma** que usa JP (`SAL_HASH`) |

Al final: **NODO JE (principal) LISTO** con `https://centinela-je.<tailnet>.ts.net`.

## Paso 8 · Tokens (los mismos de JP y del Worker)
`CONTROL_TOKEN`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `LLAMADAS_TOKEN`. Pegarlos **sin que se vean en pantalla** (no usar `tee` ni `nano` frente a una captura):
```bash
poner(){ read -rsp "$1 (no se ve al pegar): " V; echo; sudo sed -i "/^$1=/d" /opt/centinela/.env; printf '%s=%s\n' "$1" "$V" | sudo tee -a /opt/centinela/.env >/dev/null; unset V; }
poner CONTROL_TOKEN
poner TELEGRAM_TOKEN
poner TELEGRAM_CHAT_ID
poner LLAMADAS_TOKEN
clear
sudo cut -d= -f1 /opt/centinela/.env | sort | uniq -d     # no debe imprimir nada
sudo systemctl restart centinela
sudo systemctl enable --now ufw
```

## Paso 9 · Comprobar
```bash
sleep 15; curl -s localhost:8000/health; echo      # con Supabase pausado tarda más en arrancar
sudo ufw status verbose                              # active, deny incoming, tailscale0 + 35.235.240.0/20
systemctl is-active centinela tailscaled ufw fail2ban
free -h
```
Desde cualquier lado:
```bash
curl -s https://centinela.juan-gallego-sec.workers.dev/gateway/estado     # "activo":"JE"
```

## Comandos de operación
| Para… | Comando |
|---|---|
| Entrar a la VM | Cloud Shell → `gcloud compute ssh centinela-je --zone=us-east1-b --tunnel-through-iap` |
| Ver si la API corre | `systemctl status centinela` |
| Logs en vivo | `journalctl -u centinela -f` |
| Reiniciar API | `sudo systemctl restart centinela` |
| Actualizar desde GitHub | `cd ~/surprised-system && sudo bash servidor/actualizar.sh` (hace `git pull` solo) |
| Link público | `tailscale funnel status` |
| Apagar / prender la VM (demo de failover) | `gcloud compute instances stop centinela-je --zone=us-east1-b` (y `start` para prender) |
| Ver gasto | Consola → **Facturación → Informes** |

## Problemas comunes
| Síntoma | Causa | Solución |
|---|---|---|
| `db:false` | Supabase pausado o cadena mal copiada | Despausar en Supabase; usar **Session pooler** |
| `failed to resolve host 'postgres.xxxx'` | La contraseña tiene `/ # ? @` y rompe la cadena | El instalador ya la codifica; en un nodo existente re‑guardar `DATABASE_URL` con el link completo (ver abajo) |
| Link `db.xxxx.supabase.co` | Es la *Direct connection* (solo IPv6) | Usar la **Session pooler** (`…pooler.supabase.com`) |
| `ollama:false` | Lenovo apagado o sin Tailscale | Normal: el chatbot responde con reglas |
| `/health` vacío justo tras reiniciar | La API aún arranca (más lento con BD caída) | Esperar 10‑20 s |
| Cloud Shell no entra por SSH | Regla IAP borrada o `ufw` sin `35.235.240.0/20` | Revisar el firewall del paso 5 y volver a correr el instalador |
| URL termina en `-1` | El `centinela-je` viejo seguía en Tailscale | Borrarlo en el panel y `sudo tailscale set --hostname=centinela-je` |

## Corregir `DATABASE_URL` en un nodo ya instalado (sin que se vea)
Pegar el link **completo** del Session pooler (con la contraseña); el bloque codifica los símbolos:
```bash
poner_db(){ read -rsp "Link COMPLETO del pooler (no se ve al pegar): " U; echo; [[ "$U" == *pooler.supabase.com* ]] || { echo "❌ No es el Session pooler"; return 1; }; L=$(U="$U" python3 -c 'import os,urllib.parse as u;s=os.environ["U"].strip();e,r=s.split("://",1);c,h=r.rsplit("@",1);us,pw=c.split(":",1);print(f"{e}://{us}:{u.quote(u.unquote(pw),safe=str())}@{h}")'); sudo sed -i '/^DATABASE_URL=/d' /opt/centinela/.env; printf 'DATABASE_URL=%s\n' "$L" | sudo tee -a /opt/centinela/.env >/dev/null; unset U L; echo "✅ DATABASE_URL guardada"; }
poner_db && sudo systemctl restart centinela
```

## Cierre del curso
Ver `00_PLAN_MAESTRO.md` §7: cerrar el proyecto, cerrar la facturación, quitar la tarjeta y revocar el token del bot.
