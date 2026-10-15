# Actualización de datos del 15/10/2026

Aprobada por el usuario el 2026-10-15 ("Sí a todo"). Corrige los errores de carga confirmados contra los archivos oficiales vigentes, agrega el 2do semestre 2012 de Nación y agrega CABA 2025.

La fe de erratas para publicar está en [`CORRECCIONES.md`](../../CORRECCIONES.md). Este archivo es el detalle técnico para revisar la rama.

## Resumen

| Corrección | Archivos | Filas | Nominal | Pesos de abr-2026 |
|---|---|---:|---:|---:|
| CABA 2016-2017: 30 montos leídos ×1000 | 2 | 0 (cambian 30) | −7.468.115.554,87 | −904.199,5 M (−11,51 %) |
| Nación 2010 y 2012-S1: "Total general" cargado como orden | 3 | −2.585 | −972.889.691,18 | −430.796,9 M (−5,48 %) |
| Nación 2009: meses corridos, celdas perdidas, filas basura | 2 | −2 | +521.066,58 | +318,9 M (+0,00 %) |
| Nación 2012-S2: faltaba | 1 nuevo | +1.395 | +518.719.290,15 | +177.727,0 M (+2,26 %) |
| CABA 2025: nuevo (parcial) | 4 nuevos | +9.963 | +22.619.385.780,33 | +28.674,0 M (+0,36 %) |
| **Total** | | **540.413 → 549.184** | **321.714.511.585,04 → 336.412.132.476,05** | **7.856.624,4 M → 6.728.347,9 M (−14,36 %)** |

Las correcciones solas bajan el total ajustado un **16,99 %**; los datos nuevos lo suben un 2,63 %. Los totales salen de la tabla `meta` de `build_db.py`.

## Commits

| Commit | Qué hace |
|---|---|
| `24ec710` | Agrega `regenerar.py` y el manifest de la descarga de CABA 2025. No cambia datos. |
| `b0eccd5` | CABA ×1000 (`--aplicar caba_x1000`). |
| `007647f` | + Nación 2010 y 2012-S1. El CSV resultante es **idéntico byte a byte a la opción a2** revisada el 2026-10-14 (SHA-256 `e48ba29a…`), que se había armado con otro método (un parche fila por fila). |
| `6018a18` | + Nación 2009. |
| `01e6103` | + Nación 2012-S2. |
| `485d51c` | + CABA 2025. CSV final: SHA-256 `edd5ea3ce9c1d02dc16ec06e91ec5cdf155f9f5d01a4a287ecff7fd23febf5ac`. |
| (último) | `home.json` regenerado, esta carpeta de evidencia y `CORRECCIONES.md`. |

Cada commit de datos se generó desde el CSV original con las correcciones acumuladas, así que se puede revertir uno por uno. Si se revierte alguno, hay que volver a correr `regenerar.py` sin esa corrección y regenerar `home.json`.

## Método: reemplazo por archivo de origen

`regenerar.py` usa las funciones del ETL del repo (`extract_caba._parse_combinado`, `_parse_pertype` y `extract_nacion._parse_pivot_pdf`) sobre los crudos oficiales, y después aplica lo mismo que `unificar.py`: relleno de `medio`, Vía Pública y `_valida_fila`.

- **Crudos.** Cada uno se verifica contra el SHA-256 de su manifest antes de leerlo. Los PDF, además, deben ser los revisados en `PDF_DE_PIVOT` / `PDF_SIN_CSV` y conciliar; si no, no se carga nada. Están en `manifest_crudos.tsv`, con su URL.
- **Archivos reemplazados.** Se regenera solo el bloque de filas de cada `archivo_origen` afectado, en el mismo lugar.
- **Archivos nuevos.** Van donde los pondría `unificar.py`:
  - CABA 2025 al final de CABA, porque la carpeta 2025 va después de la de 2024;
  - Nación 2012-S2 antes del 1er semestre, porque los PDF sin CSV de la carpeta 2012 se cargan primero.
  - Así, una corrida completa del ETL con estos crudos da el mismo CSV.

### El resto del CSV queda idéntico

1. **Control del script** (`verificacion.txt`): las 515.541 filas que no son de los archivos corregidos o nuevos son idénticas byte a byte y están en el mismo orden. SHA-256 de esas filas: `0017aed9…21a1`.
2. **`git diff -U0 8241b17 HEAD -- etl/data/pauta_oficial_unificado_v2.csv`**: 2.014 bloques, 6.115 líneas quitadas y 14.886 agregadas. **Ninguna** pertenece a otro `archivo_origen` (`diff_resumen.tsv`).

| archivo_origen | líneas quitadas | líneas agregadas |
|---|---:|---:|
| pauta-publicitaria-2016.csv | 28 | 28 |
| pauta-publicitaria-2017-total.csv | 2 | 2 |
| (nuevo v2) Pauta_por_Proveedor_conIVA-_-2009-mayo-oct.csv | 1.053 | 1.061 |
| (nuevo v2) Pauta_por_proveedor_conIVA_nov_dic_2009.csv | 212 | 202 |
| (nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv | 1.006 | 324 |
| (nuevo v2)segundo_semestre_prov_rubro-2010.csv | 1.832 | 878 |
| inversion_1er_Semestre_2012_proveedor_rubro.csv | 1.982 | 1.033 |
| 2dosemestre2012_01_prov_rubro.pdf | 0 | 1.395 |
| 2025_Pauta_Publicitaria_*.csv (4) | 0 | 9.963 |

## Conciliación con el total oficial

`conciliacion.tsv` tiene además la URL y el SHA-256 de cada fuente. "Total oficial":
- CSV: suma exacta (en decimal) de la columna de importe del CSV oficial, leída sin el ETL.
- PDF: el "Total general" leído del texto de la página, no por coordenadas.

| Archivo | Filas antes → después | Total antes | Total después | Total oficial | Dif. |
|---|---:|---:|---:|---:|---:|
| CABA pauta-publicitaria-2016.csv | 6.411 → 6.411 | 6.911.727.812,68 | 657.508.065,89 | 657.508.065,89 | 0,00 |
| CABA pauta-publicitaria-2017-total.csv | 9.497 → 9.497 | 2.326.532.584,02 | 1.112.636.775,94 | 1.112.636.775,94 | 0,00 |
| Nación may-oct 2009 | 2.294 → 2.302 | 245.442.921,25 | 245.572.554,64 | 245.572.555,62 ¹ | −0,98 ¹ |
| Nación nov-dic 2009 | 523 → 513 | 77.439.732,08 | 77.831.165,27 | 77.831.165,29 ¹ | −0,02 ¹ |
| Nación ene-jun 2010 | 1.566 → 884 | 470.535.967,45 | 244.128.145,44 | 244.128.145,44 | 0,00 |
| Nación jul-dic 2010 | 2.356 → 1.402 | 759.809.574,44 | 410.232.355,85 | 410.232.355,85 | 0,00 |
| Nación ene-jun 2012 | 2.225 → 1.276 | 817.199.119,86 | 420.294.469,28 | 420.294.469,28 | 0,00 |
| Nación jul-dic 2012 (nuevo) | 0 → 1.395 | — | 518.719.290,15 | 518.719.290,15 | 0,00 |
| CABA 2025 Cine (nuevo) | 0 → 46 | — | 463.707.193,00 | 463.707.193,00 | 0,00 |
| CABA 2025 Gráfica (nuevo) | 0 → 672 | — | 7.024.455.278,68 | 7.024.455.278,68 | 0,00 |
| CABA 2025 Medios Vecinales (nuevo) | 0 → 4.055 | — | 3.738.449.119,01 | 3.738.449.119,01 | 0,00 |
| CABA 2025 Radio (nuevo) | 0 → 5.190 | — | 11.392.774.189,64 | 11.392.774.189,64 | 0,00 |

¹ **2009 es el único que no concilia al centavo con un total impreso, y la diferencia es de la fuente.**
- Los PDF de 2009 son por mes y no tienen "Total general". El total oficial es la suma de su fila de totales por mes, que se calculó antes de redondear cada celda.
- Lo cargado es exactamente la suma de las celdas del PDF: 245.572.554,64 y 77.831.165,27. Coincide al centavo con el lector geométrico independiente de la auditoría de fuentes (`auditoria_pivots_nacion_resumen.tsv`).
- Por mes, la diferencia contra la fila de totales va de −0,41 a +0,01. Antes, por mes, era de decenas de millones:

| Mes 2009 | Fila de totales del PDF | Base antes | Base después | Dif. después |
|---|---:|---:|---:|---:|
| mayo | 116.778.592,23 | 157.478.201,69 | 116.778.592,01 | −0,22 |
| julio | 42.341.328,05 | 26.649.586,99 | 42.341.327,64 | −0,41 |
| agosto | 27.726.333,01 | 28.171.355,01 | 27.726.332,64 | −0,37 |
| septiembre | 16.535.598,02 | 26.478.454,81 | 16.535.598,03 | +0,01 |
| octubre | 42.190.704,31 | 6.665.322,75 | 42.190.704,32 | +0,01 |
| noviembre | 53.754.561,17 | 72.461.043,22 | 53.754.561,15 | −0,02 |
| diciembre | 24.076.604,12 | 4.978.688,86 | 24.076.604,12 | 0,00 |

- El ETL revisado (`_tabla_pdf`) acepta en 2009 hasta medio centavo por celda, por esta razón.
- 2009 está en un commit propio (`6018a18`): si se prefiere exigir el centavo contra el total impreso, se puede dejar afuera.

### Controles independientes

- **CABA ×1000:** los 30 cambios son, uno por uno, los de `cambios_a.csv`, el parche revisado el 2026-10-14. `cambios_caba_x1000.csv` tiene cada fila con la línea del CSV oficial y el importe tal como está escrito, por ejemplo `pauta-publicitaria-2016.csv` línea 5275: `1160879.808`.
- **Pivots 2010-2012:** proveedor por proveedor, los montos de antes menos el Total general son exactamente los de después.

  | Archivo | Totales que salen | Rubros corregidos | Otros cambios |
  |---|---:|---:|---|
  | ene-jun 2010 | 683 | 323 | entra TOTAL PUBLIVIA SA, 70.785,00 |
  | jul-dic 2010 | 954 | 878 | — |
  | ene-jun 2012 | 949 | 1.033 | — |

  Coincide con la auditoría independiente.
- **2012-S2:** las 1.395 filas son idénticas a `registros_2dosemestre2012.csv` de la sesión de huecos, que se cruzó celda por celda con el lector de la auditoría.
- **CABA 2025:** no se descarta ninguna fila del CSV oficial y todas las fechas son de 2025.
  - Hay 723 filas repetidas exactas, tal como las publica la fuente: mismo medio, fecha y monto, típico de medios vecinales. 2024 tiene 1.120.
  - Los montos van de 65.000 a 176 M: no hay ×1000.

### Control externo: tabla de La Nación por semestre

Fuente: JGM / Poder Ciudadano / Fundación LED, en pesos redondeados por proveedor. La tabla es la suma de todas sus filas, incluidas "Total Publivia S.A." y "Total F.M. S.R.L.", que son proveedores.

| Semestre | La Nación | Base antes | Base después | Dif. después |
|---|---:|---:|---:|---:|
| 2009-H2 | 206.630.089 | 165.404.452 | 206.625.128 | −4.961 ² |
| 2010-H1 | 244.128.152 | 470.535.967 | 244.128.145 | −7 |
| 2010-H2 | 410.232.369 | 759.809.574 | 410.232.356 | −13 |
| 2011 (H1+H2) | 771.157.711 | 771.157.684 | 771.157.684 | −27 |
| 2012-H1 | 420.294.480 | 817.199.120 | 420.294.469 | −11 |
| 2012-H2 | 518.719.294 | 0 | 518.719.290 | −4 |
| 2013-H1 | 610.453.685 | 522.526.407 | 522.526.407 | −87.927.278 ³ |
| 2013-H2 | 750.258.671 | 750.258.801 | 750.258.801 | +130 |

² Jul-dic según la fila de totales del PDF oficial: 206.625.128,68. La diferencia de 4.961 es entre La Nación y el PDF; la base sigue al PDF.
³ Hallazgo, ver abajo. No se corrige en esta actualización.

## Validación y base

- **Tests:** `python -m unittest discover -s etl/tests`: 40 OK.
- **`validar.py`** (`validacion_antes.md` → `validacion_despues.md`):
  - atípicos ≥1000× la mediana: **34 → 11**. Los 11 que quedan son los que el reporte del 2026-10-14 clasificó como dato correcto de la fuente: SENTIDOS S.A. y RTA 2020-2022 (totales agregados) y Media Force 2014.
  - archivos con "Total general" cargado como orden: **3 → 0**.
  - sin montos ≤0, fechas malformadas ni jurisdicciones inválidas.
  - "proveedor nulo" sube en 9.963, porque CABA 2025 trae solo medio, igual que 2018-2024.
- **`build_db.py`** (sin `R2_PUBLIC_URL`):
  - 549.184 órdenes, 0 montos nulos, 2003-2025;
  - 6.487 proveedores y 15.719 medios normalizados (antes 6.481 y 15.688).
  - `check_build.py` pasa todo salvo "dist/ existe", que requiere `npm run build`.
- **`public/data/home.json`:**
  - El versionado era coherente con el CSV anterior: al reconstruirlo sin cambios solo difiere en el último dígito de sumas en coma flotante.
  - Después de la actualización, la vista inicial (PBA 2025) no cambia de montos. Sí cambia un nombre visible: "AM 630 RADIO RIVADAVIA" pasa a "AM 630 RIVADAVIA", porque el nombre de un medio es la grafía más frecuente, y CABA 2025 trae esta.
  - Cambian el ranking histórico global y el Grupo Clarín del generador: 689.264 M → 536.541 M; CABA 2016 55.146 M → 14.168 M; CABA 2017 129.339 M → 13.870 M.

## Impacto

### Por jurisdicción (pesos de abril de 2026)

| Jurisdicción | Antes | Después | Cambio |
|---|---:|---:|---:|
| CABA | 2.998.434,3 M | 2.122.908,9 M | −29,20 % |
| Nación | 4.091.252,9 M | 3.838.501,8 M | −6,18 % |
| PBA | 317.730,6 M | 317.730,6 M | sin cambio |
| Santa Fe | 449.206,5 M | 449.206,5 M | sin cambio |

### Por año (solo los que cambian)

| Jurisdicción y año | Filas | Nominal antes → después | Ajustado antes → después |
|---|---:|---:|---:|
| CABA 2016 | 6.411 → 6.411 | 6.911.727.812,68 → 657.508.065,89 | 864.611,8 M → 82.249,9 M |
| CABA 2017 | 9.497 → 9.497 | 2.326.532.584,02 → 1.112.636.775,94 | 233.512,0 M → 111.674,3 M |
| CABA 2025 | 0 → 9.963 | 0 → 22.619.385.780,33 | 0 → 28.674,0 M |
| Nación 2009 | 2.817 → 2.815 | 322.882.653,33 → 323.403.719,91 | 197.584,7 M → 197.903,6 M |
| Nación 2010 | 3.922 → 2.286 | 1.230.345.541,89 → 654.360.501,29 | 629.728,7 M → 334.921,8 M |
| Nación 2012 | 2.225 → 2.671 | 817.199.119,86 → 939.013.759,43 | 279.994,1 M → 321.731,1 M |

### Top 5 histórico (todas las jurisdicciones, pesos de abril de 2026)

| # | Proveedores antes | Proveedores después |
|---|---|---|
| 1 | IMPREBA S.A. — 346.184 M | TELEVISION FEDERAL S.A. — 238.853 M |
| 2 | ARTE RADIOTELEVISIVO ARGENTINO S.A. — 317.083 M | ARTE RADIOTELEVISIVO ARGENTINO S.A. — 160.637 M |
| 3 | TELEVISION FEDERAL S.A. — 253.729 M | TELEARTE — 159.060 M |
| 4 | EVENTOS PRODUCCIONES S A — 183.626 M | AMERICA TV — 156.947 M |
| 5 | TELEARTE — 173.466 M | EDITORIAL LA PAGINA S.A. — 110.252 M |

IMPREBA (Diario Popular) pasa al 10.º lugar (64.924 M) y Eventos Producciones (Canal 26) al 20.º (36.255 M).

| # | Medios antes | Medios después |
|---|---|---|
| 1 | Via Publica — 419.466 M | Via Publica — 405.007 M |
| 2 | POPULAR — 281.445 M | CANAL 13 — 240.481 M |
| 3 | CANAL 13 — 240.481 M | TELEFE — 236.045 M |
| 4 | TELEFE — 236.045 M | CLARIN — 161.747 M |
| 5 | TN — 223.203 M | CANAL 9 — 130.764 M |

POPULAR pasa al 87.º lugar (8.443 M) y TN al 10.º (66.757 M).

| # | Grupos antes | Grupos después |
|---|---|---|
| 1 | Grupo Clarín — 689.264 M | Grupo Clarín — 536.541 M |
| 2 | Viacom (Argentina) — 246.761 M | Viacom (Argentina) — 246.761 M |
| 3 | Grupo América — 205.752 M | Grupo América — 205.934 M |
| 4 | Grupo Telecentro — 184.212 M | Grupo Indalo — 128.796 M |
| 5 | Grupo Indalo — 128.796 M | Grupo La Nación — 115.821 M |

### Número de orden (`#id`)

`orders.id` es el número de fila del CSV. En el sitio se muestra, pero no hay enlaces permanentes por id.

| Filas | Qué pasa con el `#id` |
|---|---|
| CABA 2003-2024 (1 a 209.877) | no cambia |
| Nación 2013-2022 | +9.963 |
| Nación 2009-2012 | nuevo (son las filas regeneradas) |
| PBA y Santa Fe | +8.771 |

Para cambiar menos ids, CABA 2025 se podría poner al final del CSV. Así no se corrían las filas de Nación 2013-2022, pero el CSV dejaba de ser el que produce `unificar.py`. Se eligió el orden del ETL.

## Decisiones tomadas por defecto (regla del proyecto: no cambiar nada que no sea parte de la corrección)

- **`archivo_origen`.** Queda como en la base:
  - las filas leídas del PDF conservan el nombre del CSV "(nuevo v2)" al que reemplazan, como ya hace el ETL;
  - el archivo nuevo de 2012-S2 lleva el nombre del PDF, como lo pone el ETL (`PDF_SIN_CSV`).
- **Textos que el PDF escribe distinto.** Quedan como en la base (`textos_conservados.tsv`):
  - medios `X4`, `PYM` y `C&N` de 2009 (7 filas): el PDF tiene espacios, "X 4", "P Y M" y "C & N";
  - proveedor `ASOC.CIV.S/FIN.LUCRO""NOSOTROS""` (2 filas, 2010-S2 y 2012-S1): el PDF dice `LUCRO"NOSOTROS"`. Es un error de comillas del texto viejo, pero no es parte de lo aprobado; la opción a2 tampoco lo tocaba.
- **Medio que era un monto.** En 4 filas de 2009, el `medio` de la base era un monto mal leído (`27.562,16`, `484,00`, `383.075,59`, `8.465,60`), porque el proveedor no tiene medio en el PDF. Eso sí es parte de la corrección de las celdas perdidas: el medio queda vacío, como en el PDF.
- **Rubro (`tipo_de_medio`) de los pivots 2010-2012.** Se corrige según el PDF, como en la opción a2 recomendada el 2026-10-14. No afecta al sitio, porque `orders` no guarda el rubro, pero sí al CSV publicado.
- **Montos con 3 o más decimales** (CABA 2016-2017): se redondean a 2, como hace el ETL para todo el CSV. La suma concilia igual al centavo.

## Hallazgo: Nación 2013-H1 (no se corrige: requiere decisión)

**Causa: clara y verificable.**
- `DatosPublicidadOficialEnero2013_Mayo2014.csv` trae la columna `IMPORTE NETO`, sin IVA, y `_parse_enero2013` la toma como monto. El resto de Nación es con IVA.
- Comparado proveedor por proveedor con el PDF oficial `1ersemestre2013_01_prov_rubro_2.pdf` (SHA-256 `b33aa21f…`, 610.453.676,53), la diferencia sigue la alícuota de cada proveedor:

| Relación PDF / base | Proveedores | Base | PDF − base |
|---|---:|---:|---:|
| ×1,21 (IVA 21 %) | 412 | 403.107.163 | 84.672.996 |
| ×1,105 (IVA 10,5 %) | 133 | 39.257.898 | 4.128.832 |
| ×1 (exento) | 436 | 36.404.058 | −2 |
| entre 1 y 1,21 (alícuotas mezcladas) | 62 | 36.386.334 | 4.983.678 |
| otros / solo en una de las dos | 21 | 7.370.954 | −5.858.235 |

- 981 de 1.064 proveedores calzan exacto con 0 %, 10,5 % o 21 %. No hay un factor único: no se puede corregir multiplicando.
- **Impacto:** faltan 87.927.269,53 nominales, unos 24.152 M de abril 2026 (0,36 % de la base corregida).

**Propuesta, como corrección separada, para decidir:**
- **Opción A.** Reemplazar las 14.023 órdenes de ene-jun 2013 (sin IVA) por las 1.361 celdas proveedor × rubro del PDF (con IVA), como se hace con 2010-2012.
  - A favor: concilia al centavo y queda con IVA como el resto de Nación.
  - En contra: se pierde el detalle por orden de ese semestre (número de orden y mes).
- **Opción B.** Dejar las órdenes y aclarar en Metodología que Nación 2013 está sin IVA.

**2013-H2:** usa la misma columna, así que probablemente también está sin IVA, pero no hay una fuente oficial con IVA para verificarlo. Que La Nación coincida con la base en $130 sugiere que usó este mismo dato para ese semestre.

## Otros pendientes (no se tocaron)

- **CABA 2023 incompleto.** Medios Gráficos, Cine y Medios Vecinales 2023 se publicaron **solo en XLSX** y no están en la base, porque el ETL lee solo `*.csv`.
  - Archivos: `pauta-publicitaria-medios-graficos-2023.xlsx`, `pauta-publicitaria-cine-2023.xlsx`, y `BA DATA 2023 - Medios Vecinales.xlsx` / `BA_DATA_2023_Medios_Vecinales.xlsx`, este último en dos versiones.
  - Impacto sin medir: hay que bajar esos XLSX, que requiere permiso.
  - **CABA 2024 no tiene faltantes:** sus 8 CSV del portal están todos en la base. El catálogo del portal, consultado hoy, es igual al del 2026-10-14 (165 recursos, modificado el 21/07/2026).
- **CABA 2025 incompleto en la fuente.** Faltan TV abierta, TV cable, Web y Vía pública, que en 2024 fueron el 85,8 % de CABA. Hay que volver a mirar el portal.
- **Nación 2013, rubro "Cine".** En la fuente es TV Cable (hallazgo de la sesión de huecos). No toca el sitio.
- **Nación junio 2009.** No está en ninguna publicación oficial.
- **De la auditoría de fuentes, fuera de este alcance:**
  - Santa Fe Radio 2008 duplicado;
  - medios omitidos en Santa Fe 2011/2013;
  - cobertura parcial de PBA 2020-2025;
  - celda ambigua de CABA 2013 (`926.957`).

## Cómo reproducir

```bash
git show 8241b17:etl/data/pauta_oficial_unificado_v2.csv > /tmp/antes.csv
python -I etl/actualizacion_2026-10-15/regenerar.py /tmp/antes.csv \
  "<auditoria_fuentes>/crudos_2026-10-14" "<crudos_caba_2025>" \
  --salida etl/data/pauta_oficial_unificado_v2.csv --informe /tmp/informe
python etl/build_db.py
```

- `<auditoria_fuentes>/crudos_2026-10-14` es la carpeta de crudos de la auditoría de fuentes, con su `manifest_descargas.tsv`.
- `<crudos_caba_2025>` tiene los 4 CSV de 2025 y `manifest_descargas_caba_2025.tsv` (renombrado `manifest_descargas.tsv`).
- Cualquier copia sirve: el script verifica el SHA-256 de cada archivo.
- Requiere `pdfplumber` (probado con 0.11.9 y Python 3.10).

## Archivos de esta carpeta

| Archivo | Qué tiene |
|---|---|
| `regenerar.py` | el script |
| `manifest_crudos.tsv` | los 12 crudos oficiales usados: URL, tamaño, SHA-256, Last-Modified |
| `manifest_descargas_caba_2025.tsv` | la descarga nueva de hoy (4 CSV de CABA 2025) |
| `conciliacion.tsv` | la tabla de conciliación por archivo |
| `cambios_caba_x1000.csv` | los 30 montos de CABA, con la línea del CSV oficial |
| `cambios_por_fila.csv` | todas las filas que salen (id de antes) y entran (id de después) en los archivos reemplazados |
| `textos_conservados.tsv` | los textos que quedan como en la base |
| `diff_resumen.tsv` | líneas del `git diff` por `archivo_origen` |
| `verificacion.txt` | control de las filas que no cambian |
| `validacion_antes.md`, `validacion_despues.md` | `validar.py` antes y después |
