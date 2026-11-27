# 18 · Expo del martes 1 de diciembre 🛡️

> Todo lo que está hecho y listo, qué revisar antes y cómo mostrarlo. El guion por persona está en [`13_PITCH.md`](13_PITCH.md).
> Actualizado: 2026‑11‑26.

## 1 · Lo que está listo y en producción ✅
| Pieza | Estado | Cómo comprobarlo en 5 s |
|---|---|---|
| 🌐 **Web + PWA** (consulta, reporte, chat IA, clúster en vivo, "Para empresas") | En vivo, se ve bien en celular | https://centinela.juan-gallego-sec.workers.dev |
| ☁️ **Gateway Cloudflare** (failover < 1 s, cortacircuito 30 s, límites por IP, panel `/admin` con 2FA) | En vivo | `/gateway/estado` → `"activo":"JE"` |
| 🟢 **JE · Cloud Run** v1.8.0 (`centinela-je`, us-east1, 0‑1 instancias) | En línea, `db:true`, `ollama:true`, `vertex:true` | `/health` |
| 🟠 **JP · VM de JP** v1.8.0 por Tailscale Funnel | En línea, `db:true`, mismas huellas de secretos que JE, acceso directo → **403** | `/gateway/estado` → JP `online:true` |
| 🔁 **Failover JE → JP** | Probado con JP | Panel → *Detener JE* |
| 🗄️ **Cloud SQL** Postgres 17 (conector obligatorio, IAM) | Activo; JE por conector, JP por Auth Proxy | — |
| ⏰ **Cloud Scheduler (OIDC)** | Latido cada minuto + exportación diaria 01:15 | — |
| 🧠 **IA híbrida** (Ollama en el Lenovo → Gemini 3.8 Flash en Vertex AI con topes 20/h, 100/día) | Activa | Panel → pestaña **IA** |
| 📊 **BigQuery** `centinela_analitica` (8 tablas, 10 vistas, agregadas y anónimas) | Exportando a diario | — |
| 🖥️ **Panel `/admin`**: Resumen · Arquitectura · Seguridad · Ventas · IA | En vivo | Entrar con clave + Aegis |
| 🤖 **Bot de Telegram** (n8n en el Lenovo) y 📱 **app Android** de llamadas | Funcionando | `/estado` en el bot |
| 🔐 **Seguridad**: puerta única, PBKDF2 + 2FA, CSRF, IAM mínima, Secret Manager, CSP/HSTS, STRIDE + OWASP API Top 10 | Documentada y auditada (0 secretos, 0 vulnerabilidades altas) | `bash servidor/ataques.sh` |
| ✅ **CI** en cada PR: ruff, 122 tests, shellcheck, gitleaks, trivy | En verde | Insignia del README |
| 📄 **Documentos** | README de producto, pitch por rol, roles JE/JP/JM, docs 14‑17 | — |

**Costo:** ≈ 11 USD/mes (casi todo es Cloud SQL); Gemini ≈ 0,80 USD/mes normal, máximo ≈ 20 USD/mes por los topes.

## 2 · Lo que falta antes del martes ⏳
| # | Qué | Quién | Cuándo |
|---|---|---|---|
| 1 | **Panel de Looker Studio** (7 páginas, [`17_LOOKER_STUDIO.md`](17_LOOKER_STUDIO.md) §5) + enlace de solo lectura | JE | Antes del martes |
| 2 | **Verificación final en el PC de mesa** (auditoría de seguridad + web moderna, §4) | JE | Antes del martes |

✔ Hecho el 2026‑11‑26: JP con la hora sincronizada; fuente del 71 % verificada: DataCrédito Experian 2026, "en el último año" (`roles/JM_VENTAS.md` [4]).

## 3 · El día de la expo
### La noche anterior
- [ ] JP: VM **prendida desde el arranque** (no suspendida), `curl -s localhost:8000/health` → `"db":true`.
- [ ] Lenovo prendido, conectado a la corriente y sin suspenderse ([`11_LENOVO_IA.md`](11_LENOVO_IA.md) paso 8).
- [ ] Celular con la app *Centinela llamadas* cargado; otro celular listo para llamarlo.
- [ ] Looker con los datos del día (la exportación corre a la 01:15).
- [ ] Capturas del panel y de Looker en el portátil y en un celular (plan B).

### 30 min antes (en el salón)
```bash
GW=https://centinela.juan-gallego-sec.workers.dev
curl -s $GW/gateway/estado          # JE y JP online:true, activo JE, los dos db:true
curl -s -o /dev/null -w "%{http_code}\n" https://centinela-jp.tailaf5c0b.ts.net/api/stats   # 403
```
- [ ] Panel `/admin` abierto con sesión iniciada (dura 20 min: volver a entrar justo antes de la demo).
- [ ] Pestañas abiertas: web, panel (Arquitectura), Looker, Telegram.
- [ ] Hotspot del celular listo por si falla el internet del salón.

### Monitor del failover (en una terminal durante la demo)
```bash
GW=https://centinela.juan-gallego-sec.workers.dev
while true; do printf "%s  " "$(date +%T)"; curl -s -o /dev/null -D - $GW/api/stats | grep -i x-centinela-nodo || echo "SIN RESPUESTA"; sleep 1; done
```
Al pulsar *Detener JE* cambia `JE → JP` sin `SIN RESPUESTA`; con *Reactivar JE* vuelve a `JE` en ≤ 30 s.

### Orden de la demo (detalle en `13_PITCH.md` §6)
1. Web en el celular: consultar `300 123 4567` y reportar uno nuevo (la IA lo clasifica) — **JM**
2. Chat: pregunta de estafa → IA; "¿cuánto es 2+2?" → rechazo al instante — **JM**
3. Telegram: el profesor le escribe un número al bot — **JM**
4. Llamada real al celular con la app → notificación + aparece en la web — **JE**
5. **Failover:** *Detener JE* → todo sigue por JP → *Reactivar JE* — **JE + JP**
6. `bash servidor/ataques.sh` y pestaña **Seguridad** — **JP**
7. Panel → **IA** → *Detectar campañas* — **JE**
8. **Looker Studio** y pestaña **Ventas** — **JM**

### Si algo falla en vivo
| Falla | Qué hacer |
|---|---|
| Internet del salón | Hotspot del celular; JE está en la nube y no depende del salón |
| JP `online:false` o `db:false` | En JP: `timedatectl`, `sudo systemctl restart cloudsql-proxy centinela` ([`12_PRUEBA_CON_JP.md`](12_PRUEBA_CON_JP.md) "Si algo falla"); si no sale, explicar el failover con el panel (pestaña Arquitectura) |
| Lenovo apagado (IA) | No pasa nada: responde Gemini (se ve en la pestaña IA) — se puede contar como otro failover |
| Looker no carga | Capturas |
| Se venció la sesión del panel | Volver a entrar (clave + Aegis) |

## 4 · Verificación final en el PC de mesa (auditoría + web moderna)
Correr desde la raíz del repo, en `main` al día. Resultado esperado al 2026‑11‑26 entre paréntesis.

**Seguridad del código**
```bash
git checkout main && git pull
auditar .                                   # paquete local: gitleaks + semgrep + trivy
gitleaks git .                              # (0 secretos en todo el historial)
semgrep --config auto --exclude node_modules --exclude vendor .   # (2 falsos positivos conocidos, doc 14)
trivy fs --severity HIGH,CRITICAL .         # (0 altas/críticas)
python3 -m venv .venv && . .venv/bin/activate && pip install -r servidor/app/requirements.txt -r requirements-dev.txt
pytest -q && ruff check . && shellcheck -S warning $(git ls-files '*.sh')   # (122 passed, sin avisos)
```

**Seguridad del sistema en vivo** (solo nuestros propios servicios)
```bash
bash servidor/ataques.sh                    # 429 flood, 413 cuerpo gigante, 401 sin token, 403 saltarse el gateway, 404 internas, 429 leads
GW=https://centinela.juan-gallego-sec.workers.dev
curl -sI $GW/ | grep -iE "content-security|strict-transport|x-frame|x-content|referrer|permissions"
```
Salen CSP, HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y, desde 2026‑11‑27, **`Permissions-Policy`** y **`Cross-Origin-Opener-Policy`**. Resultados de la verificación: `14_AUDITORIA_Y_MEJORAS.md` → *Verificación final antes de la expo*.

**Web moderna** (rendimiento, accesibilidad, PWA, buenas prácticas)
```bash
npx lighthouse $GW --preset=desktop --output html --output-path ./lighthouse-escritorio.html --view
npx lighthouse $GW --form-factor=mobile --screenEmulation.mobile --output html --output-path ./lighthouse-movil.html --view
```
Y en el navegador (son públicos y no atacan nada, solo leen la página):
- **Mozilla Observatory** (cabeceras y CSP) y **SSL Labs** (TLS) con la URL de la web.
- DevTools → **Application** → Manifest y Service Worker (la PWA se puede instalar y funciona sin internet).
- DevTools → modo celular a 360 y 390 px: el menú se ve y nada se sale de la pantalla.

Los reportes de Lighthouse quedan en el PC (no subirlos al repo). Lo que salga se anota en `docs/14_AUDITORIA_Y_MEJORAS.md` y, si hay que corregir algo, va en una rama con su PR.

## 5 · Cifras para decir de memoria
- **71 %** de los colombianos recibió al menos un intento de fraude en el último año (DataCrédito Experian, 2026).
- Riesgo por **personas distintas**: 1 → 30, 2 → 50, **3 → 65 (alto)**, 5 → 83; 3 personas en 15 min = alerta de campaña.
- Failover en **menos de 1 s**; JE caído se recuerda **30 s**.
- **≈ 11 USD/mes** en total; Gemini con tope de **20 llamadas/hora y 100/día**.
- **122 tests**, CI con 5 herramientas, **0 secretos** y **0 vulnerabilidades altas**.
- Planes: Gratis · **Pro $14.900 COP/mes** · **Empresa desde $790.000 COP/mes** (piloto gratis 1 mes para 3 cooperativas).
