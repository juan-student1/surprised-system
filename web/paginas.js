/* CENTINELA · lógica de las páginas de documentación (Arquitectura · Seguridad · Empresas)
   Sin dependencias y compatible con la CSP estricta (script-src 'self'): tema, menú, índice
   que marca la sección visible y estado en vivo del clúster (solo lectura de /gateway/estado). */
"use strict";

const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => [...raiz.querySelectorAll(s)];

/* ---------- tema claro / oscuro (misma preferencia que la portada) ---------- */
const botonTema = $("#tema-btn");
function pintarTema(t) {
  if (!botonTema) return;
  botonTema.textContent = t === "oscuro" ? "Claro" : "Oscuro";
  botonTema.setAttribute("aria-pressed", String(t === "oscuro"));
}
try {
  const guardado = localStorage.getItem("centinela-tema");
  if (guardado) { document.documentElement.dataset.tema = guardado; pintarTema(guardado); }
} catch { /* sin almacenamiento: tema del sistema */ }
botonTema?.addEventListener("click", () => {
  const siguiente = (document.documentElement.dataset.tema || "auto") === "oscuro" ? "claro" : "oscuro";
  document.documentElement.dataset.tema = siguiente;
  try { localStorage.setItem("centinela-tema", siguiente); } catch { /* opcional */ }
  pintarTema(siguiente);
});

/* ---------- menú del celular: se cierra al elegir un enlace ---------- */
const menu = $("#menu");
menu?.addEventListener("click", (e) => {
  if (e.target.closest("a") && menu.matches(":popover-open")) menu.hidePopover();
});

/* ---------- índice lateral: marca la sección que se está leyendo ---------- */
(() => {
  const enlaces = $$(".doc-indice a[href^='#']");
  if (!enlaces.length || !("IntersectionObserver" in window)) return;
  const porId = new Map(enlaces.map((a) => [a.getAttribute("href").slice(1), a]));
  const visibles = new Set();
  const marcar = () => {
    const primero = $$(".doc-sec").find((s) => visibles.has(s.id));
    enlaces.forEach((a) => a.removeAttribute("aria-current"));
    if (primero && porId.has(primero.id)) porId.get(primero.id).setAttribute("aria-current", "true");
  };
  const io = new IntersectionObserver((entradas) => {
    entradas.forEach((x) => (x.isIntersecting ? visibles.add(x.target.id) : visibles.delete(x.target.id)));
    marcar();
  }, { rootMargin: "-90px 0px -55% 0px" });
  $$(".doc-sec").forEach((s) => s.id && io.observe(s));
})();

/* ---------- estado en vivo del clúster ---------- */
const fmtSeg = (s) => {
  if (s == null) return "—";
  if (s < 90) return `${s} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  if (s < 172800) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} días`;
};
const siNo = (v, si = "Conectada", no = "Sin conexión") => (v === true ? si : v === false ? no : "—");

function pintarNodo(n) {
  const tarjeta = $(`#vivo-${n.nombre}`);
  if (!tarjeta) return;
  const h = n.health || {};
  tarjeta.dataset.estado = n.online ? "ok" : "caido";
  const chip = $(".chip", tarjeta);
  if (chip) { chip.className = "chip " + (n.online ? "ok" : "mal"); chip.textContent = n.online ? "En línea" : "Fuera de línea"; }
  const poner = (campo, valor) => { const el = $(`[data-v="${campo}"]`, tarjeta); if (el) el.textContent = valor; };
  poner("lat", n.online && n.latencia_ms != null ? `${n.latencia_ms} ms` : "—");
  poner("db", siNo(h.db));
  poner("ia", h.ollama === true ? "Ollama (local)" : h.vertex === true ? "Gemini (respaldo)" : h.ollama === false ? "Reglas" : "—");
  poner("ver", h.version ? `v${h.version}` : "—");
  poner("up", fmtSeg(h.uptime_seg));
}

async function estadoCluster() {
  const pulso = $("#pulso"), txt = $("#pulso-txt");
  try {
    const r = await fetch("/gateway/estado", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    const d = await r.json();
    (d.nodos || []).forEach(pintarNodo);
    const activo = (d.nodos || []).find((n) => n.nombre === d.activo);
    if (pulso && txt) {
      pulso.dataset.estado = !d.activo ? "caido" : d.activo === "JE" ? "ok" : "failover";
      txt.textContent = d.activo ? `Atendiendo ${d.activo}${activo?.latencia_ms != null ? ` · ${activo.latencia_ms} ms` : ""}` : "Sin servidores";
    }
    const pie = $("#vivo-hora");
    if (pie) pie.textContent = `Actualizado ${new Date().toLocaleTimeString("es-CO")} · nodo activo: ${d.activo || "ninguno"}`;
  } catch {
    if (pulso && txt) { pulso.dataset.estado = "caido"; txt.textContent = "Sin conexión"; }
  }
}
estadoCluster();
setInterval(() => { if (!document.hidden) estadoCluster(); }, 15000);

/* ---------- cifras públicas de la comunidad (si la página las muestra) ---------- */
(async () => {
  const campos = $$("[data-stat]");
  if (!campos.length) return;
  try {
    const r = await fetch("/api/stats", { cache: "no-store" });
    if (!r.ok) return;
    const s = await r.json();
    campos.forEach((el) => {
      const v = s[el.dataset.stat];
      if (typeof v === "number") el.textContent = v.toLocaleString("es-CO");
    });
  } catch { /* las cifras quedan con su valor por defecto */ }
})();

/* ---------- PWA ---------- */
if ("serviceWorker" in navigator) {
  addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {}));
}
