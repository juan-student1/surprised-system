/**
 * CENTINELA · Gateway con failover + escudo de peticiones (Cloudflare Worker, plan gratis)
 *
 *   Usuario ──► centinela.<cuenta>.workers.dev ──► JE (principal, Tailscale Funnel)
 *                                              └─► JP (respaldo) si JE no responde
 *
 * Cloudflare es la primera línea de defensa: absorbe el tráfico volumétrico (DDoS) antes
 * de que llegue a los PCs. Encima de eso, este Worker limita las peticiones por IP para
 * que una avalancha nunca sature a los nodos, y hace failover a JP si el principal cae.
 *
 * Variables (wrangler.toml): NODO_PRINCIPAL, NODO_RESPALDO.
 * Opcionales: LIMITE_MIN (peticiones/min por IP, def. 100), LIMITE_CHAT_MIN (def. 12).
 * Admin en el borde (profesor): ADMIN_USER, ADMIN_HASH, SECRET_KEY (opcional), ADMIN_TOTP (opcional).
 * Si ADMIN_USER/HASH existen, /admin y /login se sirven aquí sin tocar JE (ver docs/10_AUTENTICACION.md).
 * Si no, se reenvían a JE/JP como antes.
 */

const TIMEOUT_MS = 6000;        // un nodo que no responde en 6 s se considera caído
const TIMEOUT_SALUD_MS = 2500;  // chequeo rápido de /health antes de la IA
const TIMEOUT_CHAT_MS = 90000;  // la IA puede tardar
const MAX_BODY = 4096;          // cuerpo máximo de una petición (bytes); corta payloads de ataque

// ---------- Cortacircuito (failover rápido) ----------
// Si un nodo falla, se marca caído 30 s: las peticiones van DIRECTO al otro sin esperar timeouts.
// Mientras está marcado, se le hace un chequeo de /health en segundo plano para devolverlo apenas reviva.
// Se guarda en memoria del isolate y en la Cache API (compartida por los isolates del mismo datacenter).
const CAIDO_MS = 30000;
const VIVO_RECIENTE_MS = 15000;
const caidos = new Map();   // nombre -> hasta (ms)
const vivosOk = new Map();  // nombre -> último ok (ms)
const claveBreaker = (n) => new Request("https://breaker.centinela.internal/" + n.nombre);

async function estaCaido(n) {
  const hasta = caidos.get(n.nombre) || 0;
  if (hasta > Date.now()) return true;
  try {
    const r = await caches.default.match(claveBreaker(n));
    if (r) {
      const h = Number(await r.text()) || 0;
      if (h > Date.now()) { caidos.set(n.nombre, h); return true; }
    }
  } catch (e) {}
  return false;
}
async function marcarCaido(n) {
  const hasta = Date.now() + CAIDO_MS;
  caidos.set(n.nombre, hasta);
  vivosOk.delete(n.nombre);
  try {
    await caches.default.put(claveBreaker(n), new Response(String(hasta), { headers: { "Cache-Control": "max-age=30" } }));
  } catch (e) {}
}
async function marcarVivo(n) {
  vivosOk.set(n.nombre, Date.now());
  if (caidos.has(n.nombre)) {
    caidos.delete(n.nombre);
    try { await caches.default.delete(claveBreaker(n)); } catch (e) {}
  }
}
async function sondear(n) {   // chequeo en segundo plano de un nodo marcado caído
  try {
    const r = await conTimeout(n.base + "/health", {}, TIMEOUT_SALUD_MS);
    if (r.status < 500) await marcarVivo(n); else await marcarCaido(n);
  } catch (e) { await marcarCaido(n); }
}

const VENTANA_MS = 60000;
const visitas = new Map();

// Bloqueo de fuerza bruta para el panel (memoria del isolate, respaldo de SECURE_DELAY del borde)
const loginFallos = new Map(); // ip -> timestamps[]

function limitado(clave, maximo) {
  const ahora = Date.now();
  const cola = (visitas.get(clave) || []).filter((t) => ahora - t < VENTANA_MS);
  cola.push(ahora);
  visitas.set(clave, cola);
  if (visitas.size > 8000) {
    visitas.delete(visitas.keys().next().value);
  }
  return cola.length > maximo;
}

// Bloqueo de fuerza bruta: 5 fallos por IP o 20 fallos en total (cualquier IP) bloquean 15 min.
// Se guarda en memoria y en la Cache API para que valga entre isolates del mismo datacenter.
const BLOQUEO_MS = 15 * 60 * 1000;
const MAX_FALLOS_IP = 5;
const MAX_FALLOS_GLOBAL = 20;
const claveFallos = (k) => new Request("https://login.centinela.internal/" + encodeURIComponent(k));
async function leerFallos(k) {
  const ahora = Date.now();
  let arr = loginFallos.get(k) || [];
  try {
    const r = await caches.default.match(claveFallos(k));
    if (r) arr = arr.concat(JSON.parse(await r.text()));
  } catch (e) {}
  arr = [...new Set(arr)].filter((t) => ahora - t < BLOQUEO_MS);
  loginFallos.set(k, arr);
  return arr;
}
async function loginBloqueado(ip) {
  return (await leerFallos("ip:" + ip)).length >= MAX_FALLOS_IP
    || (await leerFallos("global")).length >= MAX_FALLOS_GLOBAL;
}
async function registrarFallo(ip) {
  for (const k of ["ip:" + ip, "global"]) {
    const arr = await leerFallos(k);
    arr.push(Date.now());
    loginFallos.set(k, arr);
    try {
      await caches.default.put(claveFallos(k), new Response(JSON.stringify(arr.slice(-50)), { headers: { "Cache-Control": "max-age=900" } }));
    } catch (e) {}
  }
}
async function limpiarFallos(ip) {
  loginFallos.delete("ip:" + ip);
  try { await caches.default.delete(claveFallos("ip:" + ip)); } catch (e) {}
}

// ---------- Admin en el borde ----------
const enc = new TextEncoder();
const dec = new TextDecoder();
function hexToBytes(h) { const a = []; for (let i = 0; i < h.length; i += 2) a.push(parseInt(h.slice(i, i + 2), 16)); return new Uint8Array(a); }
function toHex(buf) { return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join(""); }
function parseCookies(req) {
  const out = {};
  const raw = req.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}
async function pbkdf2(clave, saltHex, iter) {
  const key = await crypto.subtle.importKey("raw", enc.encode(clave), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", iterations: iter, salt: hexToBytes(saltHex) }, key, 256);
  return toHex(bits);
}
async function claveOk(clave, guardado) {
  try {
    const [pref, saltHex, hashHex] = String(guardado).split("$");
    if (pref !== "pbkdf2" || !saltHex || !hashHex) return false;
    const h = await pbkdf2(clave, saltHex, 100000);
    // comparación en tiempo constante (mismo largo 64 chars hex)
    let diff = 0;
    if (h.length !== hashHex.length) return false;
    for (let i = 0; i < h.length; i += 1) diff |= h.charCodeAt(i) ^ hashHex.charCodeAt(i);
    return diff === 0;
  } catch { return false; }
}
function base32ToBytes(s) {
  const ALF = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  s = s.replace(/[^A-Z2-7]/gi, "").toUpperCase();
  const bits = [];
  for (const ch of s) bits.push(ALF.indexOf(ch));
  let out = [];
  for (let i = 0; i < bits.length; i += 1) {
    // expandir bits
  }
  // implementación compacta RFC4648
  let buffer = 0, n = 0;
  const res = [];
  for (const ch of s) {
    buffer = (buffer << 5) | ALF.indexOf(ch);
    n += 5;
    if (n >= 8) { n -= 8; res.push((buffer >> n) & 0xff); }
  }
  return new Uint8Array(res);
}
async function totpOk(secreto, codigo) {
  if (!secreto) return true;
  try {
    const keyBytes = base32ToBytes(secreto);
    const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
    const ahora = Math.floor(Date.now() / 1000);
    const code = String(codigo || "").replace(/\s/g, "");
    for (const d of [-1, 0, 1]) {
      const step = Math.floor(ahora / 30) + d;
      const msg = new DataView(new ArrayBuffer(8));
      msg.setUint32(0, Math.floor(step / 0xffffffff));
      msg.setUint32(4, step >>> 0);
      const sig = await crypto.subtle.sign("HMAC", key, msg.buffer);
      const o = new Uint8Array(sig)[19] & 15;
      const val = (((new Uint8Array(sig)[o] & 0x7f) << 24) | (new Uint8Array(sig)[o + 1] << 16) | (new Uint8Array(sig)[o + 2] << 8) | new Uint8Array(sig)[o + 3]);
      const otp = String(val % 1000000).padStart(6, "0");
      if (otp === code) return true;
    }
    return false;
  } catch { return false; }
}
const SESION_SEG = 20 * 60;
const COOKIE = "__Host-centinela_admin";
async function huella(req) {   // la sesión queda atada al navegador que inició sesión
  const d = await crypto.subtle.digest("SHA-256", enc.encode(req.headers.get("User-Agent") || ""));
  return toHex(d).slice(0, 16);
}
async function firmarAsync(usuario, secret, req) {
  const cuerpo = btoa(JSON.stringify({ u: usuario, ua: await huella(req), exp: Math.floor(Date.now() / 1000) + SESION_SEG }));
  const k = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(cuerpo));
  return cuerpo + "." + toHex(sig);
}
async function sesionValida(cookieVal, secret, req) {
  if (!secret || !cookieVal || !cookieVal.includes(".")) return false;
  try {
    const [cuerpo, firma] = cookieVal.split(".");
    const k = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const sig = await crypto.subtle.sign("HMAC", k, enc.encode(cuerpo));
    const esp = toHex(sig);
    if (esp.length !== firma.length) return false;
    let diff = 0;
    for (let i = 0; i < esp.length; i += 1) diff |= esp.charCodeAt(i) ^ firma.charCodeAt(i);
    if (diff !== 0) return false;
    const obj = JSON.parse(atob(cuerpo));
    return obj.exp > Math.floor(Date.now() / 1000) && obj.ua === await huella(req);
  } catch { return false; }
}

const LOGIN_CSS = "body{font-family:system-ui,sans-serif;background:#0e1424;color:#e7ebf4;margin:0;padding:24px}.card{max-width:480px;margin:6vh auto;background:#161e33;border:1px solid #283252;border-radius:16px;padding:28px}h1{font-size:20px;margin:0 0 4px}.sub{color:#9ba5bd;margin:0 0 18px;font-size:14px}label{display:block;font-size:13px;color:#9ba5bd;margin:12px 0 4px}input{width:100%;box-sizing:border-box;padding:11px;border-radius:8px;border:1px solid #283252;background:#0e1424;color:#e7ebf4;font-size:15px}button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:8px;background:#2346d8;color:#fff;font-size:15px;font-weight:600;cursor:pointer}.err{background:#3a0f16;color:#ff8a98;border:1px solid #cc2539;border-radius:8px;padding:10px;font-size:14px;margin-bottom:12px}.count{color:#9ba5bd;font-size:12px;margin-top:12px;text-align:center}";

function loginHtml(error, totp) {
  const err = error ? `<div class=err>${error}</div>` : "";
  const totpHtml = totp ? `<label>Código (Aegis)</label><input name=codigo inputmode=numeric autocomplete=one-time-code required>` : "";
  return `<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1"><title>Centinela · Panel</title><style>${LOGIN_CSS}</style></head><body><div class=card><h1>🛡️ Centinela · Panel</h1><p class=sub>Acceso solo para el equipo (profesor / admin)</p>${err}<form method=post action="/admin/login"><label>Usuario</label><input name=usuario autocomplete=username required autofocus><label>Contraseña</label><input name=clave type=password autocomplete=current-password required>${totpHtml}<button>Entrar</button></form><p class=count>Verificación: PBKDF2-HMAC-SHA256 · sesión firmada HMAC de 20 min atada al navegador · bloqueo tras 5 intentos/IP · anti-CSRF · TOTP opcional (Aegis).</p></div></body></html>`;
}

function escHtml(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function fmtNum(n){var m=n&&String(n).match(/^\+57(\d{3})(\d{3})(\d{4})$/);return m?"+57 "+m[1]+" "+m[2]+" "+m[3]:(n||"");}
var CAT_PANEL={estafa:"Estafa",suplantacion:"Falso banco",cobranza:"Cobranza",telemarketing:"Telemarketing",wangiri:"Wangiri",extorsion:"Extorsion",encuesta:"Encuesta",otro:"Otro"};
async function datosPanel(env){
  const sanos = [], marcados = [];
  for (const n of nodos(env)) { if (await estaCaido(n)) marcados.push(n); else sanos.push(n); }
  for (const n of [...sanos, ...marcados]) {
    try {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 8000);
      try {
        const hg = { "X-Centinela-Gateway": env.GATEWAY_SECRET || "1" };
        const sres = await fetch(n.base + "/api/stats", { signal: c.signal, headers: hg });
        if (!sres.ok) throw new Error("down");
        const s = await sres.json();
        const tres = await fetch(n.base + "/api/top?limite=100", { signal: c.signal, headers: hg });
        const tp = tres.ok ? await tres.json() : [];
        return { stats: s, top: Array.isArray(tp) ? tp : [], nodo: n.nombre };
      } finally { clearTimeout(t); }
    } catch (e) {}
  }
  return { stats: null, top: [], nodo: null };
}
// ---------- Panel: pestañas (Resumen · Arquitectura [JE] · Seguridad [JP] · Ventas [JM]) ----------
// Todo se arma en el servidor: cero JavaScript en el navegador (compatible con la CSP script-src 'self').
const PESTANAS = [["/admin", "Resumen"], ["/admin/arquitectura", "Arquitectura"], ["/admin/seguridad", "Seguridad"], ["/admin/ventas", "Ventas"], ["/admin/ia", "IA"]];
const REPO_DOCS = "https://github.com/juan-student1/surprised-system/blob/main/docs/roles/";
const PANEL_CSS = " .hdr{display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:4px} .top{max-width:1100px;margin:0 auto} table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px} th,td{padding:8px;border-bottom:1px solid #283252;text-align:left;vertical-align:top} th{color:#9ba5bd} a{color:#7a93ff} .stats{color:#9ba5bd;font-size:14px;margin:0 0 8px} .ctrl{background:#161e33;border:1px solid #283252;border-radius:12px;padding:16px;margin:12px 0 18px} .ctrl-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px} .act{font-size:22px;font-weight:700;color:#7dffa9;margin-top:2px} .lbl{color:#9ba5bd;font-size:12px;text-transform:uppercase;letter-spacing:.04em} .grupo{display:flex;gap:10px;flex-wrap:wrap} .ctrl form{display:inline;margin:0} .ctrl button{width:auto;margin-top:0;padding:10px 14px;font-size:14px} .rojo{background:#cc2539} .verde{background:#1f9d57} .nota{color:#9ba5bd;font-size:13px;margin:12px 0 0} .count{color:#9ba5bd;font-size:12px;margin-top:14px}"
  + " .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 6px;border-bottom:1px solid #283252} .tabs a{padding:9px 14px;border-radius:8px 8px 0 0;color:#9ba5bd;text-decoration:none;font-weight:600;font-size:14px} .tabs a[aria-current=page]{background:#161e33;color:#e7ebf4;border:1px solid #283252;border-bottom-color:#161e33;margin-bottom:-1px}"
  + " .chip{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700} .ok{background:#0f2a1a;color:#7dffa9} .mal{background:#3a0f16;color:#ff8a98} .gris{background:#232c45;color:#9ba5bd}"
  + " .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0} .kpi{background:#161e33;border:1px solid #283252;border-radius:12px;padding:12px} .kpi b{display:block;font-size:24px} .kpi span{color:#9ba5bd;font-size:12px}"
  + " .barra{height:8px;border-radius:4px;background:#cc2539;min-width:2px} .que{color:#9ba5bd;font-size:13px} .scroll{overflow-x:auto} h2{font-size:17px;margin:22px 0 4px}";

function chip(ok, si = "En línea", no = "Caído", nada = "Sin datos") {
  return ok === true ? `<span class="chip ok">${si}</span>` : ok === false ? `<span class="chip mal">${no}</span>` : `<span class="chip gris">${nada}</span>`;
}
function horaCO(iso, conDia = true) {
  try {
    return new Date(iso).toLocaleString("es-CO", { timeZone: "America/Bogota", hour: "2-digit", minute: "2-digit", ...(conDia ? { day: "2-digit", month: "short" } : {}) });
  } catch { return escHtml(iso); }
}
function hace(seg) {
  if (seg == null || isNaN(seg)) return "—";
  return seg < 90 ? Math.round(seg) + " s" : seg < 5400 ? Math.round(seg / 60) + " min" : Math.round(seg / 3600) + " h";
}
function marco(username, actual, cuerpo) {
  const tabs = PESTANAS.map(([href, txt]) => `<a href="${href}"${href === actual ? ' aria-current="page"' : ""}>${txt}</a>`).join("");
  return "<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content=\"width=device-width, initial-scale=1\"><title>Centinela · Panel</title><style>" + LOGIN_CSS + PANEL_CSS + "</style></head><body><div class=top>"
    + "<div class=hdr><h1>Panel de Centinela</h1><a href=\"/admin/salir\">Salir (" + escHtml(username) + ")</a></div>"
    + "<nav class=tabs aria-label=\"Pestañas del panel\">" + tabs + "</nav>" + cuerpo + "</div></body></html>";
}

// Pide una ruta a los nodos (sanos primero). Las rutas /api/interno/* llevan además el CONTROL_TOKEN.
async function pedirNodo(env, ruta, interno = false) {
  const sanos = [], marcados = [];
  for (const n of nodos(env)) { if (await estaCaido(n)) marcados.push(n); else sanos.push(n); }
  for (const n of [...sanos, ...marcados]) {
    try {
      const h = { "X-Centinela-Gateway": env.GATEWAY_SECRET || "1" };
      if (interno) h["x-centinela-control"] = env.CONTROL_TOKEN || "";
      const r = await conTimeout(n.base + ruta, { headers: h }, 8000);
      if (r.ok && esDeCentinela(r)) return { data: await r.json(), nodo: n.nombre };
    } catch (e) {}
  }
  return { data: null, nodo: null };
}

function panelHtml(username, d) {
  d = d || { stats: null, top: [], nodo: null };
  const act = d.nodo || "sin conexion";
  const linea = d.stats
    ? (d.stats.numeros + " numeros · " + d.stats.reportes + " reportes · " + d.stats.alto_riesgo + " de riesgo alto")
    : "Sin conexion a la base (recarga en unos segundos).";
  const filas = (d.top && d.top.length)
    ? d.top.map(function(f){return "<tr><td>" + escHtml(fmtNum(f.numero)) + "</td><td>" + escHtml(f.pais||"") + "</td><td>" + escHtml(f.score) + "</td><td>" + escHtml(f.nivel) + "</td><td>" + escHtml(f.total_reportes) + "</td><td>" + escHtml(CAT_PANEL[f.categoria_principal]||"—") + "</td></tr>";}).join("")
    : "<tr><td colspan=6>Sin numeros todavia</td></tr>";
  const btn = function(nodo, accion, clase, txt){ return '<form method=post action="/admin/control"><input type=hidden name=nodo value="' + nodo + '"><input type=hidden name=accion value="' + accion + '"><button class="' + clase + '">' + txt + '</button></form>'; };
  return marco(username, "/admin",
    "<div class=ctrl><div class=ctrl-top><div><span class=lbl>Atendiendo ahora</span><div class=act>" + escHtml(act) + "</div></div>"
    + "<div class=grupo>" + btn("JE","pausar","rojo","⏸ Detener JE") + btn("JE","reactivar","verde","▶ Reactivar JE") + "</div></div>"
    + "<p class=nota>Detener JE lo deja de atender DE VERDAD (responde 503): el gateway enruta el tráfico a JP (otra máquina, otro internet). Reactívalo para repetir.</p></div>"
    + "<p class=stats>" + linea + " · datos vía " + escHtml(act) + "</p>"
    + "<div class=scroll><table><thead><tr><th>Numero</th><th>Pais</th><th>Riesgo</th><th>Nivel</th><th>Reportes</th><th>Tipo</th></tr></thead><tbody>" + filas + "</tbody></table></div>"
    + "<p class=count>Datos de /api/top y /api/stats (JE/JP), cargados por el gateway. Sin scripts en el navegador — compatible con el blindaje (CSP).</p>");
}

// Pestaña Arquitectura (JE): estado de cada pieza, con una línea de "qué es" para quien no es técnico.
async function paginaArquitectura(username, env) {
  const [est, cl] = await Promise.all([estado(env), pedirNodo(env, "/api/cluster")]);
  const h = Object.fromEntries(est.nodos.map((n) => [n.nombre, n]));
  const filaNodo = (cl.data && cl.data.nodos || []).reduce((a, n) => (a[n.nombre] = n, a), {});
  const edadLatido = (nom) => filaNodo[nom] && filaNodo[nom].ultimo_latido ? (Date.now() - Date.parse(filaNodo[nom].ultimo_latido)) / 1000 : null;
  const algun = (k) => est.nodos.some((n) => n.health && n.health[k] === true) ? true : est.nodos.some((n) => n.health) ? false : null;
  const pend = est.nodos.reduce((s, n) => s + ((n.health && n.health.pendientes) || 0), 0);
  const descNodo = (n) => n && n.online ? `v${escHtml(n.health.version)} · ${n.latencia_ms} ms · encendido hace ${hace(n.health.uptime_seg)} · CPU ${Math.round(n.health.cpu || 0)} %` : escHtml(n ? n.error || "sin respuesta" : "no configurado");
  const latJE = edadLatido("JE");
  const piezas = [
    ["Cloudflare Worker (gateway)", "Borde de Cloudflare", true, "Sirviendo esta página", "La puerta de entrada: reparte el tráfico, frena abusos por IP, publica la web y este panel."],
    ["JE · nodo principal", "Google Cloud Run (us-east1)", h.JE ? h.JE.online : null, descNodo(h.JE), "Atiende a los usuarios. Se apaga solo si no hay tráfico (costo casi cero)."],
    ["JP · nodo de respaldo", "VM de JP (Tailscale Funnel)", h.JP ? h.JP.online : null, descNodo(h.JP), "Si JE cae, el gateway manda todo aquí en menos de un segundo."],
    ["Base de datos", "Cloud SQL · Postgres 17", algun("db"), "Vista desde los nodos que respondieron", "Guarda números, reportes y eventos. Solo entra quien tenga identidad de Google (IAM)."],
    ["Latido programado", "Cloud Scheduler (OIDC)", latJE == null ? null : latJE < 180, latJE == null ? "Sin latidos de JE" : "Último latido de JE hace " + hace(latJE), "Cada minuto despierta a JE, sincroniza pendientes y revisa la IA."],
    ["IA local", "Lenovo · Ollama (modelo centinela) por Tailscale", algun("ollama"), algun("ollama") ? "Respondiendo" : "Pasa a Gemini o a reglas", "Primera opción: gratis y privada. Clasifica reportes y conversa."],
    ["IA de respaldo", "Vertex AI · Gemini Flash (a demanda)", algun("vertex"), algun("vertex") ? "Configurada, con topes por hora y por día" : "Apagada en este nodo", "Solo responde si el Lenovo no contesta, o cuando se pide un análisis profundo en la pestaña IA."],
    ["Modo degradado", "SQLite en cada nodo", pend === 0 ? true : pend > 0 ? false : null, pend + " reporte(s) en cola para sincronizar", "Si la base falla, los reportes se guardan en el nodo y se suben al volver."],
  ];
  const filas = piezas.map(([nom, donde, ok, det, que]) => `<tr><td><b>${nom}</b><div class=que>${que}</div></td><td>${donde}</td><td>${nom === "Modo degradado" ? chip(ok, "Sin cola", "Con cola") : chip(ok)}</td><td>${det}</td></tr>`).join("");
  const breaker = [];
  for (const n of nodos(env)) breaker.push(`${n.nombre}: ${(await estaCaido(n)) ? "<span class='chip mal'>marcado caído (30 s)</span>" : "<span class='chip ok'>disponible</span>"}`);
  return marco(username, "/admin/arquitectura",
    `<p class=stats>Activo ahora: <b>${escHtml(est.activo || "ninguno")}</b> · consultado ${horaCO(est.hora, false)} (hora Colombia) · Cortacircuito del gateway: ${breaker.join(" · ")}</p>`
    + `<div class=scroll><table><thead><tr><th>Pieza</th><th>Dónde corre</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>${filas}</tbody></table></div>`
    + `<p class=count>Decisiones (ADR), diagrama y costos: <a href="${REPO_DOCS}JE_ARQUITECTURA.md">docs/roles/JE_ARQUITECTURA.md</a>. Recarga la página para actualizar.</p>`);
}

// Último análisis del CI (gitleaks + trivy + tests) en main. Repo público: la API de GitHub no pide token.
// Se guarda 10 min en la Cache API para no gastar el límite de GitHub.
async function ultimoEscaneo(env) {
  const repo = env.REPO_GITHUB || "juan-student1/surprised-system";
  const clave = new Request("https://ci.centinela.internal/" + repo);
  try {
    const c = await caches.default.match(clave);
    if (c) return await c.json();
  } catch (e) {}
  try {
    const r = await conTimeout(`https://api.github.com/repos/${repo}/actions/workflows/ci.yml/runs?branch=main&per_page=1`,
      { headers: { "User-Agent": "centinela-gateway", Accept: "application/vnd.github+json" } }, 5000);
    if (!r.ok) return null;
    const run = ((await r.json()).workflow_runs || [])[0];
    const dato = run ? { estado: run.status, resultado: run.conclusion, fecha: run.updated_at, url: run.html_url, commit: (run.head_sha || "").slice(0, 7) } : null;
    try { await caches.default.put(clave, new Response(JSON.stringify(dato), { headers: { "Cache-Control": "max-age=600" } })); } catch (e) {}
    return dato;
  } catch (e) { return null; }
}

// Pestaña Seguridad (JP): peticiones bloqueadas por hora, rutas más atacadas, eventos, login y último escaneo.
async function paginaSeguridad(username, env) {
  const [sec, ci, fallosGlobal] = await Promise.all([pedirNodo(env, "/api/interno/seguridad?horas=24", true), ultimoEscaneo(env), leerFallos("global")]);
  const d = sec.data;
  let cuerpo = "";
  if (!d) {
    cuerpo += "<p class=nota>Sin datos de los nodos (revisa que CONTROL_TOKEN esté en el gateway y en JE, y que la migración db/004 esté aplicada).</p>";
  } else {
    const t = d.por_hora.reduce((a, f) => ({ a: a.a + (+f.c401 || 0), b: a.b + (+f.c403 || 0), c: a.c + (+f.c429 || 0) }), { a: 0, b: 0, c: 0 });
    const max = Math.max(1, ...d.por_hora.map((f) => (+f.c401 || 0) + (+f.c403 || 0) + (+f.c429 || 0)));
    cuerpo += `<div class=kpis><div class=kpi><b>${t.a}</b><span>401 · sin credencial válida (24 h)</span></div><div class=kpi><b>${t.b}</b><span>403 · intentaron saltarse el gateway</span></div><div class=kpi><b>${t.c}</b><span>429 · frenados por exceso de peticiones</span></div><div class=kpi><b>${fallosGlobal.length}</b><span>fallos de login al panel (15 min)</span></div></div>`;
    const filas = d.por_hora.map((f) => { const tot = (+f.c401 || 0) + (+f.c403 || 0) + (+f.c429 || 0); return `<tr><td>${horaCO(f.hora)}</td><td>${+f.c401 || 0}</td><td>${+f.c403 || 0}</td><td>${+f.c429 || 0}</td><td style="width:35%"><div class=barra style="width:${Math.round(100 * tot / max)}%"></div></td></tr>`; }).join("") || "<tr><td colspan=5>Ningún bloqueo en 24 h</td></tr>";
    cuerpo += `<h2>Bloqueos por hora (hora Colombia, vistos por ${escHtml(sec.nodo)})</h2><div class=scroll><table><thead><tr><th>Hora</th><th>401</th><th>403</th><th>429</th><th>Volumen</th></tr></thead><tbody>${filas}</tbody></table></div>`;
    const rutas = d.por_ruta.map((f) => `<tr><td><code>${escHtml(f.ruta)}</code></td><td>${escHtml(f.codigo)}</td><td>${escHtml(f.total)}</td></tr>`).join("") || "<tr><td colspan=3>—</td></tr>";
    cuerpo += `<h2>Rutas más bloqueadas</h2><div class=scroll><table><thead><tr><th>Ruta</th><th>Código</th><th>Total</th></tr></thead><tbody>${rutas}</tbody></table></div>`;
    const ev = d.eventos.map((e) => `<tr><td>${horaCO(e.creado)}</td><td>${escHtml(e.nodo)}</td><td>${escHtml(e.tipo)}</td><td>${escHtml(e.detalle)}</td></tr>`).join("") || "<tr><td colspan=4>—</td></tr>";
    cuerpo += `<h2>Eventos de seguridad</h2><div class=scroll><table><thead><tr><th>Cuándo</th><th>Nodo</th><th>Tipo</th><th>Detalle</th></tr></thead><tbody>${ev}</tbody></table></div>`;
  }
  const esc = ci ? `${chip(ci.resultado === "success" ? true : ci.resultado ? false : null, "Sin hallazgos", "Falló", "En curso")} commit <code>${escHtml(ci.commit)}</code> · ${horaCO(ci.fecha)} · <a href="${escHtml(ci.url)}">ver en GitHub</a>` : chip(null);
  cuerpo += `<h2>Último escaneo (CI en main: gitleaks, trivy, ruff, pytest, shellcheck)</h2><p class=stats>${esc}</p>`;
  cuerpo += `<p class=count>Los 429 del propio gateway (límites por IP en el borde) se ven en Cloudflare → Security → Analytics. Modelo de amenazas y checklist: <a href="${REPO_DOCS}JP_SEGURIDAD.md">docs/roles/JP_SEGURIDAD.md</a>.</p>`;
  return marco(username, "/admin/seguridad", cuerpo);
}

// Pestaña IA: uso de Ollama/Gemini, cupo de Gemini y "análisis profundo" a demanda (nunca automático).
async function pedirAnalisis(env, tipo) {
  // Solo JE tiene Vertex; el análisis puede tardar hasta ~60 s.
  const n = nodos(env).find((x) => x.nombre === "JE");
  if (!n) return { error: "JE no está configurado" };
  try {
    const r = await conTimeout(n.base + "/api/interno/analisis?tipo=" + tipo, { method: "POST",
      headers: { "X-Centinela-Gateway": env.GATEWAY_SECRET || "1", "x-centinela-control": env.CONTROL_TOKEN || "" } }, 90000);
    const d = await r.json().catch(() => ({}));
    return r.ok ? d : { error: d.detail || d.error || ("HTTP " + r.status) };
  } catch (e) { return { error: motivo(e) }; }
}
const lista = (xs) => (xs && xs.length) ? "<ul>" + xs.map((x) => "<li>" + escHtml(typeof x === "string" ? x : JSON.stringify(x)) + "</li>").join("") + "</ul>" : "<p class=que>—</p>";
function htmlAnalisis(a) {
  if (!a) return "";
  if (a.error) return `<div class=err>No se pudo hacer el análisis: ${escHtml(a.error)}</div>`;
  const r = a.resultado || {};
  const pie = `<p class=count>Generado con <b>${escHtml(a.fuente)}</b> en ${escHtml(a.nodo)}${a.desde_cache ? " (reutilizado: se pidió hace menos de 15 min)" : ""}.</p>`;
  if (a.tipo === "campanas") {
    const camp = (r.campanas || []).map((c) => `<tr><td><b>${escHtml(c.nombre)}</b><div class=que>${escHtml(c.patron)}</div></td><td>${(c.numeros || []).map((x) => escHtml(fmtNum(x))).join("<br>")}</td><td>${chip(c.riesgo === "alto" ? false : null, "", "Alto", "Medio")}</td><td>${escHtml(c.evidencia)}<div class=que>👉 ${escHtml(c.recomendacion)}</div></td></tr>`).join("") || "<tr><td colspan=4>No se detectaron campañas</td></tr>";
    return `<h2>Campañas detectadas (72 h)</h2><p class=stats>${escHtml(r.resumen)}</p><div class=scroll><table><thead><tr><th>Campaña</th><th>Números</th><th>Riesgo</th><th>Evidencia</th></tr></thead><tbody>${camp}</tbody></table></div>${pie}`;
  }
  return `<h2>${escHtml(r.titulo || "Resumen semanal")}</h2><p>${escHtml(r.resumen)}</p><h2>Hallazgos</h2>${lista(r.hallazgos)}<h2>Recomendaciones</h2>${lista(r.recomendaciones)}${pie}`;
}
async function paginaIA(username, env, analisis) {
  const { data } = await pedirNodo(env, "/api/interno/ia?horas=24", true);
  const v = data && data.vertex;
  const form = (tipo, txt, desc) => `<form method=post action="/admin/ia"><input type=hidden name=tipo value="${tipo}"><button>${txt}</button></form><p class=que>${desc}</p>`;
  let cuerpo = data
    ? `<div class=kpis><div class=kpi><b>${chip(data.ollama, "Activa", "Apagada")}</b><span>IA local (Ollama, Lenovo)</span></div>`
      + `<div class=kpi><b>${v && v.activo ? `${v.hora}/${v.max_hora}` : "—"}</b><span>llamadas a Gemini esta hora</span></div>`
      + `<div class=kpi><b>${v && v.activo ? `${v.dia}/${v.max_dia}` : "—"}</b><span>llamadas a Gemini hoy (24 h)</span></div>`
      + `<div class=kpi><b>${v && v.activo ? `${v.profundo_dia}/${v.max_profundo_dia}` : "—"}</b><span>análisis profundos hoy</span></div></div>`
      + `<p class=stats>Gemini: ${v && v.activo ? `<code>${escHtml(v.modelo)}</code> · región <code>${escHtml(v.region)}</code>` : "apagado en el nodo que respondió"}</p>`
    : "<p class=nota>Sin datos de los nodos.</p>";
  cuerpo += `<div class=ctrl><span class=lbl>Análisis profundo (a demanda, gasta cupo de Gemini)</span><div class=grupo style="margin-top:10px">`
    + form("campanas", "🔎 Detectar campañas", "Busca números que parecen la misma operación en las últimas 72 h.")
    + form("semanal", "🗓️ Resumen semanal", "Explica la semana para no técnicos y la compara con la anterior.") + "</div></div>";
  cuerpo += htmlAnalisis(analisis);
  const filas = data && data.uso && data.uso.length ? data.uso.map((u) => `<tr><td>${escHtml(u.proveedor)}</td><td>${escHtml(u.tipo)}</td><td>${escHtml(u.resultado)}</td><td>${escHtml(u.llamadas)}</td><td>${escHtml(u.tokens_entrada)} / ${escHtml(u.tokens_salida)}</td></tr>`).join("") : "<tr><td colspan=5>Sin uso registrado en 24 h</td></tr>";
  cuerpo += `<h2>Uso de IA (24 h)</h2><div class=scroll><table><thead><tr><th>Proveedor</th><th>Para qué</th><th>Resultado</th><th>Llamadas</th><th>Tokens entrada / salida</th></tr></thead><tbody>${filas}</tbody></table></div>`
    + `<p class=count>Por qué es híbrida (costo, privacidad, disponibilidad): <a href="https://github.com/juan-student1/surprised-system/blob/main/docs/16_VERTEX_AI.md">docs/16_VERTEX_AI.md</a>.</p>`;
  return marco(username, "/admin/ia", cuerpo);
}

// Pestaña Ventas (JM): leads del formulario "Para empresas". Datos personales: solo aquí, nunca en público.
const SEG_TXT = { persona: "Persona", call_center: "Call center / BPO", cooperativa: "Cooperativa", banco: "Banco / fintech", operador: "Operador", otro: "Otra" };
async function paginaVentas(username, env) {
  const { data, nodo } = await pedirNodo(env, "/api/interno/leads?limite=100", true);
  if (!data) return marco(username, "/admin/ventas", "<p class=nota>Sin datos de los nodos (CONTROL_TOKEN en gateway y JE, migración db/004 aplicada).</p>");
  const porSeg = {};
  for (const l of data) porSeg[l.segmento] = (porSeg[l.segmento] || 0) + 1;
  const kpis = `<div class=kpi><b>${data.length}</b><span>leads (últimos 100)</span></div>` + Object.entries(porSeg).sort((a, b) => b[1] - a[1]).map(([s, n]) => `<div class=kpi><b>${n}</b><span>${escHtml(SEG_TXT[s] || s)}</span></div>`).join("");
  const filas = data.map((l) => `<tr><td>${horaCO(l.creado)}</td><td>${escHtml(l.nombre)}<div class=que>${escHtml(l.empresa || "")}</div></td><td>${escHtml(SEG_TXT[l.segmento] || l.segmento)}</td><td>${escHtml(l.plan)}</td><td><a href="mailto:${escHtml(encodeURIComponent(l.correo).replace(/%40/g, "@"))}">${escHtml(l.correo)}</a><div class=que>${escHtml(l.telefono || "")}</div></td><td>${escHtml((l.mensaje || "").slice(0, 200))}</td><td>${escHtml(l.estado)}</td></tr>`).join("") || "<tr><td colspan=7>Todavía no hay leads</td></tr>";
  return marco(username, "/admin/ventas",
    `<div class=kpis>${kpis}</div><div class=scroll><table><thead><tr><th>Fecha</th><th>Contacto</th><th>Segmento</th><th>Plan</th><th>Correo / tel.</th><th>Mensaje</th><th>Estado</th></tr></thead><tbody>${filas}</tbody></table></div>`
    + `<p class=count>Datos vía ${escHtml(nodo)}. Datos personales bajo la Ley 1581 de 2012: no se copian fuera del panel y se borran si la persona lo pide. Plan comercial: <a href="${REPO_DOCS}JM_VENTAS.md">docs/roles/JM_VENTAS.md</a>.</p>`);
}

// Respuesta HTML del panel: nunca en caché, no indexable, y sin poder incrustarse.
function htmlAdmin(cuerpo, status = 200, extra = {}) {
  return new Response(cuerpo, { status, headers: { "content-type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", ...extra } });
}
function irA(destino, extra = {}) {
  return new Response("", { status: 303, headers: { Location: destino, "Cache-Control": "no-store", ...extra } });
}
// CSRF: un POST al panel solo vale si viene de esta misma página (además de SameSite=Strict).
// 1º Sec-Fetch-Site (lo pone el navegador, la página no lo puede falsificar).
// Ojo: con Referrer-Policy no-referrer el navegador manda "Origin: null" en los POST de formulario,
// por eso la política es same-origin y "null" nunca cuenta como origen válido.
function mismoOrigen(req, url) {
  const sfs = req.headers.get("Sec-Fetch-Site");
  if (sfs) return sfs === "same-origin";
  const o = req.headers.get("Origin");
  if (o && o !== "null") return o === url.origin;
  const r = req.headers.get("Referer");
  return Boolean(r && r.startsWith(url.origin + "/"));
}
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

async function handleAdmin(req, env, url) {
  const user = env.ADMIN_USER || "";
  const hash = env.ADMIN_HASH || "";
  const totp = env.ADMIN_TOTP || "";
  const secret = env.SECRET_KEY || "";
  // Sin SECRET_KEY no hay forma segura de firmar la sesión: el panel no se abre.
  if (!secret || secret.length < 32) return htmlAdmin(loginHtml("Panel deshabilitado: falta SECRET_KEY en el gateway.", false), 503);
  const cookies = parseCookies(req);
  const valid = await sesionValida(cookies[COOKIE] || "", secret, req);
  const borrar = `${COOKIE}=; HttpOnly; Path=/; Max-Age=0; SameSite=Strict; Secure`;
  if (url.pathname === "/admin/salir") return irA("/admin/login", { "Set-Cookie": borrar });

  if (req.method === "POST" && url.pathname === "/admin/login") {
    const ct = req.headers.get("content-type") || "";
    if (!ct.includes("application/x-www-form-urlencoded")) return new Response("Unsupported", { status: 415 });
    if (!mismoOrigen(req, url)) return new Response("Origen no permitido", { status: 403 });
    const ip = req.headers.get("CF-Connecting-IP") || "0.0.0.0";
    if (await loginBloqueado(ip)) {
      return htmlAdmin(loginHtml("Demasiados intentos. Espera 15 minutos.", false), 429, { "Retry-After": "900" });
    }
    const body = await req.text();
    if (body.length > 1024) return new Response("Demasiado grande", { status: 413 });
    const params = new URLSearchParams(body);
    const usuario = params.get("usuario") || "";
    const clave = params.get("clave") || "";
    const codigo = params.get("codigo") || "";
    // Siempre se calcula el PBKDF2 (aunque el usuario no exista) para no filtrar por tiempo.
    const pOk = await claveOk(clave, hash);
    let uOk = usuario.length === user.length ? 1 : 0;
    for (let i = 0; i < user.length; i += 1) uOk &= (usuario.charCodeAt(i) === user.charCodeAt(i)) ? 1 : 0;
    const tOk = await totpOk(totp, codigo);
    if (!(uOk && pOk && tOk)) {
      await registrarFallo(ip);
      await espera(700 + Math.floor(Math.random() * 600));   // frena la fuerza bruta
      return htmlAdmin(loginHtml("Datos incorrectos.", Boolean(totp)), 401);
    }
    await limpiarFallos(ip);
    const token = await firmarAsync(user, secret, req);
    return irA("/admin", { "Set-Cookie": `${COOKIE}=${token}; HttpOnly; Path=/; Max-Age=${SESION_SEG}; SameSite=Strict; Secure` });
  }
  if (url.pathname === "/admin/login") {
    if (valid) return irA("/admin");
    return htmlAdmin(loginHtml("", Boolean(totp)));
  }
  if (req.method === "POST" && url.pathname === "/admin/ia") {
    if (!valid) return irA("/admin/login");
    if (!mismoOrigen(req, url)) return new Response("Origen no permitido", { status: 403 });
    const tipo = new URLSearchParams(await req.text()).get("tipo") === "semanal" ? "semanal" : "campanas";
    return htmlAdmin(await paginaIA(user, env, await pedirAnalisis(env, tipo)));
  }
  if (req.method === "POST" && url.pathname === "/admin/control") {
    if (!valid) return irA("/admin/login");
    if (!mismoOrigen(req, url)) return new Response("Origen no permitido", { status: 403 });
    const body = await req.text();
    const params = new URLSearchParams(body);
    const nodo = params.get("nodo") === "JP" ? "JP" : "JE";
    const accion = params.get("accion") === "pausar" ? "pausar" : "reactivar";
    const base = ((nodo === "JE" ? env.NODO_PRINCIPAL : env.NODO_RESPALDO) || "").replace(/\/$/, "");
    try {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), 8000);
      try { await fetch(base + "/api/control?accion=" + accion, { method: "POST", headers: { "x-centinela-control": env.CONTROL_TOKEN || "", "X-Centinela-Gateway": env.GATEWAY_SECRET || "1" }, signal: c.signal }); }
      finally { clearTimeout(t); }
    } catch (e) {}
    // El cortacircuito se actualiza al instante para que el failover se vea sin esperar
    const n = nodos(env).find((x) => x.nombre === nodo);
    if (n) { if (accion === "pausar") await marcarCaido(n); else await marcarVivo(n); }
    return irA("/admin");
  }
  // GET /admin y sus pestañas
  if (!valid) return irA("/admin/login", cookies[COOKIE] ? { "Set-Cookie": borrar } : {});
  if (url.pathname === "/admin/arquitectura") return htmlAdmin(await paginaArquitectura(user, env));
  if (url.pathname === "/admin/seguridad") return htmlAdmin(await paginaSeguridad(user, env));
  if (url.pathname === "/admin/ventas") return htmlAdmin(await paginaVentas(user, env));
  if (url.pathname === "/admin/ia") return htmlAdmin(await paginaIA(user, env, null));
  const d = await datosPanel(env);
  return htmlAdmin(panelHtml(user, d));
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return cors(new Response(null, { status: 204 }));

    const ip = req.headers.get("CF-Connecting-IP") || "0.0.0.0";
    // El panel vive SOLO en el borde (no depende de JE/JP). Ninguna ruta /admin ni /login llega a los nodos,
    // y /api/control solo lo usa el propio gateway (con CONTROL_TOKEN), nunca desde afuera.
    if (url.pathname === "/login") return cors(irA("/admin/login"));
    if (url.pathname === "/admin" || url.pathname.startsWith("/admin/")) {
      const conocida = ["/admin", "/admin/login", "/admin/salir", "/admin/control", ...PESTANAS.map((p) => p[0])].includes(url.pathname);  // incluye /admin/ia (GET y POST)
      if (!conocida || !env.ADMIN_USER || !env.ADMIN_HASH) return cors(json({ error: "No encontrado" }, 404));
      if (limitado("admin:" + ip, 30)) return cors(json({ error: "Demasiadas peticiones. Espera un minuto." }, 429, { "Retry-After": "60" }));
      return cors(await handleAdmin(req, env, url));
    }
    // Rutas que solo usa el propio gateway (con CONTROL_TOKEN): desde afuera no existen.
    if (url.pathname === "/api/control" || url.pathname.startsWith("/api/interno")) return cors(json({ error: "No encontrado" }, 404));
    const esApi = url.pathname.startsWith("/api/") || url.pathname === "/health";

    if (esApi) {
      const esChat = url.pathname.startsWith("/api/chat");
      const cubeta = esChat ? "chat:" : "api:";
      const tope = esChat ? Number(env.LIMITE_CHAT_MIN || 20) : Number(env.LIMITE_MIN || 200);
      if (limitado(cubeta + ip, tope)) {
        return cors(json({ error: "Demasiadas peticiones. Espera un minuto." }, 429,
          { "Retry-After": "60" }));
      }
    }

    if (url.pathname === "/gateway/estado") return cors(json(await estado(env)));
    if (esApi) return cors(await proxy(req, env, url, ctx));
    if (env.ASSETS) return cors(await env.ASSETS.fetch(req));
    return cors(json({ servicio: "Centinela gateway", rutas: ["/api/*", "/health", "/gateway/estado"] }));
  },
};

function nodos(env) {
  return [
    { nombre: "JE", base: (env.NODO_PRINCIPAL || "").replace(/\/$/, "") },
    { nombre: "JP", base: (env.NODO_RESPALDO || "").replace(/\/$/, "") },
  ].filter((n) => n.base);
}

// Toda respuesta de la API de Centinela trae X-Centinela-Nodo (la pone el middleware del nodo)
const esDeCentinela = (r) => !!r.headers.get("x-centinela-nodo");

async function conTimeout(recurso, opciones, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(recurso, { ...opciones, signal: ctrl.signal });
  } finally {
    clearTimeout(t);
  }
}

async function vivo(n, ms = TIMEOUT_MS) {
  const t0 = Date.now();
  try {
    const r = await conTimeout(n.base + "/health", {}, ms);
    if (r.status >= 500) throw new Error("HTTP " + r.status);
    if (!esDeCentinela(r)) throw new Error("HTTP " + r.status + " ajeno");
    const health = await r.json();
    await marcarVivo(n);
    return { nombre: n.nombre, online: true, latencia_ms: Date.now() - t0, health };
  } catch (e) {
    return { nombre: n.nombre, online: false, latencia_ms: Date.now() - t0, error: motivo(e) };
  }
}

async function proxy(req, env, url, ctx) {
  const esLento = url.pathname.startsWith("/api/chat") || url.pathname.startsWith("/api/bot");

  let cuerpo;
  if (!["GET", "HEAD"].includes(req.method)) {
    cuerpo = await req.arrayBuffer();
    if (cuerpo.byteLength > MAX_BODY) {
      return json({ error: "Cuerpo demasiado grande" }, 413);
    }
  }
  const fallas = [];

  // Orden: primero los nodos sanos; los marcados caídos van al final (solo si todo lo demás falla)
  // y se sondean en segundo plano para volver a usarlos apenas revivan.
  const sanos = [], marcados = [];
  for (const n of nodos(env)) {
    if (await estaCaido(n)) {
      marcados.push(n);
      fallas.push(`${n.nombre}:caido`);
      if (ctx) ctx.waitUntil(sondear(n));
    } else sanos.push(n);
  }

  for (const n of [...sanos, ...marcados]) {
    // La IA puede tardar hasta 90 s: antes de mandarle el chat se confirma (rápido) que el nodo vive,
    // salvo que haya respondido bien hace poco.
    if (esLento && Date.now() - (vivosOk.get(n.nombre) || 0) > VIVO_RECIENTE_MS) {
      const v = await vivo(n, TIMEOUT_SALUD_MS);
      if (!v.online) { await marcarCaido(n); fallas.push(`${n.nombre}:${v.error}`); continue; }
    }
    try {
      const h = new Headers(req.headers);
      h.delete("host");
      // El cliente no puede colar su propia "IP" ni el secreto: se borran y los pone el gateway.
      for (const x of ["x-real-ip", "x-forwarded-for", "cf-connecting-ip", "x-centinela-gateway"]) h.delete(x);
      h.set("X-Real-IP", req.headers.get("CF-Connecting-IP") || "");
      h.set("X-Centinela-Gateway", env.GATEWAY_SECRET || "1");   // wrangler secret put GATEWAY_SECRET
      const r = await conTimeout(n.base + url.pathname + url.search,
        { method: req.method, headers: h, body: cuerpo }, esLento ? TIMEOUT_CHAT_MS : TIMEOUT_MS);
      if (r.status >= 500) { await marcarCaido(n); fallas.push(`${n.nombre}:HTTP ${r.status}`); continue; }
      // Cloud Run responde 403/404 él mismo si se le quita el permiso run.invoker (IAM) o se cierra el
      // ingreso: esa respuesta no viene de la API (no trae X-Centinela-Nodo) y cuenta como caída.
      if (!esDeCentinela(r)) { await marcarCaido(n); fallas.push(`${n.nombre}:HTTP ${r.status} ajeno`); continue; }
      await marcarVivo(n);
      const resp = new Response(r.body, r);
      resp.headers.set("X-Centinela-Nodo", n.nombre);
      if (fallas.length) resp.headers.set("X-Centinela-Failover", fallas.join(" | "));
      return resp;
    } catch (e) {
      await marcarCaido(n);
      fallas.push(`${n.nombre}:${motivo(e)}`);
    }
  }
  return json({ error: "Todos los nodos están fuera de línea", detalle: fallas }, 503);
}

async function estado(env) {
  const res = await Promise.all(nodos(env).map((n) => vivo(n, 4000)));
  const activo = res.find((r) => r.online);
  return { activo: activo ? activo.nombre : null, nodos: res, hora: new Date().toISOString() };
}

function motivo(e) {
  return e && e.name === "AbortError" ? "timeout"
    : e && e.message && e.message.startsWith("HTTP") ? e.message : "sin conexión";
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status, headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

function cors(resp) {
  const r = new Response(resp.body, resp);
  r.headers.set("Access-Control-Allow-Origin", "*");
  r.headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  r.headers.set("Access-Control-Allow-Headers", "content-type");
  r.headers.set("Access-Control-Expose-Headers", "X-Centinela-Nodo, X-Centinela-Failover");
  r.headers.set("X-Content-Type-Options", "nosniff");
  r.headers.set("X-Frame-Options", "DENY");
  r.headers.set("Referrer-Policy", "same-origin");
  r.headers.set("Strict-Transport-Security", "max-age=31536000");
  // Ninguna página usa cámara, micrófono, ubicación, pagos, USB ni sensores: quedan apagados.
  // Pantalla completa solo para nuestro propio sitio (la usa la sala 3D).
  r.headers.set("Permissions-Policy", "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), fullscreen=(self)");
  // Ninguna otra pestaña abierta desde aquí puede manipular esta ventana (window.opener).
  r.headers.set("Cross-Origin-Opener-Policy", "same-origin");
  r.headers.set("Content-Security-Policy",
    "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; " +
    "connect-src 'self'; frame-ancestors 'none'");
  return r;
}
