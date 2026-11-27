# JM · Ventas de Centinela

> Responsable: **JM**. Interfaces: sección **Para empresas** de la web (`/#empresas`, formulario que guarda leads en la BD) y pestaña **Ventas** del panel (`/admin/ventas`).
> Página pública del rol: **Empresas** (https://centinela.juan-gallego-sec.workers.dev/empresas), versión para clientes y jurado de este documento (sin detalles internos ni explotables).
> Las cifras de mercado tienen su fuente al final; los precios son **hipótesis de piloto** para validar con clientes, no una tarifa publicada. Última revisión: 2026‑11‑25.

## 1. El problema
- En Colombia contestar un número desconocido es una apuesta: **falso banco** que pide el código del SMS, **wangiri** (llamada perdida internacional para que la devuelvas a tarifa premium), extorsión, cobranza y telemarketing no pedido.
- El 71 % de los colombianos recibió al menos un intento de fraude en el último año, y entre ellos el 46 % dice que al menos uno se concretó (DataCrédito Experian, 2026) [4]. La Policía registró 13.600 denuncias de fraude telefónico en 2024, 18 % más que en 2023 [3], y el vishing (fraude por voz) es el canal donde más personas pierden dinero según TransUnion [3].
- **Cada víctima lo sufre sola:** lo que aprende una persona no protege a la siguiente. Los bancos y cooperativas se enteran tarde de que los están suplantando.

## 2. La solución
Centinela convierte cada reporte en protección para todos: **puntaje de riesgo 0‑100** calculado por **personas distintas** que reportan, detección de **campañas** (3 personas en 15 min = alerta), IA que clasifica el tipo de fraude, y aviso **antes de contestar** por web, Telegram y app Android. Para empresas: **API con llave** y panel de campañas contra su marca.

## 3. Mercado en Colombia

| Dato | Cifra | Fuente |
|---|---|---|
| Líneas móviles activas | 92,5 millones (1T 2025), penetración 174 % | MinTIC [1] |
| Intentos de fraude | 71 % de los colombianos recibió al menos uno en el último año; el 46 % de ellos sufrió al menos una estafa | DataCrédito Experian, 2026 [4] |
| Denuncias de fraude telefónico | 13.600 en 2024 (+18 %) | Policía Nacional, vía prensa [3] |
| Industria BPO / contact center | ~750.000‑790.000 empleos formales, ~3 % del PIB | BPrO, Bancolombia [5][6] |
| Cooperativas de ahorro y crédito | 172 entidades, > 4,4 millones de asociados (cierre 2024) | Fecolfin vía La República [7] |

**Tamaño (hipótesis para validar):**
- **TAM** (todas las líneas móviles protegidas): ~92 M líneas.
- **SAM** (organizaciones que pagan por proteger a sus clientes o su operación): 172 cooperativas de ahorro y crédito + bancos pequeños y fintech + empresas de contact center.
- **SOM año 1** (meta del piloto): **10 cooperativas** en plan Empresa + **500 usuarios Pro** ≈ 10 × 790.000 × 12 + 500 × 14.900 × 12 ≈ **184 M COP/año**.

## 4. Clientes objetivo

| Segmento | Dolor | Qué compra | Quién decide |
|---|---|---|---|
| **Personas** | Miedo a contestar; ya cayeron o casi | Gratis → **Pro** (aviso al entrar la llamada) | La persona (o el hijo que configura el celular de los papás) |
| **Cooperativas y bancos pequeños** | Suplantan su marca para robar a sus asociados; no tienen un equipo antifraude grande | **Empresa**: alertas de campañas contra su marca, consulta por API en su app, reporte mensual | Gerente de riesgo / oficial de cumplimiento (SARLAFT/SARO) |
| **Call centers y BPO** | Sus líneas salientes terminan marcadas como spam; necesitan reputación de números | **Empresa**: API de reputación antes de marcar y monitoreo de sus propios números | Gerente de operaciones / calidad |
| **Operadores** | Campañas de wangiri y spoofing en su red; presión regulatoria de la CRC | **Empresa** a la medida: feed de campañas en tiempo real | Fraude / regulatorio |

## 5. Propuesta de valor
> **"Centinela te dice quién te llama y si debes contestar, con lo que ya sabe toda la comunidad, antes de que levantes el teléfono."**

Para empresas: **"Sepan que están suplantando su marca en minutos, no en semanas."**

Diferenciales:
1. **Local:** prefijos, modalidades y lenguaje de Colombia (falso Bancolombia, Nequi, DIAN, "su familiar está detenido").
2. **Comunidad + campañas en tiempo real:** el riesgo sube con personas distintas, no con un solo reporte; las campañas se detectan en 15 minutos.
3. **Privacidad por diseño:** IA local (los reportes no salen a un proveedor de IA), reporteros anónimos con hash, números enmascarados al público, Ley 1581.
4. **Siempre arriba:** dos servidores en redes distintas con failover automático (< 1 s); si la BD falla, el reporte no se pierde.

## 6. Planes

| | **Gratis** | **Pro** | **Empresa** |
|---|---|---|---|
| Precio (piloto) | $0 | **$14.900 COP/mes** | **desde $790.000 COP/mes** |
| Consulta web y Telegram | ✅ | ✅ | ✅ |
| Reportes y alertas de campañas | ✅ | ✅ | ✅ |
| App Android (aviso al entrar la llamada) | — | ✅ | ✅ (para sus asociados) |
| Alertas privadas por Telegram | — | ✅ | ✅ |
| **API con llave propia** (consulta + reporte) | — | — | ✅ (hasta 100.000 consultas/mes) |
| Panel de campañas contra su marca | — | — | ✅ |
| Soporte y acuerdo de servicio | — | — | ✅ |

**Cómo se llega a esos precios:** Pro por debajo del costo de un plan de datos pequeño (decisión de impulso, se paga con Nequi/Daviplata). Empresa: el valor de **evitar un solo fraude** a un asociado suele superar la mensualidad; incluye el costo de nube por cliente (< 5 % del precio).

**Estado técnico de la API con llave:** hoy la API pública no usa llaves (se limita por IP). La llave por empresa (tabla de llaves con hash, cuota mensual, límite por llave) es el siguiente desarrollo cuando haya un cliente piloto; la landing lo dice ("en piloto").

## 7. Competencia

| Alternativa | Fortaleza | Debilidad frente a Centinela |
|---|---|---|
| Truecaller / Hiya | Base mundial enorme, identificador de nombre | Genérico, poco foco en modalidades locales; modelo basado en datos de contactos; sin servicio a cooperativas |
| Filtro de spam del teléfono (Google, Samsung) | Viene instalado, gratis | Caja negra: no explica por qué ni deja reportar el tipo de fraude; nada para empresas |
| Listas negras internas de bancos | Datos propios | Cada entidad sola; no ven lo que reportan los clientes de otras |
| Medidas de operadores y CRC | Escala de red | Lentas; no avisan al usuario en el momento ni explican el riesgo |

**Nuestra cuña:** cooperativas y bancos pequeños: nadie les vende antifraude telefónico a su medida y su regulación (SARO) les exige gestionar el riesgo de fraude.

## 8. One‑pager (para enviar o imprimir)

> **CENTINELA · Antes de contestar, sabe quién te llama**
>
> **Problema:** 7 de cada 10 colombianos recibieron un intento de fraude en 2025 y el fraude por llamada es el que más dinero cuesta. Las víctimas aprenden solas y tarde.
>
> **Solución:** una red comunitaria que califica cada número de 0 a 100 según cuántas personas distintas lo reportan, detecta campañas en 15 minutos y avisa antes de contestar (web, Telegram, Android).
>
> **Para su cooperativa o banco:** alertas cuando suplantan su marca, consulta por API desde su app y reporte mensual de campañas. Piloto desde **$790.000 COP/mes**.
>
> **Por qué confiar:** dos servidores con failover automático, base de datos en Google Cloud con acceso solo por identidad, IA privada que no envía los reportes a terceros, auditoría de seguridad propia (OWASP API Top 10), datos personales bajo la Ley 1581.
>
> **Contacto:** formulario en https://centinela.juan-gallego-sec.workers.dev/#empresas

## 9. Guion de demo comercial (5 minutos)

| Min | Qué se hace | Qué se dice |
|---|---|---|
| 0:00 | Abrir la web en el celular | "¿Cuántos de ustedes contestaron esta semana un número que no conocían?" |
| 0:30 | Consultar un número reportado como falso banco | "Rojo, 83/100: cinco personas distintas lo reportaron como suplantación. Esto lo ve cualquiera, gratis." |
| 1:30 | Reportar una llamada con descripción ("dijeron que eran de mi cooperativa y pidieron el código") | "La IA lo clasificó sola como suplantación. Si 3 personas lo reportan en 15 minutos, salta una alerta de campaña." |
| 2:30 | Telegram: escribirle el número al bot | "Su asociado no necesita instalar nada: le escribe al bot." |
| 3:15 | Panel → **Ventas** (el lead que entró por el formulario) y explicar el plan Empresa | "Así llegan ustedes: dejan sus datos y en un día hábil los contactamos. Para su cooperativa: API, alertas contra su marca y reporte mensual." |
| 4:15 | Panel → **Detener JE** y volver a consultar | "Aunque se caiga un servidor, sigue funcionando. Esto es lo que compran: que no se caiga." |
| 4:45 | Cierre | "Piloto de 1 mes sin costo para 3 cooperativas. ¿Agendamos la de ustedes?" |

## 10. Siguientes pasos de JM
1. Revisar los leads cada semana en el panel → Ventas y marcar el estado (por ahora en la BD; luego botón en el panel).
2. Validar precios con 5 entrevistas (2 cooperativas, 2 call centers, 1 persona mayor y su familia).
3. Preparar la versión en PDF del one‑pager para la sustentación.

## Fuentes
1. MinTIC, *Colombia cerró el primer trimestre de 2025 con más de 49 millones de accesos móviles a Internet* (incluye 92,5 M de líneas): https://mintic.gov.co/portal/inicio/Sala-de-prensa/Noticias/404518:Colombia-cerro-el-primer-trimestre-de-2025-con-mas-de-49-millones-de-accesos-moviles-a-Internet
2. Portafolio, *Internet móvil en Colombia crece a 49,1 millones de accesos*: https://www.portafolio.co/tecnologia/negocios-empresas-internet-movil-en-colombia-crece-a-49-1-millones-de-accesos-en-el-primer-trimestre-637043
3. El País Cali, *Cibercrimen en Colombia cierra 2025 con 13 mil casos*: https://www.elpais.com.co/colombia/cibercrimen-en-colombia-cierra-2025-con-13-mil-casos-alerta-por-modalidades-de-fraude-3146.html · La República, *Las estafas por correo, internet y llamadas cayeron 74 % en 2025* (TransUnion): https://www.larepublica.co/finanzas/las-estafas-por-correo-internet-y-llamadas-cayeron-74-en-2025-hasta-llegar-a-2-3-4402402
4. DataCrédito Experian, estudio *Del fraude digital a la confianza digital* (septiembre de 2026), reportado en La República: https://www.larepublica.co/finanzas/estudio-de-datacredito-experian-revelo-que-intento-de-fraude-llego-a-71-de-las-personas-en-el-ultimo-ano-4474135 y en Portafolio: https://www.portafolio.co/economia/finanzas/el-71-de-colombianos-enfrento-intentos-de-fraude-durante-el-ultimo-ano-y-46-reporto-una-estafa-consumada-501838 (verificado 2026‑11‑26). El 46 % es sobre los expuestos, no sobre todos los colombianos.
5. Noticias RCN, *El BPO en Colombia: más de 750 mil empleos*: https://www.noticiasrcn.com/economia/call-center-bpo-tiene-mas-de-750-mil-empleos-en-colombia-891279
6. Bancolombia, *Actualidad del sector de contact centers en Colombia: 3 % del PIB*: https://www.bancolombia.com/empresas/capital-inteligente/actualidad-economica-sectorial/evolucion-bpo-colombia
7. La República, *Cifras del sistema financiero cooperativo 2024*: https://www.larepublica.co/finanzas/cifras-sistema-financiero-cooperativo-2024-4085157

> Nota de método: las cifras de fraude varían mucho entre fuentes (denuncias formales vs. encuestas vs. datos de empresas privadas). En la sustentación se citan **con su fuente** y como orden de magnitud.
