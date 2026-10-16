# PROMPT PARA EJECUCIÓN (modelo barato)

> Prompt autónomo. No requiere contexto previo. Ejecuta los scripts de re-unificación
> de datos de pauta oficial y verifica el resultado.

## Contexto mínimo
El repo `Repositorio DatosPautaOficial` contiene un ETL en `etl/` que reconstruye
`pauta_oficial_unificado.csv` desde los datos crudos. Los extractores ya están escritos
en `etl/extractores/`. Tu tarea es **ejecutarlos, verificar el output y dejarlo listo**.

## Requisitos
- Python 3.8+ y las dependencias `openpyxl` (solo para el Excel de PBA 2025) y `pdfplumber`
  (para los PDFs oficiales de los pivots de Nación, ver abajo):
  ```
  pip install openpyxl pdfplumber
  ```
- Los datos crudos deben estar en:
  `C:\Users\IvanGomezD\Desktop\0\ClaudeCoWork\DatosPautaOficial\`
  (subcarpetas `Datos crudos Pauta Oficial\`, `PBA Nuevos datos sin curar\`,
   y el archivo `santa_fe_curado.csv`).
  Si están en otra ruta, exportá la variable de entorno antes de correr:
  ```
  set DATOS_CRUDOS_BASE=D:\ruta\a\DatosPautaOficial      (Windows CMD)
  ```
- **PDFs oficiales de los pivots de Nación 2009, 2010 y 2012.** El texto "(nuevo v2)" de esos
  pivots viene corrido en las páginas sin encabezado: de ahí no se puede leer el rubro
  (`tipo_de_medio`) ni el mes (`fecha`) de cada monto. Si el PDF está en la carpeta del año,
  junto a su CSV, el extractor lo lee por coordenadas y concilia cada fila y cada columna.
  Si falta, si su SHA-256 no es el revisado o si no concilia, avisa y lee el texto: el rubro
  queda vacío y el mes sale de la posición, que en 2009 está mal en cerca de la mitad de las filas.
  `archivo_origen` sigue siendo el nombre del CSV. Se bajan de
  `https://www.argentina.gob.ar/sites/default/files/<pdf>`:

  | Carpeta `Nacion\` | PDF | SHA-256 | Reemplaza al texto |
  |---|---|---|---|
  | `2009\` | `pauta_por_proveedor_con_iva_2009.pdf` | `8fd2e1d3…c1c3b4` | `(nuevo v2) Pauta_por_Proveedor_conIVA-_-2009-mayo-oct.csv` |
  | `2009\` | `pauta_por_proveedor_coniva_nov_dic_2009.pdf` | `8fd88ffc…56098b` | `(nuevo v2) Pauta_por_proveedor_conIVA_nov_dic_2009.csv` |
  | `2010\` | `pauta_por_proveedor_coniva_ene_jun_2010.pdf` | `e9d500b6…59a783` | `(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv` |
  | `2010\` | `segundo_semestre_prov_rubro_2010.pdf` | `e0bee281…3aead3` | `(nuevo v2)segundo_semestre_prov_rubro-2010.csv` |
  | `2012\` | `inversion_1er_semestre_2012_proveedor_rubro.pdf` | `a1bd5110…1c5448` | `inversion_1er_Semestre_2012_proveedor_rubro.csv` |

  Los SHA-256 completos están en `PDF_DE_PIVOT` (`etl/extractores/extract_nacion.py`).
  En el log, cada PDF leído dice "se lee el PDF oficial, que concilia".
- **XLSX de CABA 2023.** Cine, Medios Gráficos y Medios Vecinales 2023 se publicaron solo en
  XLSX. El extractor los lee si están en la carpeta `CABA\2023\`, junto a los CSV, y si su
  SHA-256 es el revisado (`XLSX_SIN_CSV` en `etl/extractores/extract_caba.py`). Si falta
  alguno, CABA 2023 sale incompleto. Se bajan de
  `https://cdn.buenosaires.gob.ar/datosabiertos/datasets/secretaria-de-medios/pauta-publicitaria/<xlsx>`:
  `BA_DATA_2023_Medios_Vecinales.xlsx`, `pauta-publicitaria-cine-2023.xlsx` y
  `pauta-publicitaria-medios-graficos-2023.xlsx`. Los demás XLSX del portal repiten un CSV:
  no hace falta bajarlos, y el extractor no los lee.

## Orden de ejecución (desde la raíz del repo)
0. **Tests de los extractores** (montos y pivots; no necesitan los crudos; los del PDF usan
   los dos PDFs oficiales de `etl/tests/fixtures/`):
   ```
   python -m unittest discover -s etl/tests
   ```
1. **Generar el CSV unificado:**
   ```
   python etl/unificar.py
   ```
   Crea `etl/data/pauta_oficial_unificado_v2.csv`.
2. **Validar:**
   ```
   python etl/validar.py
   ```
   Crea `REPORTE_VALIDACION.md` en la raíz del repo.

(Para debug individual cada extractor corre solo, p.ej. `python etl/extractores/extract_caba.py`.)

## Regla de agrupabilidad (importante)
Toda fila queda agrupable por `medio` o por `proveedor` (nunca ambos nulos):
- **Vía Pública** se colapsa a un único `medio = "Via Publica"` (se elimina la distinción de
  soporte: GRANDES FORMATOS, PANTALLAS LED, etc.).
- **CABA 2006/2007**, cuyo único dato identificable es el "tipo de producto" (Spot, Avisos
  Gráfica, etc.), vuelca ese concepto a `medio` para poder agruparlo.

## Conteos esperados (referencia para verificar que salió bien)
Total ≈ **506.700 filas**, repartidas aproximadamente así:

| Jurisdicción | Filas aprox. | Años |
|---|---|---|
| CABA | ~207.700 | 2003–2024 |
| Nación | ~193.800 | 2009–2012, 2014–2022 (sin 2013) |
| Santa Fe | ~61.200 | 2008–2023 |
| PBA | ~44.000 | 2020–2025 |

En la salida de `unificar.py` (bloque "REPORTE DE COBERTURA"):
- TOTAL filas entre 500.000 y 512.000 → OK.
- Si alguna jurisdicción da **0** → falló su ruta de crudos; revisar.
- Debe aparecer "Filas con medio rellenado desde tipo_de_medio: ~11.800".

En `REPORTE_VALIDACION.md`:
- `montos <=0 o no numericos: 0` ✅
- `fechas malformadas: 0` ✅
- `jurisdicciones invalidas: ninguna` ✅
- `ambos nulos (proveedor Y medio): 0` ✅  (gracias a la regla de agrupabilidad)
- cobertura de `medio` ≈ 97% (el ~3% restante son filas con proveedor pero sin medio,
  p.ej. los pivots por rubro de Nación: agrupan por proveedor, está OK).

## Qué hacer si falla un script
- `ModuleNotFoundError: openpyxl` → `pip install openpyxl`.
- `no existe <ruta>` (en el log) → la base de crudos está mal; fijá `DATOS_CRUDOS_BASE`.
- `[Santa Fe] ... no se encontro santa_fe_curado.csv` → conseguí ese archivo y ponelo en la
  base de crudos; **no** intentes re-extraer los PDFs de Santa Fe.
- Cualquier traceback → reportalo completo y **no** continúes con el rename del paso final.

## Paso final (solo si todo lo anterior dio OK)
`build_db.py` lee directamente `etl/data/pauta_oficial_unificado_v2.csv` (es el
CSV canónico y el único versionado). Regenerá la base:
```
python etl/build_db.py
```
Verificá que `etl/build/pauta.sqlite` tenga las filas esperadas en la tabla `orders`
y que `public/data/home.json` se haya regenerado (es el seed de la portada y SÍ se
commitea).

## Qué commitear y qué NO
- **Commitear:** `etl/extractores/*.py`, `etl/unificar.py`, `etl/validar.py`,
  `etl/data/pauta_oficial_unificado_v2.csv` (canónico actualizado),
  `public/data/home.json`, `REPORTE_VALIDACION.md`, `etl/PROMPT_EJECUCION.md`.
- **NO commitear:** datos crudos, `__pycache__/`, backups, `pauta.sqlite`,
  chunks `pauta.sqlite.*`, `config.json`, `search.json`, `grupos.json`
  (artefactos reproducibles, ya gitignored).
