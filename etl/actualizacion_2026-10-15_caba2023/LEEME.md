# CABA 2023 completo (15/10/2026)

Agrega a la base Cine, Medios Gráficos y Medios Vecinales de CABA 2023. BA Data los publicó solo en XLSX, y el ETL leía solo `*.csv`. El usuario aprobó la descarga y la carga el 2026-10-15; todavía no está publicado.

La fe de erratas para publicar está en [`CORRECCIONES.md`](../../CORRECCIONES.md). Este archivo es el detalle técnico para revisar la rama. Repite el método de [`etl/actualizacion_2026-10-15/`](../actualizacion_2026-10-15/LEEME.md).

## Resumen

| | Antes | Después |
|---|---:|---:|
| Órdenes | 549.184 | 554.021 (+4.837) |
| Total nominal | 336.412.132.476,05 | 339.066.379.833,99 (+2.654.247.357,94) |
| Total en pesos de abril de 2026 | 6.728.347,9 M | 6.743.610,5 M (+15.262,6 M, +0,23 %) |
| CABA 2023: órdenes | 19.906 | 24.743 |
| CABA 2023: nominal | 36.481.514.507,76 | 39.135.761.865,70 (+7,28 %) |
| CABA 2023: pesos de abril de 2026 | 209.778,2 M | 225.040,8 M |
| Medios normalizados | 15.719 | 15.728 |

Los totales salen de la tabla `meta` de `build_db.py`. Proveedores: 6.487, sin cambios, porque estos archivos traen solo el medio, igual que el resto de CABA desde 2018.

## Commits

| Commit | Qué hace |
|---|---|
| `947ad98` | `comun.leer_xlsx`, `extract_caba.XLSX_SIN_CSV`, tests (`test_xlsx.py`), `agregar.py` y el manifest de la descarga. No cambia datos. |
| `bc09507` | El CSV con las 4.837 filas nuevas. Solo agrega líneas. SHA-256 `dbe7b01fc41e9051972b237799ad8de24c475fe10ba0f3f1b02e5dfbb431c74a`. |
| `46c2e35` | `home.json` regenerado, cifras de la portada, README y AGENTS.md, y la evidencia de esta carpeta. |
| (último) | Esta nota y `CORRECCIONES.md`. |

## Fuente

Catálogo CKAN de `pauta-publicitaria`, consultado el 2026-10-15: 165 recursos, modificado el 21/07/2026, igual que el consultado el mismo día por la actualización anterior. Para 2023 hay CSV de Web, Radio, TV abierta, TV cable y Vía pública, que ya estaban en la base. Gráfica, Cine y Medios vecinales tienen solo XLSX.

| Archivo | Bytes | Last-Modified | SHA-256 |
|---|---:|---|---|
| `pauta-publicitaria-cine-2023.xlsx` | 11.175 | 20/03/2025 | `d3c0b944…0f7c8d37` |
| `pauta-publicitaria-medios-graficos-2023.xlsx` | 31.782 | 20/03/2025 | `6dd545a9…62541f10` |
| `BA_DATA_2023_Medios_Vecinales.xlsx` | 78.029 | 14/04/2025 | `e68cbe3e…90865ba1` |
| `BA DATA 2023 - Medios Vecinales.xlsx` | 78.029 | 09/08/2024 | `e68cbe3e…90865ba1` (idéntico) |

- URLs completas y SHA-256 en `manifest_descargas_caba_2023.tsv` y `manifest_crudos.tsv`.
- Los crudos están fuera del repo, en la carpeta de notas de la sesión: `side-session-notes\local_5cee6ed6-…\caba_2023_xlsx\crudos\`.
- Medios Vecinales está publicado dos veces con el mismo contenido byte a byte. Se carga la publicación vigente de 2025 (`BA_DATA_2023_Medios_Vecinales.xlsx`), del mismo lote que `BA_DATA_2023_Web.csv`, que ya está en la base.

## Método

### Lectura: el mismo criterio que los CSV por tipo

- `extract_caba._parse_pertype` ahora acepta `.xlsx`, que lee con `comun.leer_xlsx` (solo librería estándar: `openpyxl` no hace falta).
- Igual que en los CSV:
  - el tipo sale del nombre del archivo: `Cine`, `Medios Gráficos` y `Medios Vecinales`, los mismos valores que en 2018-2025;
  - columnas por encabezado (`_indices`): `fecha`, `medio`, `monto_pesos_ars` o `importe_pesos_ars`;
  - `medio` por `limpiar_str`, que colapsa los espacios;
  - `proveedor` vacío, como en todo CABA desde 2018.
- **Montos.** Las celdas de importe son numéricas: se toma el valor guardado (`7427626.3399999999` → 7.427.626,34), sin pasar por el parser de texto, como hace `extract_pba._parse_excel_2025`. Así no hay ambigüedad de separador ni riesgo de ×1000. Solo una celda de texto pasaría por `parser_montos`, y no hay ninguna.
- **Fechas.** Son números de serie de Excel con formato `yyyy-mm-dd`. Se convierten a fecha y pasan por `normalizar_fecha`.
- `extraer()` lee solo los XLSX de `XLSX_SIN_CSV`, y solo si su SHA-256 coincide. Los demás XLSX del portal repiten un CSV. Se ordenan con los CSV de la carpeta del año por nombre.
- **La lectura de los CSV no cambia.** Releídos con el extractor nuevo, los 4 CSV de CABA 2025 dan exactamente las mismas líneas que están en la base.

### Inserción: donde la pone el ETL

`agregar.py` usa las funciones de `etl/actualizacion_2026-10-15/regenerar.py`:
- `posprocesar`, que hace lo mismo que `unificar.py` después de extraer;
- `a_lineas`, que escribe las líneas igual que `unificar.py`.

Las filas van en el bloque de CABA 2023, en el orden de `extract_caba.extraer()`:

1. `BA_DATA_2023_Medios_Vecinales.xlsx` (nuevo)
2. `BA_DATA_2023_Web.csv`
3. `pauta-publicitaria-cine-2023.xlsx` (nuevo)
4. `pauta-publicitaria-medios-graficos-2023.xlsx` (nuevo)
5. radios, tv-abierta, tv-cable y via-publica 2023

El script exige que ese orden sea el mismo con `Path` de Windows (sin distinguir mayúsculas, donde se generó el CSV) y de POSIX. Una corrida completa del ETL con estos crudos da el mismo CSV.

## Conciliación

"Total oficial": suma exacta (Decimal) de la columna de importe de la planilla. Se lee del XML de la hoja, sin el lector del ETL, con el valor guardado de cada celda, y se redondea al centavo una sola vez. Las planillas no traen fila de total.

| Archivo | Filas | `#id` | Total cargado | Total oficial | Dif. |
|---|---:|---|---:|---:|---:|
| Medios Vecinales | 3.826 | 170.615–174.440 | 805.453.597,20 | 805.453.597,20 | 0,00 |
| Cine | 56 | 182.040–182.095 | 141.569.332,46 | 141.569.332,46 | 0,00 |
| Medios Gráficos | 955 | 182.096–183.050 | 1.707.224.428,28 | 1.707.224.428,28 | 0,00 |

En pesos de abril de 2026: Medios Vecinales 4.631,6 M, Cine 814,1 M y Medios Gráficos 9.817,0 M.

### Controles

- **Fila por fila** (`control_por_fila`). Cada línea cargada se compara con su fila de la planilla, leída sin el ETL:
  - fecha: número de serie contado desde 1899-12-30;
  - medio: con los espacios colapsados;
  - monto: el valor guardado, redondeado al centavo.
  - Coinciden las 4.837. Ninguna trae proveedor ni resolución.
- **Ninguna fila se descarta.** Filas cargadas = filas con importe en la planilla. Todas las fechas son de 2023.
- **Montos.** Van de 15.422 a 14.299.985,70. No hay montos con más de 2 decimales, ni filas de total o subtotal.
- **Repetidas exactas.** Mismo medio, fecha y monto, tal como las publica la fuente: 20 en Medios Vecinales y 5 en Gráficos. Se mantienen, como en 2024 y 2025.
- **Magnitudes.** Coherentes con los años vecinos, en nominal:

  | Tipo | 2022 | 2023 | 2024 |
  |---|---:|---:|---:|
  | Cine | 119 M (57) | 142 M (56) | 367 M (53) |
  | Gráfica | 752 M (941) | 1.707 M (955) | 3.409 M (546) |
  | Medios vecinales | 288 M (3.777) | 805 M (3.826) | 2.571 M (4.023) |

### El resto del CSV queda idéntico

- Control del script (`verificacion.txt`): las 549.184 filas anteriores siguen idénticas byte a byte y en el mismo orden. SHA-256 `0d27bfc3…85aa`.
- **`git diff -U0 485d51c bc09507 -- etl/data/pauta_oficial_unificado_v2.csv`:** 4.837 líneas agregadas y 0 quitadas. Todas son de los 3 XLSX.

## Validación y base

- **Tests:** `python -m unittest discover -s etl/tests`, 44 OK (40 + 4 de `test_xlsx.py`).
- **`validar.py`** (`validacion_antes.md` → `validacion_despues.md`):
  - los mismos 11 atípicos, con otro `#id`;
  - sin montos ≤0, fechas malformadas ni jurisdicciones inválidas;
  - "proveedor nulo" sube en 4.837.
- **`build_db.py`:** 554.021 órdenes y 0 montos nulos. `check_build.py`: todo OK.
- **`npm run build` y `npx tsc --noEmit`:** OK.
- **`home.json`:**
  - La vista inicial (PBA 2025) no cambia.
  - Cambian el ranking global de grupos y el Grupo Clarín del generador: 536.541 M → 537.808 M; CABA 2023 pasa de 14.459 M a 15.726 M.

## Impacto en el sitio

- **Rankings.** De las 223 combinaciones de `rankings_cache`, solo 2 cambian de orden, las dos de 2023 con todas las jurisdicciones (`'*'`, 2023):
  - grupos: Grupo América entra 5.º (4.814,4 M) y sale Grupo Infobae (4.796,2 M);
  - medios: CRONICA pasa al 4.º lugar (6.110,3 M → 6.892,7 M) y WWW.YOUTUBE.COM al 5.º (6.562,6 M).
  - Las demás, incluidos el histórico global, CABA y CABA 2023, solo cambian de monto. Clarín: +1.267 M, de 161.747 M a 163.014 M. También suben Grupo Clarín, La Nación, Indalo, América y Olmos en CABA 2023.
- **Nombres visibles.** El nombre de display es la grafía más frecuente.
  - 31 medios cambian de grafía. Casi todos solo pasan a mayúsculas, como escriben estas planillas: `www.mibelgrano.com.ar` → `WWW.MIBELGRANO.COM.AR`.
  - Otros toman una grafía que la Ciudad ya usaba en otros años:
    - `PALERMO'S` → `PALERMO S` (así desde 2017);
    - `www.hoornik.com.ar` → `HOORNIK`;
    - `DIARIO EPOCA ***` → `DIARIO EPOCA`;
    - `LA VOZ DE CORDOBA` → `LA VOZ DE CÓRDOBA`.
  - Es la regla de siempre: no se tocó.
- **9 medios nuevos**, todos de Gráfica: DIARIO EL LIBERAL DE SANTIAGO DEL ESTERO, TRIBUNA DEL PUEBLO LUJÁN, DIARIO NORTE 24, DIARIO SUR 24, EL POPULAR DE OLAVARRIA, REVISTA PUERTO NEGOCIOS, NUEVO DIARIO SALTA, EL DIA DE GUALEGUAY y SEMANARIO GUALEGUAY.
- **Número de orden (`#id`):**

  | Filas | Qué pasa con el `#id` |
  |---|---|
  | CABA 2003-2022 (1 a 170.614) | no cambia |
  | CABA 2023 Web | +3.826 |
  | CABA 2023 Radio, TV y Vía pública; CABA 2024-2025; Nación; PBA; Santa Fe | +4.837 |

- **Cifras a mano:**
  - portada: 554.021 pautas y 15.728 medios;
  - README y README.en: CABA 224.677, total 554.021;
  - AGENTS.md.
  - `DISPONIBILIDAD`, `ANIOS_PILLS` y las barras de cobertura no cambian: CABA 2023 no estaba marcado como parcial.

## Decisiones tomadas por defecto

- **`archivo_origen`** es el nombre del XLSX, como el ETL pone el nombre del archivo leído (igual que `2dosemestre2012_01_prov_rubro.pdf` de Nación).
- **Medios Vecinales:** se usa la publicación de 2025. Las dos versiones son idénticas, así que no cambia ningún dato.
- **Orden de las filas:** el de `extraer()`. Para que corrieran menos `#id` se podían poner al final del bloque de CABA 2023, pero entonces el CSV dejaba de ser el que produce el ETL. Se mantuvo el criterio de la actualización anterior.

## Cómo reproducir

```bash
git show 485d51c:etl/data/pauta_oficial_unificado_v2.csv > /tmp/antes.csv
python -I etl/actualizacion_2026-10-15_caba2023/agregar.py /tmp/antes.csv "<crudos>" \
  --salida etl/data/pauta_oficial_unificado_v2.csv --informe /tmp/informe
python etl/build_db.py
```

- `<crudos>` es la carpeta con `manifest_descargas.tsv`; este archivo es `manifest_descargas_caba_2023.tsv`, renombrado. Lleva una subcarpeta por archivo: `0001/…`, `0002/…`.
- Cualquier copia sirve: el script verifica el SHA-256 de cada XLSX contra el manifest y contra `XLSX_SIN_CSV`.

## Archivos de esta carpeta

| Archivo | Qué tiene |
|---|---|
| `agregar.py` | el script |
| `manifest_descargas_caba_2023.tsv` | la descarga: los 4 XLSX, con URL, tamaño, SHA-256 y Last-Modified |
| `manifest_crudos.tsv` | los 3 XLSX cargados |
| `conciliacion.tsv` | la conciliación por archivo |
| `verificacion.txt` | control de las filas que no cambian y del orden |
| `validacion_antes.md`, `validacion_despues.md` | `validar.py` antes y después |
