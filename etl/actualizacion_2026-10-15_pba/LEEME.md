# PBA: anexos oficiales que faltaban (15-16/10/2026)

Agrega a la base las órdenes de publicidad de PBA de los anexos publicados en normas.gba.gob.ar que no estaban cargados. La etapa 1 (78 resoluciones) está publicada desde el 16/10/2026. La etapa 2 (3 resoluciones más, ver abajo) todavía no.

La fe de erratas para publicar está en [`CORRECCIONES.md`](../../CORRECCIONES.md). Este archivo es el detalle técnico para revisar la rama. Repite el método de [`etl/actualizacion_2026-10-15/`](../actualizacion_2026-10-15/LEEME.md): cada fuente verificada por SHA-256, conciliación al centavo y el resto del CSV idéntico byte a byte.

## Resumen

| | Antes | Después |
|---|---:|---:|
| Órdenes | 554.021 | 567.157 (+13.136) |
| Órdenes de PBA | 43.982 | 57.118 |
| Total nominal | 339.066.379.833,99 | 350.233.819.939,99 (+11.167.440.106,00) |
| Total en pesos de abril de 2026 | 6.743.610,5 M | 6.835.675,5 M (+92.065,0 M, +1,37 %) |
| PBA en pesos de abril de 2026 | 317.730,6 M | 409.795,6 M (+29,0 %) |
| Proveedores / medios normalizados | 6.487 / 15.728 | 6.521 / 15.941 |

Se cargan **78 resoluciones**: 69 que no tenían ninguna orden en la base y 9 que tenían una parte. Los totales salen de la tabla `meta` de `build_db.py`.

### Por año (las órdenes van al año del mes en que se emitieron)

| Año | Órdenes antes → después | Nominal antes → después | Pesos de abril de 2026 | Lo publicado que está en la base, antes → después |
|---|---:|---:|---:|---:|
| 2020 | 1.304 → 3.305 | 260.607.556 → 653.112.922 | 8.936,8 M → 22.396,6 M | 38 % → 95,5 % |
| 2021 | 4.956 → 11.997 | 1.616.355.715 → 3.566.048.494 | 37.367,9 M → 82.442,1 M | 45 % → 100 % |
| 2022 | 8.456 → 10.761 | 4.816.691.298 → 6.271.668.907 | 64.619,7 M → 84.139,4 M | 79 % → 100 % |
| 2023 | 13.773 → 14.602 | 15.759.376.819 → 16.497.136.340 | 90.620,5 M → 94.862,8 M | 94 % → 99,5 % |
| 2024 | 6.574 → 7.170 | 24.000.553.728 → 26.563.574.639 | 43.170,2 M → 47.780,3 M | 90 % → 99,1 % |
| 2025 | 8.919 → 9.283 | 57.597.958.639 → 61.667.442.559 | 73.015,5 M → 78.174,3 M | 93 % → 100 % |

- "Lo publicado" es la suma de los anexos de aprobación legibles, por el mes de las órdenes. No incluye las resoluciones sin anexo ni los 3 anexos ilegibles (ver abajo).
- El año de la base y el del anexo no siempre coinciden: los `tabula-*` toman el año del nombre del archivo, y algunas órdenes de diciembre de 2022 están en archivos de 2023. Por eso la cobertura se mide por resolución, no comparando totales anuales.
- En 2025, la Res. 301/2025 estaba a medias (ver abajo) y faltaban 4 resoluciones de noviembre (307, 308, 309 y 311/2025).

## Commits

| Commit | Qué hace |
|---|---|
| `528c829` | Scripts (`leer_anexos.py`, `cruzar.py`, `agregar.py`) y la evidencia de esta carpeta. No cambia datos. |
| `6c079b6` | El CSV con las 13.136 filas nuevas. Solo agrega líneas. SHA-256 `e9ac121acab5e72500e454ee4a9a27f393359cbb068f51d2f03c6e2e2915cddf`. |
| (último) | `home.json`, cifras de la portada y README, nota de cobertura de PBA, AGENTS.md, esta nota y `CORRECCIONES.md`. |

## Etapa 2 (16/10/2026): 33/2023, 45/2023 y 274/2024

Ni el resumen ni el anexo de estas tres resoluciones dicen de qué mes son las órdenes. El usuario autorizó bajar su texto oficial desde normas.gba.gob.ar (`manifest_textos_resoluciones.tsv`: URL, tamaño, SHA-256 y fecha). Los PDF están fuera del repo, en `side-session-notes\local_5cee6ed6-…\pba_resoluciones_sin_mes_2026-10-16\crudos\`.

| Resolución | Texto | Artículo 1: órdenes emitidas en | Artículo 1: total | Anexo: total impreso | Órdenes |
|---|---|---|---:|---:|---:|
| 33/2023 | `xDwLdZSK.pdf` | noviembre de 2022 | 1.875.500,00 | 1.875.500,00 | 1 |
| 45/2023 | `xb3Ra5cp.pdf` | diciembre de 2022 | 60.191.748,00 | 60.191.748,00 | 145 |
| 274/2024 | `0XnqrlHd.pdf` | noviembre de 2024 | 237.373.821,00 | 237.373.821,00 | 81 |

- `agregar.py --etapa 2 --textos DIR` parte del CSV de la etapa 1 (SHA-256 `e9ac121a…cddf`) y del cruce sobre ese CSV. Para cada resolución exige:
  - el SHA-256 del texto;
  - que el artículo 1 diga ese mes y ese total;
  - que el total del anexo sea el mismo, y las mismas condiciones que la etapa 1.
- Con el CSV de la etapa 1, `cruzar.py` da las 78 resoluciones de la etapa 1 como "cargada": las filas agregadas emparejan con su anexo.
- La etapa 1 se sigue reproduciendo igual: con el CSV de antes da otra vez `e9ac121a…cddf`.
- **Resultado:** +227 órdenes, +299.441.069,00 nominales, +1.259,6 M de abril de 2026. Van al final del bloque de PBA (`#id` 505.971 a 506.197); Santa Fe corre su número en 227 más.
  - Sobre el CSV de la etapa 1: 567.157 → 567.384 órdenes (SHA-256 `58c86802…c360`).
  - Integrado con la corrección de Santa Fe de `main` (d8f6377), que solo cambió el bloque de Santa Fe: 569.783 → 570.010 órdenes y 6.846.542,4 M → 6.847.802,0 M de abril de 2026. Se verificó que el CSV integrado es exactamente el de `main` con las 227 filas en su lugar (SHA-256 `a1faee49…739a`).
- `git diff --numstat`: 227 líneas agregadas, 0 quitadas.
- PBA por año: 2022 pasa de 10.761 a 10.907 órdenes (84.139,4 M → 84.972,1 M de abril de 2026) y 2024 de 7.170 a 7.251 (47.780,3 M → 48.207,3 M).
- Cobertura de lo publicado y legible: 2020 95,5 %; 2021 a 2025, 100 %.
- `conciliacion_etapa2.tsv` y `validacion_despues_etapa2.md` (11 atípicos, igual que antes).
- Proveedores y medios normalizados no cambian (6.521; 16.022 medios con Santa Fe corregido).

## Fuente

- La lista de resoluciones de pauta de normas.gba.gob.ar armada por la auditoría de fuentes del 2026-10-15: `pba_resoluciones_normas_gba.tsv`, con 456 resoluciones y 427 anexos (462 filas, una por anexo).
- Los 427 anexos PDF que bajó esa auditoría el 2026-10-14, con su URL, tamaño y SHA-256: `manifest_anexos.tsv`. Los PDF están fuera del repo, en `side-session-notes\local_70186434-…\auditoria_fuentes\crudos_2026-10-14\D-PBA\`.
- **No se bajó nada nuevo.**

## Método

### 1. Lectura de los anexos (`leer_anexos.py`)

- Las tablas de los anexos tienen bordes dibujados, así que se leen celda por celda con `pdfplumber.extract_tables()`. Las columnas salen del encabezado (OP / Proveedor / Medio / Monto, con sus variantes: "Orden de Publicidad", "O.P", "Preveedor", "Provedor", "Importe", "Total Op").
- El texto de una celda que ocupa dos renglones se une con un espacio, **igual que en los `tabula-*` de la base** (por ejemplo, `WWW.SALPIMENT A.COM.AR`, tal como ya está cargado). Así las órdenes nuevas de un medio quedan con el mismo nombre que las que ya estaban.
- El total del anexo es la fila que trae solo un monto (con o sin el rótulo "Total"); algunos anexos lo imprimen debajo de la tabla o en una página aparte.
- Casos especiales, todos controlados por la conciliación con el total impreso:
  - montos partidos por el PDF ("$ 3 85.000,00", dígitos pegados en el archivo): se unen;
  - montos con coma de miles y punto decimal ("$ 9,000.00");
  - un renglón de un medio que el PDF pasa a una fila aparte: se une a la orden anterior;
  - un guion suelto delante del monto, que es el final del texto del medio corrido de celda.
- **Resultado:** 406 de los 415 anexos de aprobación concilian al centavo con su total impreso (sin contar 3 que repiten otro anexo). Los que no (`anexos.tsv`, columna `motivo`):

| Resolución | Anexo | Motivo | ¿Afecta la carga? |
|---|---|---|---|
| 79/2020 | `lxkRme02.pdf` | una sola orden ($353.088) y sin total impreso | no se carga |
| 17/2021 | `n0vlmmBE.pdf` | las 158 órdenes suman $30.766.762 y el total impreso dice $30.843.184 ($76.422 más) | no se carga |
| 257/2022, 138/2023, 142/2023 | `yBo8ORVz`, `30PEDyxP`, `dV9KZYxO` | la fuente del PDF no tiene texto (requiere OCR) | no se carga |
| 259/2024, 208/2025, 283/2025, 284/2025 | | sin total impreso | no: ya estaban completas en la base |
| 251/2024, 298/2025 | 6 anexos | rescisiones (otro formato) | aparte, ver abajo |

### 2. Cruce por resolución (`cruzar.py`)

La base no guarda el número de OP. Una fila de la base se empareja con una orden del anexo por **monto exacto** y, en este orden: proveedor y medio iguales, proveedor igual, medio igual (sin tildes, mayúsculas ni signos).

1. **Vínculo directo:** `PBA_2025.csv` por la URL de la resolución; los `tabula-*` que guardan el expediente, por el expediente impreso en el anexo.
2. **Por pares:** lo que queda (los bloques sin expediente, casi todo 2021-2024, y las filas de otro anexo dentro de un bloque con expediente) se asigna bloque contra resolución, empezando por el par que comparte más órdenes. Se acepta con al menos 3 órdenes en común que sean la mitad de lo que le queda al bloque o a la resolución. Así una orden mensual que se repite igual en otro mes no arrastra una resolución entera.
3. **Solo monto,** dentro de los vínculos ya hallados.

Resultado (`resoluciones.tsv`, columnas `estado` y `accion`):

| Estado | Resoluciones |
|---|---:|
| ya estaba completa | 329 |
| se cargan las órdenes que faltan | 78 |
| no se carga (sin mes, sin total o no concilia); las 3 sin mes se cargan en la etapa 2 | 5 |
| sin anexo con órdenes publicado (incluye rectificaciones sin anexo y resoluciones de personal) | 35 |
| anexo ilegible | 3 |
| repite el anexo de otra resolución | 4 |
| rescisión | 2 |
| **Total** | **456** |

- **Fuera de 2023, todas las filas de PBA de la base tienen su orden en un anexo oficial.**
- `bloques_base.tsv` dice a qué resolución corresponde cada bloque de la base (`archivo_origen` + expediente) y cómo se vinculó.

### 3. Carga (`agregar.py`)

- Solo las resoluciones de la lista `CARGAR`, revisada a mano. El script exige, para cada una:
  - que sus anexos sean de aprobación, propios (no repetidos) y concilien con su total impreso;
  - que lo que ya estaba en la base más lo que se agrega dé exactamente el total del anexo, en órdenes y al centavo.
- **Campos de las filas nuevas:**
  - `anio` y `fecha`: el mes de emisión de las órdenes según el resumen de la resolución (`AAAA-MM-01`), como `PBA_2025.csv`. En 44/2023 y 70/2023 el resumen no dice el mes y sale de la referencia del anexo ("diciembre 2022", "febrero 2023").
  - `proveedor` y `medio`: el texto del anexo.
  - `tipo_de_medio`: vacío, como el resto de PBA.
  - `resolucion`: la URL de la resolución, como `PBA_2025.csv`. En el sitio se ve como un enlace a la resolución oficial.
  - `archivo_origen`: el nombre del PDF del anexo, como el ETL hace con los PDF de Nación.
- Pasan por el mismo control de calidad que `unificar.py` (`posprocesar`) y se escriben igual (`a_lineas`).
- **Lugar:** al final del bloque de PBA, después de `PBA_2025.csv`, en el orden de las resoluciones. No hay un extractor del ETL que las produzca, así que no hay un "orden del ETL" que seguir; se eligió el lugar que no corre ningún `#id` de CABA, Nación ni PBA.

## Conciliación

`conciliacion.tsv` tiene las 78 resoluciones cargadas: órdenes agregadas, monto agregado, lo que ya estaba en la base, total del anexo y total impreso. En las 78, **lo que estaba más lo agregado es igual al total impreso del anexo, al centavo.**

Las 9 que estaban a medias:

| Resolución | Ya en la base | Se agregan | Total del anexo |
|---|---:|---:|---:|
| 80/2020 | 170 órdenes, 50.450.284 | 4, 646.336 | 51.096.620 |
| 118/2020 | 191, 63.505.392 | 3, 1.134.724 | 64.640.116 |
| 119/2020 | 305, 67.626.249 | 5, 731.186 | 68.357.435 |
| 129/2020 | 64, 862.245 | 1, 18.829 | 881.074 |
| 133/2020 | 130, 1.587.032 | 2, 25.356 | 1.612.388 |
| 136/2020 | 79, 10.425.139 | 1, 42.011 | 10.467.150 |
| 137/2020 | 297, 64.960.644 | 3, 1.409.153 | 66.369.797 |
| 35/2021 (dic. 2020) | 50, 942.879 | 1, 14.850 | 957.729 |
| 301/2025 | 74, 506.625.613 | 46, 515.032.673 | 1.021.658.286 |

(Las 20 órdenes de 2020 son las que la conversión con Tabula perdió dentro de expedientes cargados; la auditoría ya las había contado: 4,0 M.)

### El resto del CSV queda idéntico

- `agregar.py` verifica que, sacando las filas nuevas, el CSV es el de antes byte a byte (SHA-256 `dbe7b01f…c74a`).
- `git diff --numstat 6c079b6^ 6c079b6`: 13.136 líneas agregadas, 0 quitadas.

## Res. 301/2025: verificada a mano

La auditoría sospechaba que su extractor contaba subtotales, porque la fuente daba el doble que la base. **No es así:**
- el anexo (`dBeAk56B.pdf`) tiene 120 órdenes con OP distintas (9627 a 10045) y ninguna fila de subtotal;
- suman $1.021.658.286, igual que su línea "Total: $ 1.021.658.286,00";
- la base tenía 74 de esas 120 ($506.625.613). Las 46 que faltaban son de SERVICIOS CAPAZPE (18), TARGIZE (12), STADIUM ENTERPRISES (9), OSP (3), MEDIA 500 (3) y ST MEDIOS (1), y se agregan.

## 2023: los "duplicados probables" no son duplicados

La auditoría vio que `tabula-15.csv` y `tabula-90.csv` comparten 139 filas idénticas y estimó unas 1.149 filas repetidas entre archivos. El cruce con los anexos lo descarta:

- `tabula-15.csv` es completo la Res. 47/2023 (órdenes de enero) y `tabula-90.csv` es completo la Res. 88/2023 (febrero, expediente 2140-4657). Comparten filas porque hay órdenes mensuales que se repiten igual: mismo proveedor, mismo medio y mismo monto cada mes.
- Lo mismo pasa con otros pares: `tabula-25.csv` es la Res. 132/2023 y `tabula-98.csv` la Res. 167/2023.
- **Ningún archivo de 2023 repite a otro:** entre los que no tienen anexo, el que más se parece a otro comparte 78 de 164 filas.

**Lo que no tiene anexo publicado en 2023** son 16 archivos `tabula-*` enteros: 2.159 filas por $3.357.663.474 nominales (`base_sin_par_2023.csv`).
- 5 traen un expediente sin anexo en normas.gba.gob.ar: 2140-4929, 4964, 4965, 4969 y 4973/2023.
- Los otros 11 no traen expediente ni mes. Lo más probable es que sean de octubre a diciembre de 2023, que no tienen resolución publicada, pero no se puede confirmar.
- **No se tocan.** No hay evidencia de que estén mal, solo de que no hay anexo publicado para controlarlos.

## No se carga (pendiente)

| Resolución | Órdenes | Monto | Por qué | Qué haría falta |
|---|---:|---:|---|---|
| 79/2020 | 1 | 353.088 | el anexo no imprime total | comparar con el monto del artículo 1 de la resolución |
| 17/2021 | 158 | 30.766.762 | no concilia: el total impreso dice $76.422 más | ídem; puede faltar una orden en el anexo |
| 257/2022, 138/2023, 142/2023 | ? | ? | anexo ilegible | OCR |

- **Rescisiones** (251/2024 y 298/2025, 6 anexos de "compromisos sin devengar", "OP no prestadas" u "OP no coincidentes"): no se suman ni se restan. Restarlas de la pauta es una decisión de criterio pendiente.
- **Rectificaciones:** las 3 con anexo repiten el anexo de otra resolución (mismo SHA-256) y no cambian nada. Las demás no tienen anexo.
- **Resoluciones sin anexo con órdenes:** 35. Entre ellas hay 12 aprobaciones de gasto de 2020 (81, 141, 160-162, 164-168, 175 y 196/2020) cuyo detalle no está publicado; el resto son rectificaciones y resoluciones de personal.

## Validación y base

- **Tests:** `python -m unittest discover -s etl/tests`: 44 OK.
- **`validar.py`** (`validacion_antes.md` → `validacion_despues.md`): 11 atípicos, igual que antes; sin montos ≤ 0, fechas malformadas, jurisdicciones inválidas ni totales duplicados. Ninguna fila nueva tiene proveedor o medio vacío.
- **`build_db.py`:** 567.157 órdenes, 0 montos nulos. `check_build.py` pasa todo; la base pesa 189.923.328 bytes, en un solo chunk.
- **`npm run build`** y `npx tsc --noEmit`: OK.

## Impacto en el sitio

- **Portada:** órdenes 554.021 → 567.157; medios 15.728 → 15.941; proveedores 6.487 → 6.521. La nota de cobertura de PBA ya no dice que faltan resoluciones "sobre todo en 2020–2022", porque ahora están todas las que se pueden leer: dice que algunas resoluciones no publican el detalle o lo publican ilegible, sobre todo en 2020.
- **Vista inicial (PBA 2025):** pasa de 8.919 a 9.283 órdenes. En el ranking de PBA 2025, PARADOR DIEZ S.A. pasa al 1.er lugar entre los proveedores (SENTIDOS S.A. al 2.º) y TALAR PRODUCCIONES S.A. entra 5.º; entre los medios, WWW.ELDESTAPEWEB.COM sube al 3.º y AMERICA TV entra 5.º.
- **Ranking histórico de todas las jurisdicciones:** SENTIDOS S.A. entra 5.º entre los proveedores (sale EDITORIAL LA PAGINA S.A.) y Grupo Olmos entra 5.º entre los grupos (sale Grupo La Nación). Los medios no cambian de orden.
- **Número de orden (`#id`):** CABA, Nación y PBA conservan su número. Las filas nuevas toman los números 492.835 a 505.970, y las de Santa Fe corren el suyo en 13.136.

## Cómo reproducir

```bash
git show 6c079b6^:etl/data/pauta_oficial_unificado_v2.csv > /tmp/antes.csv
python -I etl/actualizacion_2026-10-15_pba/leer_anexos.py "<auditoria_fuentes>/crudos_2026-10-14" etl/actualizacion_2026-10-15_pba/pba_resoluciones_normas_gba.tsv /tmp/lectura
python -I etl/actualizacion_2026-10-15_pba/cruzar.py /tmp/antes.csv /tmp/lectura etl/actualizacion_2026-10-15_pba/pba_resoluciones_normas_gba.tsv /tmp/cruce
python -I etl/actualizacion_2026-10-15_pba/agregar.py /tmp/antes.csv /tmp/lectura /tmp/cruce --salida etl/data/pauta_oficial_unificado_v2.csv
python etl/build_db.py
```

- `leer_anexos.py` verifica el SHA-256 de cada PDF contra el manifest de la carpeta de crudos, y tarda unos 15 minutos.
- Requiere `pdfplumber` (probado con 0.11.9 y Python 3.10).

## Archivos de esta carpeta

| Archivo | Qué tiene |
|---|---|
| `leer_anexos.py`, `cruzar.py`, `agregar.py` | los scripts |
| `pba_resoluciones_normas_gba.tsv` | las 456 resoluciones de pauta de normas.gba.gob.ar, con resumen y anexos |
| `manifest_anexos.tsv` | los 427 anexos: URL, tamaño, SHA-256 y fecha de descarga |
| `anexos.tsv` | cada anexo leído: órdenes, suma, total impreso, si concilia y por qué no |
| `resoluciones.tsv` | **la tabla por resolución**: estado en la base, órdenes y montos, y qué se hizo |
| `bloques_base.tsv` | cada bloque de la base y su resolución |
| `conciliacion.tsv` | las 78 resoluciones cargadas |
| `base_sin_par_2023.csv` | las 2.159 filas de 2023 sin anexo publicado |
| `validacion_antes.md`, `validacion_despues.md` | `validar.py` antes y después |
| `manifest_textos_resoluciones.tsv` | etapa 2: los 3 textos oficiales bajados (URL, tamaño, SHA-256, fecha) |
| `conciliacion_etapa2.tsv`, `validacion_despues_etapa2.md` | etapa 2: conciliación y `validar.py` |
