"""CENTINELA · análisis profundo a demanda (botón del panel, nunca automático).

- campanas: busca campañas coordinadas en los reportes de las últimas 72 h.
- semanal:  resume la semana para alguien no técnico (comparada con la anterior).

Gemini recibe datos AGREGADOS: conteos, categorías, prefijos y números reportados (que ya son públicos
en la web). Las descripciones van recortadas y con cualquier secuencia de dígitos reemplazada,
para no enviar teléfonos personales ni datos que la víctima haya escrito.
"""
import json, re, threading, time

from .config import CAT_TXT, NODO, log
from .db import q, evento
from .ia import SinIA, ollama_chat, ollama_disponible, registrar_uso, vertex_chat, vertex_puede

TIPOS = ("campanas", "semanal")
_CACHE_SEG = 900                     # el mismo análisis se reutiliza 15 min (recargar el panel no gasta)
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
RE_DIGITOS = re.compile(r"\+?\d[\d\s\-().]{4,}\d")


def anonimizar(texto: str | None, largo: int = 160) -> str:
    t = RE_DIGITOS.sub("[número]", (texto or "").replace("\n", " ")).strip()
    return t[:largo]


def _datos_campanas() -> dict:
    nums = q("""select r.numero, count(*) reportes, count(distinct r.reportero) personas,
                       min(r.creado) primero, max(r.creado) ultimo,
                       mode() within group (order by r.categoria) categoria, n.pais, n.score
                from reportes r join numeros n using (numero)
                where r.creado > now() - interval '72 hours'
                group by r.numero, n.pais, n.score order by personas desc, reportes desc limit 40""", todos=True)
    for f in nums:
        desc = q("""select descripcion from reportes where numero=%s and descripcion is not null
                    and creado > now() - interval '72 hours' order by creado desc limit 3""", (f["numero"],), todos=True)
        f["descripciones"] = [anonimizar(d["descripcion"]) for d in desc]
    prefijos = q("""select left(numero, 6) prefijo, count(*) reportes, count(distinct numero) numeros
                    from reportes where creado > now() - interval '72 hours' and numero like '+%%'
                    group by 1 having count(distinct numero) > 1 order by 2 desc limit 15""", todos=True)
    return {"ventana": "últimas 72 horas", "numeros": nums, "prefijos_repetidos": prefijos}


def _datos_semanal() -> dict:
    def semana(desde: str, hasta: str):
        return q(f"""select count(*) reportes, count(distinct numero) numeros, count(distinct reportero) personas
                     from reportes where creado > now() - interval '{desde}' and creado <= now() - interval '{hasta}'""", uno=True)
    return {
        "esta_semana": semana("7 days", "0 days"),
        "semana_anterior": semana("14 days", "7 days"),
        "por_categoria": q("""select coalesce(categoria,'sin clasificar') categoria, count(*) total from reportes
                              where creado > now() - interval '7 days' group by 1 order by 2 desc""", todos=True),
        "por_canal": q("""select canal, count(*) total from reportes where creado > now() - interval '7 days' group by 1 order by 2 desc""", todos=True),
        "por_dia": q("""select date_trunc('day', creado)::date dia, count(*) total from reportes
                        where creado > now() - interval '7 days' group by 1 order by 1""", todos=True),
        "top_numeros": q("""select numero, pais, score, nivel, total_reportes, categoria_principal from numeros
                            where ultimo_reporte > now() - interval '7 days' and verificado = false
                            order by score desc, total_reportes desc limit 10""", todos=True),
        "campanas_detectadas": q("""select detalle, creado from eventos where tipo='campana'
                                    and creado > now() - interval '7 days' order by creado desc limit 10""", todos=True),
        "llamadas_reales": q("select count(*) total from llamadas where creado > now() - interval '7 days'", uno=True),
    }


PROMPTS = {
    "campanas": ("Eres analista antifraude telefónico en Colombia. Con los DATOS (reportes de la comunidad de las últimas 72 h) "
                 "detecta CAMPAÑAS: varios números o reportes que parecen la misma operación (mismo libreto, misma entidad "
                 "suplantada, prefijos consecutivos, ráfagas en poco tiempo). No inventes números ni cifras que no estén en los datos. "
                 'Responde SOLO JSON: {"campanas": [{"nombre": "...", "numeros": ["+57..."], "patron": "...", '
                 '"evidencia": "...", "riesgo": "alto|medio", "recomendacion": "..."}], "resumen": "2 frases"}. '
                 "Si no hay campañas, devuelve la lista vacía y dilo en el resumen. Español claro, sin tecnicismos."),
    "semanal": ("Eres el analista de Centinela, una red comunitaria anti-estafas telefónicas en Colombia. Con los DATOS escribe el "
                "resumen de la semana para personas NO técnicas (profesor, clientes, comunidad). Compara con la semana anterior, "
                "di qué tipo de fraude creció y da consejos prácticos. Usa solo los datos; no inventes cifras. "
                'Responde SOLO JSON: {"titulo": "...", "resumen": "3-4 frases", "hallazgos": ["..."], "recomendaciones": ["..."]}'),
}


def _llamar(tipo: str, datos: dict) -> tuple[dict, str]:
    system = PROMPTS[tipo]
    usuario = "DATOS:\n" + json.dumps(datos, default=str, ensure_ascii=False)[:24000]
    # Profundo: Gemini primero (más contexto y razonamiento); si no hay cupo o falla, Ollama.
    if vertex_puede(profundo=True):
        try:
            return json.loads(vertex_chat(system, usuario, json_mode=True, temperatura=0.2, max_tokens=4096,
                                          timeout=60, tipo="profundo_" + tipo, profundo=True)), "vertex"
        except (SinIA, ValueError) as e:
            log.warning("Análisis profundo con Vertex falló, intento Ollama: %s", e)
    if ollama_disponible():
        try:
            txt = ollama_chat(system, usuario[:6000], json_mode=True, timeout=110, temperatura=0.2, num_predict=700)
            registrar_uso("ollama", "profundo_" + tipo, "ok")
            return json.loads(txt), "ollama"
        except Exception as e:
            registrar_uso("ollama", "profundo_" + tipo, "error")
            log.warning("Análisis profundo con Ollama falló: %s", e)
    raise SinIA("No hay IA disponible para el análisis profundo")


def analisis_profundo(tipo: str) -> dict:
    if tipo not in TIPOS: raise ValueError("tipo inválido")
    with _lock:
        hit = _cache.get(tipo)
    if hit and time.time() - hit[0] < _CACHE_SEG:
        return {**hit[1], "desde_cache": True}
    datos = _datos_campanas() if tipo == "campanas" else _datos_semanal()
    resultado, fuente = _llamar(tipo, datos)
    salida = {"tipo": tipo, "fuente": fuente, "nodo": NODO, "generado": time.time(), "resultado": resultado,
              "categorias": CAT_TXT, "desde_cache": False}
    with _lock:
        _cache[tipo] = (time.time(), salida)
    evento("analisis_ia", f"Análisis profundo '{tipo}' con {fuente}")
    return salida
