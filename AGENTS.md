# Datos Pauta Oficial: guía para agentes de IA

Sitio público y neutral (https://datospautaoficial.com.ar) que unifica la publicidad
oficial argentina: ~571 mil órdenes de Nación, CABA, PBA y Santa Fe (2003-2025), con
montos deflactados. Postura estrictamente informativa: sin denuncia ni opinión.
Proyecto muy sensible: un número mal cargado se publica como dato oficial.

## Reglas de trabajo (no negociables)

1. **No cambiar datos publicados sin OK explícito del usuario.** Esto incluye
   `etl/data/pauta_oficial_unificado_v2.csv`, la base y `public/data/home.json`.
   Pedir OK solo para un sí/no real: aplicar un parche, re-ejecutar el ETL o
   descargar archivos. No preguntar decisiones de formato: elegir la opción que deja
   el dato como está hoy y decirlo.
2. **Toda corrección de datos se verifica contra la fuente oficial vigente** y
   concilia al centavo con su total oficial. Antes de cambiar algo, buscar la causa
   raíz con los "5 porqués"; las sospechas sin evidencia no se aplican.
3. **Push a `main` = deploy a producción.** No hacer push sin pedido.
4. **Explicarle al usuario en lenguaje simple**: qué cambió en la web y por qué. Nada
   de hashes, rutas ni jerga.
5. **Decisiones ya tomadas por el usuario**:
   - mantener los textos de metodología ("dato crudo", deflactación con IPC);
   - la etiqueta "Gestión" muestra una sola gestión por año, la que tomaba
     `ORDER BY date_from DESC`.

## Arquitectura

```
Fuentes oficiales (CSV / XLSX / PDF por jurisdicción)
  → etl/extractores/extract_{caba,nacion,pba,santa_fe}.py   (comun.py: montos, fechas)
  → etl/unificar.py → etl/data/pauta_oficial_unificado_v2.csv  (CSV canónico, versionado)
  → etl/validar.py  (solo informa: atípicos, totales de pivot duplicados)
  → etl/build_db.py → etl/build/pauta.sqlite + public/data/{config,home,search,grupos}.json
  → etl/upload_r2.mjs → Cloudflare R2 (db.datospautaoficial.com.ar/v/<version>/pauta.sqlite.0)
  → Astro + React islands (src/) consultan la SQLite desde el navegador con sql.js-httpvfs
  → Cloudflare Pages
```

En el deploy de Cloudflare **solo corre `build_db.py` sobre el CSV**: los
extractores no corren. Los datos cambian únicamente si cambia el CSV versionado.

## Mapa del repo

| Ruta | Qué es |
|---|---|
| `etl/extractores/` | Un extractor por jurisdicción. `comun.py`: `normalizar_monto`, el separador decimal por columna y `leer_xlsx`. |
| `etl/unificar.py` | Corre los extractores y escribe el CSV unificado (8 columnas + `archivo_origen`). |
| `etl/build_db.py` | Normaliza nombres (`aliases.csv`), deflacta (`ipc_indec.csv`), crea `orders` y las caches, `home.json`, `search.json`, `grupos.json` y la copia publicable. |
| `etl/check_build.py` | Valida config, tamaños y límites de Pages antes del deploy. |
| `etl/upload_r2.mjs` | Sube la versión de la base a R2 si falta (`--dry-run` para probar). |
| `etl/R2_SETUP.md` | Configuración de R2, versionado y migración. |
| `etl/PROMPT_EJECUCION.md` | Cómo re-ejecutar el ETL completo con los crudos. |
| `etl/tests/` | Tests del ETL (`python -m unittest discover -s etl/tests`). |
| `src/lib/queries.ts` | Todas las consultas SQL del front. |
| `src/lib/db.ts` | Singleton del worker de sql.js-httpvfs. |
| `src/lib/search.ts` | `search.json`: búsqueda (MiniSearch) y clave → nombre de display. |
| `src/lib/url-state.ts` | Estado de filtros en la URL; `JURISDICCIONES` es la lista única. |
| `src/components/DataTable.tsx` | Tabla (modo agrupado y modo individual), filtros y "Gestión". |
| `src/components/Generador.tsx` | "Cuánto recibió" e imagen para compartir. |
| `src/components/Rankings.tsx` | Rankings contextual y global. |
| `src/pages/index.astro` | Portada: hero, cobertura, scripts inline. |
| `src/pages/metodologia.astro` | Metodología pública. |
| `src/pages/contacto.astro` | Formulario de contacto (envía a `/api/contacto`). |
| `functions/api/contacto.js` | Pages Function: pasa el formulario al Worker por el service binding `CONTACTO`. |
| `workers/contacto/` | Worker `datospautaoficial-contacto`: valida y reenvía el mensaje por Email Routing. |

## Comandos

```bash
npm run dev                                  # dev server (http://localhost:4321)
npx tsc --noEmit                             # typecheck
npm run build                                # build estático en dist/
python -m unittest discover -s etl/tests     # tests del ETL
python etl/validar.py                        # reporte REPORTE_VALIDACION.md
python etl/build_db.py                       # reconstruye la base (local: urlPrefix /data/)
python etl/check_build.py                    # chequeos previos al deploy
node etl/upload_r2.mjs --dry-run             # simula la subida (requiere R2_BUCKET y R2_PUBLIC_URL)
```

## Invariantes y trampas (leer antes de tocar código)

- **`orders.id` es el número de fila (1-based) del CSV unificado.** Quitar, agregar
  o reordenar filas cambia los `#id` visibles en la web.
- **`orders.proveedor` y `orders.medio` guardan la clave normalizada** (minúsculas,
  sin tildes, sin S.A., dominios recortados), no el texto de la fuente. El nombre de
  display es la grafía más frecuente de la entidad: sale de `search.json`
  (`getNombreDisplay`) o de `groups_cache` y `rankings_cache`.
- **`monto` en la base ya está deflactado**: IPC INDEC, promedio anual del índice,
  llevado a pesos del último mes de `ipc_indec.csv`. El nominal no está en la base.
- **Caches de `build_db.py`.** En todas, `jurisdiccion = '*'` significa "todas" y
  `anio = 0` "todos".
  - `totals_cache` alimenta "Cuánto recibió".
  - `rankings_cache` guarda el top 5.
  - `groups_cache` tiene **`rank` contiguo 1..N por clave**: el front pagina con
    `rank > ?` y toma el total del rank máximo.
  - `filtros_cache`: su `n_ordenes` es igual a `COUNT(*)`.
- **`getDetalleGrupo`:** un medio o proveedor `NULL` se filtra con `IS NULL`. Significa
  "sin medio", no "cualquiera".
- **sql.js-httpvfs** (sin mantenimiento desde 2022) trae **SQLite 3.35** en el
  navegador; el ETL usa la de Python. Usa XHR sincrónico en un worker, así que las
  consultas se resuelven en orden. Página de 64 KiB = `requestChunkSize`.
- **La base se publica en UN solo chunk** (`pauta.sqlite.0`). Con chunks de 20 MiB, la
  lectura anticipada de la librería cruzaba el borde y fallaba ("database disk image is
  malformed", p. ej. filtrando por infobae). Tope: 300 MiB, límite de
  `wrangler r2 object put`; si la base lo supera, pasar a subida multipart, no volver a
  partirla.
- **Versionado en R2.** `v/<version>/` es el sha256 de la base, con `meta.generado` en
  ceros y el tamaño de chunk incluido. Una versión nunca se pisa. `config.json` lo sirve
  Pages con `max-age=0` y es el que cambia de versión en cada deploy.
- **Cloudflare Pages no soporta Range requests** (responde 200): la base no puede
  servirse desde Pages.
- **`home.json` es el seed del primer paint**: PBA + su último año, modo agrupado,
  ranking y demo del generador. Si cambian las consultas o el filtro por defecto,
  regenerarlo con `build_db.py`.
- **Datos escritos a mano en el front.** Hay que actualizarlos cuando cambian los datos:
  - `DISPONIBILIDAD` en `DataTable.tsx`;
  - `ANIOS_PILLS` en `Generador.tsx`;
  - cifras del hero y barras de cobertura en `index.astro` (escala de 24 intervalos,
    2003→2027);
  - tabla del README.
- **Windows: escribir archivos con LF.** `Path.write_text` convierte a CRLF y el diff
  marca el archivo entero.

## Deploy

- Push a `main` dispara el build de Cloudflare Pages:
  `python3 etl/build_db.py && node etl/upload_r2.mjs && npm run build && rm -f dist/data/pauta.sqlite.*`.
  En `etl/R2_SETUP.md` está el build command recomendado, que agrega `check_build.py`.
- Variables de entorno de Pages: `R2_BUCKET`, `R2_PUBLIC_URL`, `CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID`.
- Si un deploy de Pages falla en "Installing python" ("not found in image" o "could
  not read Username for 'https://github.com'"), es una falla transitoria de
  Cloudflare: reintentar el deploy desde el panel. Mientras tanto, sigue en vivo la
  versión anterior.
- Verificar después del deploy (tarda ~4 min):
  - `https://datospautaoficial.com.ar/data/config.json` apunta a `/v/<version>/`;
  - el objeto de R2 responde 206 con `Cache-Control: ... immutable`;
  - la tabla carga con un filtro de entidad (p. ej. `?norm=infobae&tipo=medio`).

## Formulario de contacto

- El sitio no muestra la dirección de mail del autor: `/contacto` envía a `/api/contacto`.
- Recorrido del mensaje:
  1. la Pages Function lo pasa por el service binding `CONTACTO` (configurado en el panel de Pages) al Worker `datospautaoficial-contacto`;
  2. el Worker lo envía con el binding `send_email` (`CORREO`) a `DESTINO`.
- `DESTINO` es un secreto del Worker cargado en el panel de Cloudflare. No va en el repo.
- Email Routing está activo en `datospautaoficial.com.ar` (registros MX, SPF y DKIM gestionados por Cloudflare), y `DESTINO` es una dirección verificada.
- Enviar a una dirección verificada es gratis en cualquier plan.
- El Worker lo despliega Workers Builds desde `workers/contacto` en cada push a `main`. No tiene URL pública (`workers_dev: false`).
- Anti-spam:
  - campo trampa `sitio` y tiempo mínimo en la página (`ms`), que se descartan en silencio;
  - control de `Origin`;
  - límites de largo.
- Si llega spam, el paso siguiente es Turnstile. Su clave secreta la carga el usuario, no un agente.

## Cómo verificar cambios

- **Front.**
  - Correr `npx tsc --noEmit` y `npm run build`.
  - Probar en el navegador con el dev server (`.claude/launch.json`, config `dev`).
  - En la consola del dev server se pueden importar los módulos reales, por ejemplo
    `await import('/src/lib/queries.ts')`.
  - Para medir la red:
    `(await (await import('/src/lib/db.ts')).getDb()).worker.getStats()`.
- **Datos.** Consultar `etl/build/pauta.sqlite` con Python en solo lectura (`mode=ro`)
  y comparar contra las fuentes oficiales.

## Fuentes oficiales

| Jurisdicción | Fuente | Estado |
|---|---|---|
| CABA | https://data.buenosaires.gob.ar/dataset/pauta-publicitaria (archivos en `cdn.buenosaires.gob.ar/datosabiertos/datasets/pauta-publicitaria/`, los recientes bajo `.../datasets/secretaria-de-medios/pauta-publicitaria/`) | Anual. 2011-2025. Usa punto decimal; ojo con los montos de 3 decimales. API CKAN genérica. 2023: Cine, Gráfica y Medios vecinales solo en XLSX; el extractor lee los revisados (`XLSX_SIN_CSV`). |
| Nación 2014-2022 | https://datos.gob.ar/dataset/publicidad-oficial | CSV. Sin actualizar desde 08/2022; 2022 cubre solo enero-abril. |
| Nación 2009-2013 | https://www.argentina.gob.ar/node/1759 | Solo PDF. Los "por proveedor y rubro" son pivots: no cargar la fila o columna de total. Junio 2009 no existe en la fuente. |
| PBA | Resoluciones y anexos PDF (normas.gba.gob.ar) | 2020-2024 armado resolución por resolución; 2025 de la fuente oficial. Cobertura parcial. |
| Santa Fe | Informes PDF | Curado en `santa_fe_curado.csv`. |

**Control secundario (no es fuente):** La Nación, con datos de Jefatura de Gabinete,
Poder Ciudadano y Fundación LED, publicó totales de Nación por semestre de 2009-H2 a
2015-H1. Coinciden con los PDF oficiales de 2009-2013. Para 2014-2015 dan menos que el
CSV oficial: se mantiene el oficial.

**APIs de Nación (revisadas el 2026-10-16).** Responden con 502 intermitentes: reintentar
y mandar un `User-Agent`.
- **CKAN de datos.gob.ar:**
  - `https://datos.gob.ar/api/3/action/package_search?q=publicidad` lista el dataset
    `publicidad-oficial`. Sirve para detectar si aparece un recurso nuevo.
  - Al 2026-10-16 sigue con `dataset_modified` 2022-08-30 y los mismos 14 CSV que ya usa
    el extractor.
  - El diccionario de datos está en `https://infra.datos.gob.ar/catalog/jgm/data.json`
    (`distribution[].field`). Para 2014, 2015 y 2016-S1, `total` dice "Monto total
    establecido en la orden", sin aclarar el IVA, así que no resuelve esa duda.
- **Series de Tiempo** (`https://apis.datos.gob.ar/series/api/`):
  - IPC nacional, nivel general: `148.3_INIVELNAL_DICI_M_26:percent_change`.
  - Coincide con `ipc_indec.csv` y llega hasta 2026-07 (este llega hasta 2026-04).
  - Tiene huecos: 2025-12 a 2026-02 vienen vacíos. Sirve para extender `ipc_indec.csv`,
    no para reemplazarlo.
  - Agregar meses cambia todos los montos deflactados de la web (cambia el mes base):
    requiere OK del usuario.
- **Otros datasets.** En datos.gob.ar, que también reúne a los portales federados, buscar
  "publicidad oficial" devuelve solo `publicidad-oficial`. Georef-AR (normalización
  geográfica) no aplica: la base no tiene ubicaciones.

**Crudos descargados**: fuera del repo y solo en la máquina del autor, bajo
`%APPDATA%\Claude\side-session-notes\`:
- `local_70186434-a1ae-4d3d-a6cb-5e7b882c92e4\auditoria_fuentes\`: crudos del
  2026-10-14, el reporte de auditoría por archivo, la lista de resoluciones de PBA
  (`pba_resoluciones_normas_gba.tsv`) y los scripts propuestos (`sf_pdf.py`,
  `pba_anexos.py`);
- `local_5cee6ed6-35b8-493f-8254-50b2a4e17023\actualizacion-datos_2026-10-15\crudos_caba_2025\`;
- `local_5cee6ed6-35b8-493f-8254-50b2a4e17023\caba_2023_xlsx\crudos\`.

Los manifiestos de cada descarga (URL, SHA-256, fecha) están versionados en
`etl/actualizacion_2026-10-15*/`.

## Estado al 2026-10-15

- Ya se arregló y está publicado:
  - el error de lectura entre chunks;
  - el detalle de grupos con medio o proveedor vacío;
  - la paginación sin `OFFSET`;
  - los nombres de display en todos los modos.
- **Actualización de datos publicada** (2026-10-15, aprobada por el usuario). Detalle y
  evidencia en `CORRECCIONES.md` y `etl/actualizacion_2026-10-15/`:
  - montos ×1000 de CABA 2016-2017;
  - "Total general" de los pivots de Nación 2010 y 2012-S1 cargado como orden;
  - meses de Nación 2009;
  - se agregan Nación 2012-S2 y CABA 2025.
  - Cada archivo concilia al centavo con su total oficial. 2009 difiere en centavos
    porque la propia fuente redondeó su fila de totales.
- **CABA 2023 completo publicado** (2026-10-15, aprobado por el usuario).
  Detalle en `CORRECCIONES.md` y `etl/actualizacion_2026-10-15_caba2023/`:
  - se agregan Cine, Gráfica y Medios vecinales 2023, publicados solo en XLSX: 4.837
    órdenes;
  - cada archivo concilia al centavo con la suma de su planilla oficial, y el resto del
    CSV queda idéntico.
- **PBA completo con los anexos publicados: publicado** (2026-10-16, aprobado por el
  usuario). Detalle en `CORRECCIONES.md` y `etl/actualizacion_2026-10-15_pba/`:
  - se agregan 13.136 órdenes de 78 resoluciones (2020-2025), leídas de los anexos PDF;
  - cada anexo concilia al centavo con su total impreso, y el resto del CSV queda idéntico;
  - las filas nuevas van al final del bloque de PBA, con la URL de la resolución en
    `resolucion` y el nombre del PDF en `archivo_origen`;
  - la tabla por resolución está en `resoluciones.tsv`.
- **Santa Fe corregido: publicado** (2026-10-16, aprobado por el usuario). Detalle en
  `CORRECCIONES.md` y `etl/actualizacion_2026-10-15_santafe/`:
  - sale el duplicado de Radio 2008 (564 filas);
  - se agregan los medios faltantes de 2011, TV 2013, Internet 2016, Vía pública 2017 y
    celdas sueltas de 2009, 2015 y 2016 (+3.190 filas);
  - cada año y tipo corregido concilia con el resumen oficial de Santa Fe. 2008, 2009 y
    2011 difieren en centavos por redondeo de la fuente.
  - `corregir.py` exige como entrada el CSV previo a PBA (SHA-256 `dbe7b01f…`). Se
    aplicó sobre ese CSV y después se reinsertaron las 13.136 filas de PBA, que son
    contiguas, en su lugar. Las filas fuera de Santa Fe quedaron idénticas.
- **PBA etapa 2: publicado** (2026-10-16, aprobado por el usuario). Se agregan
  33/2023, 45/2023 y 274/2024 (227 órdenes, $299,4 M nominales). El mes sale del texto
  oficial de cada resolución, bajado con permiso del usuario (`manifest_textos_resoluciones.tsv`;
  crudos en `side-session-notes\local_5cee6ed6-…\pba_resoluciones_sin_mes_2026-10-16\`).
  `agregar.py --etapa 2` verifica el SHA-256 del texto, el mes y el total de su artículo 1.
- **Santa Fe Gráfica 2013 y PBA etapa 3: publicado** (2026-10-16, aprobado por el usuario).
  Detalle en `CORRECCIONES.md`:
  - Gráfica 2013 (`corregir.py --aplicar ...,grafica2013`): +772 filas, $35,2 M nominales.
    El usuario aceptó la diferencia de $1.925,25 en julio contra el resumen del sistema:
    el detalle es una planilla de Calc hecha a mano (13/04/2016, 10:34) y el resumen, un
    reporte GeneXus de 33 minutos antes; las demás planillas de 2013 concilian al centavo.
    Se corrió `corregir.py` sobre el CSV previo a PBA con y sin `grafica2013`, y las 772
    filas de diferencia (contiguas) se insertaron en el CSV vigente en el mismo lugar.
  - PBA 257/2022, 138/2023 y 142/2023 (`agregar_ilegibles.py`): +229 filas, $146,0 M
    nominales. La fuente embebida no tiene texto: cada glifo se identifica por la firma de
    su contorno TrueType, rotulada con los anexos legibles que concilian (sin ambigüedad).
    Cada anexo concilia al centavo con su total impreso.
- Las cifras escritas a mano del front (hero, cobertura, README) reflejan 571.011
  órdenes.
- **También publicado el 2026-10-15:**
  - aviso en Metodología: la base se controló contra cada fuente, pero por su volumen
    puede tener errores y no debe tomarse como fuente única;
  - notas de cobertura en la portada: CABA 2025 parcial, Nación 2013 sin IVA y PBA
    parcial;
  - README sin "más de 500 resoluciones": normas.gba.gob.ar lista 361 resoluciones de
    pauta de PBA en 2020-2024 (456 con 2025);
  - formulario de contacto en vez del mail (ver "Formulario de contacto").
- **Pendientes conocidos, sin corregir:**
  - Nación 2013: la fuente (`DatosPublicidadOficialEnero2013_Mayo2014.csv`, columna
    `IMPORTE NETO`) da el importe sin IVA. 2013-H1 suma $87,9 M nominales menos que el
    PDF oficial, que es con IVA. No hay un factor único de IVA. Se mantiene el dato
    (opción B) y la tarjeta de cobertura de Nación lo aclara. La opción A, reemplazar
    por las celdas del PDF, perdería el detalle por orden.
  - IVA sin verificar en Nación 2014-2015 (columna `total`) y 2021-10 a 2022-04
    (`total_general`). 2016-2021 usan `total_con_iva`; 2009-2013-H1 en PDF son con IVA.
    El usuario cree que probablemente son con IVA y lo considera menor: no se toca.
  - CABA 2025: la fuente solo publicó Radio, Gráfica, Medios vecinales y Cine (falta
    TV, Web y Vía pública). La web lo marca como parcial.
  - PBA, después de la carga de los anexos (ver `etl/actualizacion_2026-10-15_pba/LEEME.md`):
    - no se cargan 79/2020 (sin total impreso) y 17/2021 (no concilia por $76.422);
    - 2023: 2.159 filas de 16 `tabula-*` no tienen anexo publicado. **No son
      duplicados:** los pares que comparten filas son meses distintos con órdenes
      mensuales iguales (p. ej. `tabula-15` = Res. 47/2023 y `tabula-90` = Res. 88/2023);
    - la Res. 301/2025 se verificó a mano: 120 órdenes reales, no subtotales;
    - las rescisiones (251/2024 y 298/2025) no se restan, por decisión del usuario, y
      no se aclara en Metodología. Dan de baja el "compromiso sin devengar" (saldo
      reservado y no usado) de órdenes de compra de 2018-2025, ~$80 M y ~$330 M
      nominales, menos del 1 % de PBA por año. Usan número de OC, no el de OP.
  - CABA 2013: hay una celda ambigua que se resuelve con el XLSX oficial.
- **R2 (verificado en el panel el 2026-10-15):** el bucket `datospautaoficial-db` solo
  tiene la regla por defecto "Default Multipart Abort Rule", que aborta subidas
  multipart incompletas y no borra objetos. No agregar reglas que borren por
  antigüedad: borrarían la versión en vivo.
  - Quedan en el bucket los chunks viejos de la raíz y las versiones anteriores en
    `v/`. Se pueden borrar, salvo la versión a la que apunta `config.json`.
