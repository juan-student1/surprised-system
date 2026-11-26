-- =====================================================================
--  CENTINELA · Vistas de BigQuery para Looker Studio (dataset centinela_analitica)
--  Las crea/actualiza: bash nube/12_bigquery.sh vistas   ({{P}} = proyecto, {{D}} = dataset)
--  Crear vistas no cuesta; cada consulta de Looker lee solo KB (muy por debajo de 1 TiB gratis/mes).
--  Cada sentencia termina en ";" y una línea en blanco (el script las separa así).
-- =====================================================================

-- Portada: KPIs de los últimos 30 días y comparación con los 30 anteriores
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_kpis`
OPTIONS (description = "KPIs de portada: últimos 30 días vs. los 30 anteriores (hora Colombia)") AS
WITH h AS (SELECT CURRENT_DATE('America/Bogota') AS hoy),
r AS (
  SELECT
    SUM(IF(fecha > DATE_SUB(hoy, INTERVAL 30 DAY), reportes, 0)) AS reportes_30d,
    SUM(IF(fecha <= DATE_SUB(hoy, INTERVAL 30 DAY) AND fecha > DATE_SUB(hoy, INTERVAL 60 DAY), reportes, 0)) AS reportes_30d_previos,
    SUM(IF(fecha > DATE_SUB(hoy, INTERVAL 30 DAY), numeros_nuevos, 0)) AS numeros_nuevos_30d,
    SUM(IF(fecha > DATE_SUB(hoy, INTERVAL 30 DAY), llamadas_reales, 0)) AS llamadas_reales_30d,
    SAFE_DIVIDE(SUM(IF(fecha > DATE_SUB(hoy, INTERVAL 30 DAY), clasificados_ia, 0)),
                SUM(IF(fecha > DATE_SUB(hoy, INTERVAL 30 DAY), con_descripcion, 0))) AS pct_clasificado_ia_30d,
    SUM(reportes) AS reportes_historicos
  FROM `{{P}}.{{D}}.reportes_diarios`, h),
c AS (SELECT COUNTIF(tipo = 'mantenimiento') AS failovers_demo_30d, COUNTIF(tipo = 'campana') AS campanas_30d
      FROM `{{P}}.{{D}}.cluster`, h WHERE fecha > DATE_SUB(hoy, INTERVAL 30 DAY)),
s AS (SELECT IFNULL(SUM(bloqueos), 0) AS bloqueos_30d FROM `{{P}}.{{D}}.seguridad`, h WHERE fecha > DATE_SUB(hoy, INTERVAL 30 DAY)),
i AS (SELECT IFNULL(SUM(costo_estimado_usd), 0) AS costo_ia_30d_usd FROM `{{P}}.{{D}}.uso_ia`, h WHERE fecha > DATE_SUB(hoy, INTERVAL 30 DAY))
SELECT r.*, SAFE_DIVIDE(r.reportes_30d - r.reportes_30d_previos, r.reportes_30d_previos) AS variacion_reportes,
       c.failovers_demo_30d, c.campanas_30d, s.bloqueos_30d, i.costo_ia_30d_usd
FROM r, c, s, i;

-- Tendencia diaria con promedio móvil de 7 días
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_tendencia_diaria`
OPTIONS (description = "Reportes por día y su promedio móvil de 7 días") AS
SELECT fecha, reportes, numeros_distintos, numeros_nuevos, llamadas_reales,
       ROUND(AVG(reportes) OVER (ORDER BY fecha ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS promedio_7d
FROM `{{P}}.{{D}}.reportes_diarios`;

-- Mapa: por ciudad (fijos colombianos), país (internacionales) y celulares (no geográficos)
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_mapa`
OPTIONS (description = "Reportes de los últimos 30 días por ubicación. pais_iso sirve como campo geográfico País en Looker; ciudad_geo como Ciudad") AS
SELECT
  pais, indicativo, tipo, region,
  IF(tipo = 'fijo', CONCAT(ciudad, ', Colombia'), NULL) AS ciudad_geo,
  CASE
    WHEN indicativo LIKE '+57%' THEN 'CO'
    WHEN indicativo IN ('+1 809', '+1 829', '+1 849') THEN 'DO'
    WHEN indicativo = '+1 876' THEN 'JM'   WHEN indicativo = '+1 268' THEN 'AG'
    WHEN indicativo = '+1 284' THEN 'VG'   WHEN indicativo = '+1 473' THEN 'GD'
    WHEN indicativo = '+1 649' THEN 'TC'   WHEN indicativo = '+1 767' THEN 'DM'
    WHEN indicativo LIKE '+1 %' THEN 'US'
    WHEN indicativo = '+52' THEN 'MX'  WHEN indicativo = '+34' THEN 'ES'  WHEN indicativo = '+44' THEN 'GB'
    WHEN indicativo = '+51' THEN 'PE'  WHEN indicativo = '+58' THEN 'VE'  WHEN indicativo = '+593' THEN 'EC'
    WHEN indicativo = '+591' THEN 'BO' WHEN indicativo = '+56' THEN 'CL'  WHEN indicativo = '+54' THEN 'AR'
    WHEN indicativo = '+55' THEN 'BR'  WHEN indicativo = '+225' THEN 'CI' WHEN indicativo = '+233' THEN 'GH'
    WHEN indicativo = '+234' THEN 'NG' WHEN indicativo = '+216' THEN 'TN' WHEN indicativo = '+232' THEN 'SL'
    WHEN indicativo = '+222' THEN 'MR'
  END AS pais_iso,
  LOGICAL_OR(prefijo_wangiri) AS prefijo_wangiri,
  SUM(reportes) AS reportes, SUM(numeros) AS numeros,
  ROUND(SAFE_DIVIDE(SUM(score_promedio * numeros), SUM(numeros)), 1) AS score_promedio,
  SUM(numeros_alto_riesgo) AS numeros_alto_riesgo
FROM `{{P}}.{{D}}.riesgo_por_prefijo`
WHERE fecha > DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 30 DAY)
GROUP BY pais, indicativo, tipo, region, ciudad_geo, pais_iso;

-- Top números de los últimos 30 días (ENMASCARADOS)
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_top_numeros_30d`
OPTIONS (description = "Números más reportados en 30 días, enmascarados (+57 300 ••• 4567)") AS
SELECT numero_enmascarado, pais,
       ARRAY_AGG(categoria_txt ORDER BY fecha DESC LIMIT 1)[OFFSET(0)] AS categoria,
       SUM(reportes_dia) AS reportes_30d, COUNT(*) AS dias_en_top,
       ARRAY_AGG(score_actual ORDER BY fecha DESC LIMIT 1)[OFFSET(0)] AS riesgo_actual,
       ARRAY_AGG(nivel_actual ORDER BY fecha DESC LIMIT 1)[OFFSET(0)] AS nivel_actual,
       MAX(fecha) AS ultimo_dia
FROM `{{P}}.{{D}}.top_numeros`
WHERE fecha > DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 30 DAY)
GROUP BY numero_enmascarado, pais
ORDER BY reportes_30d DESC
LIMIT 50;

-- Tipos de fraude (30 días) con su participación
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_categorias_30d`
OPTIONS (description = "Reportes por tipo de fraude en 30 días y % del total") AS
SELECT categoria, categoria_txt, SUM(reportes) AS reportes, SUM(clasificados_ia) AS clasificados_ia,
       ROUND(SAFE_DIVIDE(SUM(reportes), SUM(SUM(reportes)) OVER ()), 4) AS participacion
FROM `{{P}}.{{D}}.categorias`
WHERE fecha > DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 30 DAY)
GROUP BY categoria, categoria_txt;

-- Canales (30 días)
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_canales_30d`
OPTIONS (description = "Reportes por canal (web, Telegram, celular) en 30 días") AS
SELECT canal, SUM(reportes) AS reportes,
       ROUND(SAFE_DIVIDE(SUM(reportes), SUM(SUM(reportes)) OVER ()), 4) AS participacion
FROM `{{P}}.{{D}}.canales`
WHERE fecha > DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 30 DAY)
GROUP BY canal;

-- Salud del clúster y failovers por día y nodo
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_salud_cluster`
OPTIONS (description = "Eventos del clúster por día y nodo: arranques, failovers de demostración, sincronizaciones, campañas") AS
SELECT fecha, nodo,
       SUM(IF(tipo = 'arranque', eventos, 0)) AS arranques,
       SUM(IF(tipo = 'mantenimiento', eventos, 0)) AS failovers_demo,
       SUM(IF(tipo = 'reactivado', eventos, 0)) AS reactivaciones,
       SUM(IF(tipo = 'sincronizacion', eventos, 0)) AS sincronizaciones,
       SUM(IF(tipo = 'campana', eventos, 0)) AS campanas,
       SUM(IF(tipo = 'analisis_ia', eventos, 0)) AS analisis_ia,
       SUM(IF(tipo = 'exportacion', eventos, 0)) AS exportaciones,
       SUM(eventos) AS eventos_totales
FROM `{{P}}.{{D}}.cluster`
GROUP BY fecha, nodo;

-- Seguridad: bloqueos por día y código
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_seguridad_diaria`
OPTIONS (description = "Peticiones bloqueadas por día: 401 sin credencial, 403 saltarse el gateway, 429 exceso") AS
SELECT fecha,
       SUM(IF(codigo = 401, bloqueos, 0)) AS sin_credencial_401,
       SUM(IF(codigo = 403, bloqueos, 0)) AS fuera_del_gateway_403,
       SUM(IF(codigo = 429, bloqueos, 0)) AS exceso_429,
       SUM(bloqueos) AS bloqueos
FROM `{{P}}.{{D}}.seguridad`
GROUP BY fecha;

-- IA: uso y costo por día y proveedor
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_ia_diaria`
OPTIONS (description = "Uso de la IA híbrida por día: respuestas reales, desde caché, errores, sin cupo, tokens y costo estimado") AS
SELECT fecha, proveedor,
       SUM(IF(resultado = 'ok', llamadas, 0)) AS respuestas,
       SUM(IF(resultado = 'cache', llamadas, 0)) AS desde_cache,
       SUM(IF(resultado = 'error', llamadas, 0)) AS errores,
       SUM(IF(resultado IN ('sin_cupo', 'apagado'), llamadas, 0)) AS sin_cupo,
       SUM(tokens_entrada) AS tokens_entrada, SUM(tokens_salida) AS tokens_salida,
       SUM(costo_estimado_usd) AS costo_estimado_usd
FROM `{{P}}.{{D}}.uso_ia`
GROUP BY fecha, proveedor;

-- Costos de infraestructura (estimados, mensuales) para la página de costos
CREATE OR REPLACE VIEW `{{P}}.{{D}}.v_costos_infra`
OPTIONS (description = "Costo mensual estimado por recurso (docs/roles/JE_ARQUITECTURA.md §3). Se actualiza a mano") AS
SELECT * FROM UNNEST([
  STRUCT('Cloud SQL (db-f1-micro + 10 GB)' AS recurso, 'Google Cloud' AS proveedor, 10.0 AS usd_mes, 'Base de datos: lo único que cobra en serio' AS nota),
  STRUCT('Cloud Run (JE)', 'Google Cloud', 0.0, 'Nivel gratis'),
  STRUCT('Cloud Scheduler (latido + exportación)', 'Google Cloud', 0.0, '3 trabajos gratis por cuenta de facturación'),
  STRUCT('Secret Manager', 'Google Cloud', 0.6, '~10 secretos activos'),
  STRUCT('Artifact Registry + Cloud Build', 'Google Cloud', 0.2, 'Imágenes de cada despliegue'),
  STRUCT('BigQuery (analítica)', 'Google Cloud', 0.0, 'KB de datos: dentro de 10 GiB y 1 TiB de consultas gratis'),
  STRUCT('Vertex AI Gemini (respaldo)', 'Google Cloud', 0.5, 'Uso real en v_ia_diaria; topes 20/h y 100/día'),
  STRUCT('Cloudflare Workers', 'Cloudflare', 0.0, 'Plan gratis'),
  STRUCT('Tailscale, Telegram, n8n', 'Otros', 0.0, 'Planes gratis / autohospedado')
]);
