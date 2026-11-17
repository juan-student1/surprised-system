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
        const sres = await fetch(n.base + "/api/stats", { signal: c.signal });
        if (!sres.ok) throw new Error("down");
        const s = await sres.json();
        const tres = await fetch(n.base + "/api/top?limite=100", { signal: c.signal });
        const tp = tres.ok ? await tres.json() : [];
        return { stats: s, top: Array.isArray(tp) ? tp : [], nodo: n.nombre };
      } finally { clearTimeout(t); }
    } catch (e) {}
  }
  return { stats: null, top: [], nodo: null };
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
  const EXTRA = " .hdr{display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:4px} .top{max-width:1100px;margin:0 auto} table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px} th,td{padding:8px;border-bottom:1px solid #283252;text-align:left} th{color:#9ba5bd} a{color:#7a93ff} .stats{color:#9ba5bd;font-size:14px;margin:0 0 8px} .ctrl{background:#161e33;border:1px solid #283252;border-radius:12px;padding:16px;margin:12px 0 18px} .ctrl-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px} .act{font-size:22px;font-weight:700;color:#7dffa9;margin-top:2px} .lbl{color:#9ba5bd;font-size:12px;text-transform:uppercase;letter-spacing:.04em} .grupo{display:flex;gap:10px;flex-wrap:wrap} .ctrl form{display:inline;margin:0} .ctrl button{width:auto;margin-top:0;padding:10px 14px;font-size:14px} .rojo{background:#cc2539} .verde{background:#1f9d57} .chico{padding:7px 11px;font-size:13px;opacity:.92} .jp{margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center} .jp .lbl{margin-right:4px} .nota{color:#9ba5bd;font-size:13px;margin:12px 0 0} .count{color:#9ba5bd;font-size:12px;margin-top:14px}";
  return "<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content=\"width=device-width, initial-scale=1\"><title>Centinela · Panel</title><style>" + LOGIN_CSS + EXTRA + "</style></head><body><div class=top>"
    + "<div class=hdr><h1>Panel de Centinela</h1><a href=\"/admin/salir\">Salir (" + escHtml(username) + ")</a></div>"
    + "<div class=ctrl><div class=ctrl-top><div><span class=lbl>Atendiendo ahora</span><div class=act>" + escHtml(act) + "</div></div>"
    + "<div class=grupo>" + btn("JE","pausar","rojo","⏸ Detener JE") + btn("JE","reactivar","verde","▶ Reactivar JE") + "</div></div>"
    + "<p class=nota>Detener JE lo deja de atender DE VERDAD (responde 503): el gateway enruta el tráfico a JP (otra máquina, otro internet). Reactívalo para repetir.</p></div>"
    + "<p class=stats>" + linea + " · datos vía " + escHtml(act) + "</p>"
    + "<table><thead><tr><th>Numero</th><th>Pais</th><th>Riesgo</th><th>Nivel</th><th>Reportes</th><th>Tipo</th></tr></thead><tbody>" + filas + "</tbody></table>"
    + "<p class=count>Datos de /api/top y /api/stats (JE/JP), cargados por el gateway. Sin scripts en el navegador — compatible con el blindaje (CSP).</p></div></body></html>";
}

// Respuesta HTML del panel: nunca en caché, no indexable, y sin poder incrustarse.
function htmlAdmin(cuerpo, status = 200, extra = {}) {
  return new Response(cuerpo, { status, headers: { "content-type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", ...extra } });
}
function irA(destino, extra = {}) {
  return new Response("", { status: 303, headers: { Location: destino, "Cache-Control": "no-store", ...extra } });
}
// CSRF: un POST al panel solo vale si viene de esta misma página (además de SameSite=Strict).
function mismoOrigen(req, url) {
  const o = req.headers.get("Origin");
  if (o) return o === url.origin;
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
      try { await fetch(base + "/api/control?accion=" + accion, { method: "POST", headers: { "x-centinela-control": env.CONTROL_TOKEN || "" }, signal: c.signal }); }
      finally { clearTimeout(t); }
    } catch (e) {}
    // El cortacircuito se actualiza al instante para que el failover se vea sin esperar
    const n = nodos(env).find((x) => x.nombre === nodo);
    if (n) { if (accion === "pausar") await marcarCaido(n); else await marcarVivo(n); }
    return irA("/admin");
  }
  // GET /admin
  if (!valid) return irA("/admin/login", cookies[COOKIE] ? { "Set-Cookie": borrar } : {});
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
      const conocida = ["/admin", "/admin/login", "/admin/salir", "/admin/control"].includes(url.pathname);
      if (!conocida || !env.ADMIN_USER || !env.ADMIN_HASH) return cors(json({ error: "No encontrado" }, 404));
      if (limitado("admin:" + ip, 30)) return cors(json({ error: "Demasiadas peticiones. Espera un minuto." }, 429, { "Retry-After": "60" }));
      return cors(await handleAdmin(req, env, url));
    }
    if (url.pathname === "/api/control") return cors(json({ error: "No encontrado" }, 404));
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
      h.set("X-Real-IP", req.headers.get("CF-Connecting-IP") || "");
      h.set("X-Centinela-Gateway", "1");
      const r = await conTimeout(n.base + url.pathname + url.search,
        { method: req.method, headers: h, body: cuerpo }, esLento ? TIMEOUT_CHAT_MS : TIMEOUT_MS);
      if (r.status >= 500) { await marcarCaido(n); fallas.push(`${n.nombre}:HTTP ${r.status}`); continue; }
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
  r.headers.set("Referrer-Policy", "no-referrer");
  r.headers.set("Strict-Transport-Security", "max-age=31536000");
  r.headers.set("Content-Security-Policy",
    "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; " +
    "connect-src 'self'; frame-ancestors 'none'");
  return r;
}
