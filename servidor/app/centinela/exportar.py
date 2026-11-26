"""CENTINELA · exportación diaria a BigQuery (Fase 4 · analítica para Looker Studio).

Cloud Scheduler llama POST /tareas/exportar (OIDC) una vez al día. Se recalculan desde Postgres
los agregados de toda la historia (BQ_HISTORIA_DIAS) y se cargan con *load jobs* (gratis en BigQuery)
con WRITE_TRUNCATE: cada corrida deja las tablas completas e iguales → idempotente, sin "backfill".

Qué NO sale nunca hacia BigQuery: IPs, hashes de reporteros, descripciones de reportes, leads,
dispositivos ni números completos. Los números salen ENMASCARADOS (+57 300 ••• 4567) y el resto
son conteos por día, prefijo, categoría, canal, nodo o proveedor de IA.
"""
import json, time, uuid
from datetime import date

import httpx

from .config import (BQ_PROYECTO, BQ_DATASET, BQ_HISTORIA_DIAS, BQ_UBICACION, CAT_TXT, PAISES,
                     VERTEX_PRECIO_ENTRADA_M, VERTEX_PRECIO_SALIDA_M, log)
from .db import q
from .utilidades import enmascarar, pais_de, prefijo_riesgo

API = "https://bigquery.googleapis.com/bigquery/v2"
UPLOAD = "https://bigquery.googleapis.com/upload/bigquery/v2"
DIA = "(creado at time zone 'America/Bogota')::date"

# Fijos de Colombia por indicativo regional (plan de numeración de la CRC, 2021). Ciudad de referencia
# para el mapa de Looker Studio; los celulares (3xx) no son geográficos.
REGIONES_CO = {
    "601": ("Bogotá", "Bogotá y Cundinamarca"),
    "602": ("Cali", "Valle, Cauca y Nariño"),
    "604": ("Medellín", "Antioquia, Córdoba y Chocó"),
    "605": ("Barranquilla", "Costa Caribe"),
    "606": ("Pereira", "Eje Cafetero"),
    "607": ("Bucaramanga", "Santanderes y Arauca"),
    "608": ("Ibagué", "Centro y Llanos (Tolima, Huila, Meta, Boyacá…)"),
}

S, I, F, D, B = "STRING", "INTEGER", "FLOAT", "DATE", "BOOLEAN"
TABLAS = {
    "reportes_diarios": [("fecha", D), ("reportes", I), ("numeros_distintos", I), ("personas_distintas", I),
                         ("numeros_nuevos", I), ("con_descripcion", I), ("clasificados_ia", I), ("llamadas_reales", I)],
    "riesgo_por_prefijo": [("fecha", D), ("pais", S), ("indicativo", S), ("tipo", S), ("ciudad", S), ("region", S),
                           ("prefijo_wangiri", B), ("reportes", I), ("numeros", I), ("score_promedio", F),
                           ("numeros_alto_riesgo", I)],
    "categorias": [("fecha", D), ("categoria", S), ("categoria_txt", S), ("reportes", I), ("clasificados_ia", I)],
    "canales": [("fecha", D), ("canal", S), ("reportes", I)],
    "cluster": [("fecha", D), ("nodo", S), ("tipo", S), ("eventos", I)],
    "seguridad": [("fecha", D), ("nodo", S), ("codigo", I), ("ruta", S), ("bloqueos", I)],
    "uso_ia": [("fecha", D), ("nodo", S), ("proveedor", S), ("tipo", S), ("resultado", S), ("llamadas", I),
               ("tokens_entrada", I), ("tokens_salida", I), ("costo_estimado_usd", F)],
    "top_numeros": [("fecha", D), ("posicion", I), ("numero_enmascarado", S), ("pais", S), ("categoria_txt", S),
                    ("reportes_dia", I), ("score_actual", I), ("nivel_actual", S)],
}
DESCRIPCIONES = {
    "reportes_diarios": "Reportes por día (hora Colombia). Sin datos personales.",
    "riesgo_por_prefijo": "Reportes por indicativo/región/país. Celulares colombianos agrupados por los 3 primeros dígitos.",
    "categorias": "Reportes por tipo de fraude y día.",
    "canales": "Reportes por canal (web, Telegram, celular) y día.",
    "cluster": "Eventos del clúster por día y nodo (arranques, mantenimiento = demo de failover, sincronizaciones, campañas).",
    "seguridad": "Peticiones bloqueadas (401/403/429) por día, nodo y grupo de ruta.",
    "uso_ia": "Uso de la IA híbrida (Ollama / Vertex Gemini) por día, con costo estimado.",
    "top_numeros": "Los 20 números más reportados de cada día, ENMASCARADOS.",
}


# ---------------- clasificación de números (sin salir del nodo) ----------------
def clasificar_numero(numero: str) -> dict:
    """Agrupa un número en un indicativo/región que se puede mostrar en un mapa sin identificarlo."""
    if not numero.startswith("+"):
        return {"pais": "Código corto", "indicativo": "corto", "tipo": "corto", "ciudad": None, "region": None}
    if numero.startswith("+57"):
        resto = numero[3:]
        if len(resto) == 10 and resto.startswith("60") and resto[:3] in REGIONES_CO:
            ciudad, region = REGIONES_CO[resto[:3]]
            return {"pais": "Colombia", "indicativo": "+57 " + resto[:3], "tipo": "fijo", "ciudad": ciudad, "region": region}
        if len(resto) == 10 and resto.startswith("3"):
            return {"pais": "Colombia", "indicativo": "+57 " + resto[:3], "tipo": "celular", "ciudad": None,
                    "region": "Celular (no geográfico)"}
        return {"pais": "Colombia", "indicativo": "+57 otro", "tipo": "otro", "ciudad": None, "region": None}
    pref = next((p for p in sorted(PAISES, key=len, reverse=True) if numero.startswith(p)), numero[:4])
    if pref == "+1": pref = "+1 " + numero[2:5]   # +1 809, +1 876…: separa el Caribe (wangiri) de EE. UU.
    return {"pais": pais_de(numero), "indicativo": pref, "tipo": "internacional", "ciudad": None, "region": None}


# ---------------- filas de cada tabla ----------------
def _desde() -> str:
    return f"now() - make_interval(days => {int(BQ_HISTORIA_DIAS)})"

def filas_reportes_diarios() -> list[dict]:
    base = {str(f["fecha"]): dict(f) for f in q(f"""
        select {DIA} fecha, count(*) reportes, count(distinct numero) numeros_distintos,
               count(distinct reportero) personas_distintas, count(descripcion) con_descripcion,
               count(*) filter (where clasificado_por = 'ia') clasificados_ia
        from reportes where creado > {_desde()} group by 1""", todos=True)}
    for f in q(f"""select (primer_reporte at time zone 'America/Bogota')::date fecha, count(*) n from numeros
                   where primer_reporte > {_desde()} group by 1""", todos=True):
        base.setdefault(str(f["fecha"]), {"fecha": f["fecha"]})["numeros_nuevos"] = f["n"]
    try:
        for f in q(f"select {DIA} fecha, count(*) n from llamadas where creado > {_desde()} group by 1", todos=True):
            base.setdefault(str(f["fecha"]), {"fecha": f["fecha"]})["llamadas_reales"] = f["n"]
    except Exception as e: log.warning("Exportar: sin llamadas (%s)", e)
    cols = [c for c, _ in TABLAS["reportes_diarios"]]
    return [{c: (r.get(c) if c == "fecha" else int(r.get(c) or 0)) for c in cols} for r in base.values()]

def filas_riesgo_por_prefijo() -> list[dict]:
    grupos: dict[tuple, dict] = {}
    for f in q(f"""select {DIA} fecha, r.numero, count(*) reportes, max(n.score) score, max(n.nivel) nivel
                   from reportes r join numeros n using (numero) where r.creado > {_desde()} group by 1, 2""", todos=True):
        c = clasificar_numero(f["numero"])
        g = grupos.setdefault((str(f["fecha"]), c["indicativo"]), {"fecha": f["fecha"], **c,
                              "prefijo_wangiri": False, "reportes": 0, "numeros": 0, "_scores": [], "numeros_alto_riesgo": 0})
        g["reportes"] += f["reportes"]; g["numeros"] += 1; g["_scores"].append(f["score"] or 0)
        g["numeros_alto_riesgo"] += f["nivel"] == "alto"
        g["prefijo_wangiri"] = g["prefijo_wangiri"] or prefijo_riesgo(f["numero"])
    salida = []
    for g in grupos.values():
        sc = g.pop("_scores"); g["score_promedio"] = round(sum(sc) / len(sc), 1); salida.append(g)
    return salida

def filas_categorias() -> list[dict]:
    return [{"fecha": f["fecha"], "categoria": f["categoria"], "categoria_txt": CAT_TXT.get(f["categoria"], "Sin clasificar"),
             "reportes": f["reportes"], "clasificados_ia": f["ia"]}
            for f in q(f"""select {DIA} fecha, coalesce(categoria, 'sin_clasificar') categoria, count(*) reportes,
                                  count(*) filter (where clasificado_por = 'ia') ia
                           from reportes where creado > {_desde()} group by 1, 2""", todos=True)]

def filas_canales() -> list[dict]:
    return [dict(f) for f in q(f"select {DIA} fecha, canal, count(*) reportes from reportes where creado > {_desde()} group by 1, 2", todos=True)]

def filas_cluster() -> list[dict]:
    return [dict(f) for f in q(f"""select {DIA} fecha, nodo, tipo, count(*) eventos from eventos
                                   where creado > {_desde()} and nodo is not null group by 1, 2, 3""", todos=True)]

def filas_seguridad() -> list[dict]:
    return [dict(f) for f in q(f"""select (hora at time zone 'America/Bogota')::date fecha, nodo, codigo, ruta, sum(total)::int bloqueos
                                   from seguridad_hora where hora > {_desde()} group by 1, 2, 3, 4""", todos=True)]

def filas_uso_ia() -> list[dict]:
    salida = []
    for f in q(f"""select (hora at time zone 'America/Bogota')::date fecha, nodo, proveedor, tipo, resultado,
                          sum(llamadas)::int llamadas, sum(tokens_entrada)::bigint tokens_entrada, sum(tokens_salida)::bigint tokens_salida
                   from ia_uso_hora where hora > {_desde()} group by 1, 2, 3, 4, 5""", todos=True):
        f = dict(f)
        precio = f["proveedor"] == "vertex" and (VERTEX_PRECIO_ENTRADA_M or VERTEX_PRECIO_SALIDA_M)
        f["costo_estimado_usd"] = round((f["tokens_entrada"] * VERTEX_PRECIO_ENTRADA_M + f["tokens_salida"] * VERTEX_PRECIO_SALIDA_M) / 1e6, 6) if precio else (0.0 if f["proveedor"] == "ollama" else None)
        salida.append(f)
    return salida

def filas_top_numeros() -> list[dict]:
    filas = q(f"""select * from (
                    select {DIA} fecha, r.numero, count(*) reportes_dia, max(n.score) score_actual, max(n.nivel) nivel_actual,
                           max(n.categoria_principal) categoria, row_number() over (partition by {DIA} order by count(*) desc, max(n.score) desc) posicion
                    from reportes r join numeros n using (numero) where r.creado > {_desde()} and not n.verificado group by 1, 2) t
                  where posicion <= 20""", todos=True)
    return [{"fecha": f["fecha"], "posicion": f["posicion"], "numero_enmascarado": enmascarar(f["numero"]), "pais": pais_de(f["numero"]),
             "categoria_txt": CAT_TXT.get(f["categoria"], "Sin clasificar"), "reportes_dia": f["reportes_dia"],
             "score_actual": f["score_actual"], "nivel_actual": f["nivel_actual"]} for f in filas]

GENERADORES = {
    "reportes_diarios": filas_reportes_diarios, "riesgo_por_prefijo": filas_riesgo_por_prefijo,
    "categorias": filas_categorias, "canales": filas_canales, "cluster": filas_cluster,
    "seguridad": filas_seguridad, "uso_ia": filas_uso_ia, "top_numeros": filas_top_numeros,
}


# ---------------- BigQuery (REST, sin librerías extra) ----------------
def _schema(tabla: str) -> dict:
    return {"fields": [{"name": n, "type": t, "mode": "REQUIRED" if n == "fecha" else "NULLABLE"} for n, t in TABLAS[tabla]]}

def ndjson(filas: list[dict]) -> bytes:
    return "\n".join(json.dumps(f, default=str, ensure_ascii=False) for f in filas).encode()

def cuerpo_multipart(tabla: str, datos: bytes) -> tuple[bytes, str]:
    frontera = "centinela" + uuid.uuid4().hex
    config = {"jobReference": {"projectId": BQ_PROYECTO, "location": BQ_UBICACION},
              "configuration": {"load": {
                  "destinationTable": {"projectId": BQ_PROYECTO, "datasetId": BQ_DATASET, "tableId": tabla},
                  "sourceFormat": "NEWLINE_DELIMITED_JSON", "writeDisposition": "WRITE_TRUNCATE",
                  "createDisposition": "CREATE_IF_NEEDED", "schema": _schema(tabla),
                  "timePartitioning": {"type": "DAY", "field": "fecha"},
                  "destinationTableProperties": {"description": DESCRIPCIONES[tabla]}}}}
    cuerpo = (f"--{frontera}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(config)}\r\n"
              f"--{frontera}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + datos + f"\r\n--{frontera}--\r\n".encode()
    return cuerpo, f"multipart/related; boundary={frontera}"

def _crear_tabla(h: dict, tabla: str):
    """Crea la tabla vacía (si no existe) para que las vistas de Looker siempre encuentren todas."""
    r = httpx.post(f"{API}/projects/{BQ_PROYECTO}/datasets/{BQ_DATASET}/tables", headers=h, timeout=30, json={
        "tableReference": {"projectId": BQ_PROYECTO, "datasetId": BQ_DATASET, "tableId": tabla},
        "schema": _schema(tabla), "timePartitioning": {"type": "DAY", "field": "fecha"}, "description": DESCRIPCIONES[tabla]})
    if r.status_code not in (200, 409): r.raise_for_status()

def exportar() -> dict:
    from .gcp import token
    if not BQ_PROYECTO: raise RuntimeError("BQ_PROYECTO no configurado")
    h = {"Authorization": f"Bearer {token()}"}
    t0, trabajos, resumen = time.time(), {}, {}
    for tabla, gen in GENERADORES.items():
        try: filas = gen()
        except Exception as e:
            log.warning("Exportar %s: sin datos (%s)", tabla, e); resumen[tabla] = {"filas": 0, "estado": "sin_fuente"}; continue
        try:
            _crear_tabla(h, tabla)
            if not filas: resumen[tabla] = {"filas": 0, "estado": "vacia"}; continue
            cuerpo, tipo = cuerpo_multipart(tabla, ndjson(filas))
            r = httpx.post(f"{UPLOAD}/projects/{BQ_PROYECTO}/jobs?uploadType=multipart", content=cuerpo,
                           headers={**h, "Content-Type": tipo}, timeout=60)
            r.raise_for_status()
            trabajos[tabla] = r.json()["jobReference"]["jobId"]; resumen[tabla] = {"filas": len(filas), "estado": "cargando"}
        except Exception as e:
            log.warning("Exportar %s falló: %s", tabla, str(e)[:300]); resumen[tabla] = {"filas": len(filas), "estado": "error"}
    # Esperar a que terminen los load jobs (normalmente segundos)
    limite = time.time() + 60
    while trabajos and time.time() < limite:
        for tabla, job in list(trabajos.items()):
            try:
                st = httpx.get(f"{API}/projects/{BQ_PROYECTO}/jobs/{job}?location={BQ_UBICACION}", headers=h, timeout=20).json().get("status", {})
            except Exception: continue
            if st.get("state") == "DONE":
                resumen[tabla]["estado"] = "error" if st.get("errorResult") else "ok"
                if st.get("errorResult"): log.warning("Load %s: %s", tabla, st["errorResult"])
                trabajos.pop(tabla)
        if trabajos: time.sleep(1.5)
    for tabla in trabajos: resumen[tabla]["estado"] = "sin_confirmar"
    ok = all(v["estado"] in ("ok", "vacia") for v in resumen.values())
    return {"ok": ok, "dataset": BQ_DATASET, "tablas": resumen, "segundos": round(time.time() - t0, 1), "dia": str(date.today())}


def resumen_por_tabla(res: dict) -> str:
    return ", ".join(f"{t}={v['filas']}({v['estado']})" for t, v in res["tablas"].items())

