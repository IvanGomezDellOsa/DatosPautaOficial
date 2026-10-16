# Santa Fe: corrección de errores de carga (preparada el 15/10/2026)

**Estado: aplicada y publicada el 16/10/2026** con el OK del usuario, sin `grafica2013`.
`grafica2013` se aplicó después, el mismo 16/10/2026, también con el OK del usuario (ver más abajo).

- El script exige como entrada el CSV revisado, previo a la carga de PBA (SHA-256
  `dbe7b01f…`). Se corrió sobre ese CSV y dio exactamente la salida de `verificacion.txt`.
- Después se reinsertaron, en su mismo lugar, las 13.136 filas de PBA agregadas ese día, que
  son contiguas y van antes del bloque de Santa Fe.
- Resultado: 569.783 filas, SHA-256
  `b6b492c894e3ba76d520fc099da30b8bfbf8143a409fab5715e6d8962b79409f`. Las filas fuera de Santa Fe
  quedaron idénticas a las de la versión con PBA.

El comando original, sobre el CSV previo a PBA, era:

```bash
git show HEAD:etl/data/pauta_oficial_unificado_v2.csv > /tmp/antes.csv
python -I etl/actualizacion_2026-10-15_santafe/corregir.py /tmp/antes.csv \
  "<auditoria_fuentes>/crudos_2026-10-14" --salida etl/data/pauta_oficial_unificado_v2.csv
python etl/build_db.py
```

`<auditoria_fuentes>` es la carpeta de la auditoría de fuentes (ver `AGENTS.md`, "Crudos
descargados"). El script verifica el SHA-256 de cada PDF contra su `manifest_descargas.tsv`.
Requiere `pdfplumber`.

## Qué corrige

| Corrección (`--aplicar`) | Archivo | Filas | Nominal | Causa |
|---|---|---:|---:|---|
| `radio2008` | Radio 2008 (II).pdf | −564 | −4.731.056,35 | El portal publica dos PDF con el mismo cuadro y el curado cargó los dos |
| `sf2011` | Gráfica, Internet, Radio y TV 2011 | +1.930 | +25.180.625,65 | El curado cargó solo los primeros medios de cada PDF |
| `tv2013` | TELE 2013.pdf | +107 | +7.624.214,57 | Igual: faltaban 10 canales |
| `vp2017` | Vía pública 2017.pdf | +8 | +2.396.163,00 | Faltaba PUBLICIDAD SARMIENTO |
| `internet2016` | Informe inversión publicitaria internet 2016.pdf | +1.125 | +10.631.199,48 | No estaba: el PDF usa una fuente sin mapa Unicode |
| `chicos` | Vía pública 2009, Radios 2015, radio 2016 | +20 | +36.303,00 | Octubre 2009 de 2 medios (el PDF pega "Septiembre" y "Octubre"); FM 88.9 PASION de María Luisa (localidad de dos palabras) |
| **Total** | | **554.021 → 556.647** | **+41.137.449,35** | |

No se aplica por defecto `grafica2013` (Gráfica 2013, +772 filas, +35.163.104,46): el detalle
concilia al centavo con su propia fila de totales, pero suma **1.925,25 más** que el resumen
oficial por tipo de medio, todo en julio (3.861.918,30 contra 3.859.993,05). No hay forma de saber
con la fuente qué renglón difiere.

**Aplicada el 16/10/2026 con el OK del usuario**, que aceptó esa diferencia: el detalle es una
planilla de Calc hecha a mano (13/04/2016, 10:34) y el resumen, un reporte del sistema generado 33
minutos antes; las demás planillas de 2013 concilian al centavo. Se corrió `corregir.py` sobre el
CSV previo a PBA con y sin `grafica2013`, y las 772 filas de diferencia, contiguas, se insertaron
en el CSV vigente en el mismo lugar (después de la última fila de Gráfica 2013 que ya estaba). El
resto del CSV quedó idéntico. Santa Fe pasa de 63.813 a 64.585 órdenes y 2013, de 2.538 a 3.310.

## Método

- **Lectura geométrica** de cada PDF: cada monto va a la columna cuyo título empieza a su
  izquierda; las tablas partidas por columnas (2013) se unen por orden de fila.
- **Control de cada fila** contra su total impreso y de cada columna contra la fila de totales.
  En 2011, 6 filas tienen el total impreso a 1 centavo de la suma de sus meses: la planilla de
  origen redondeó cada celda. Se cargan las celdas como están impresas.
- **Emparejamiento con la base**: cada medio ya cargado tiene que estar, con todos sus montos y
  meses, en un solo renglón del PDF. Si alguno no aparece, no se carga nada.
- **Filas que ya están: idénticas byte a byte y en el mismo orden** (`verificacion.txt`). Las
  nuevas van al final del bloque de su archivo; Internet 2016, al final del CSV, junto a Estática
  2016, el otro archivo de 2016 que el curado había puesto al final.
- **Nombres de los medios nuevos**: "columna izquierda (columna derecha)", como el resto del
  archivo ("Medio (Localidad)" en 2011-2013, "Localidad (Medio)" en 2015-2016). Si la localidad ya
  está en el nombre, va solo el nombre. La regla reproduce los nombres ya cargados en 9 de los 10
  archivos (`conciliacion.tsv`, columna nota); la excepción es Vía pública 2017, donde el curado
  partió la primera palabra como si fuera localidad y el PDF no tiene esa columna: el medio nuevo
  va con el texto del PDF, "PUBLICIDAD SARMIENTO".
- **Internet 2016**: cada letra y dígito del PDF está reemplazado por otro signo, siempre el mismo
  ("30.240,00" se lee ")*+,-*.**"). La tabla `MAPA_2016` se armó con los títulos de columna y se
  verificó contra la imagen de las 5 páginas, incluidos los acentos que la fuente escribe graves
  ("San Josè", "Constituciòn"). Los montos se controlan con 132 filas que cuadran con su total y
  con el resumen oficial, mes por mes.

## Conciliación con los resúmenes oficiales

| Año | Tipo | Antes | Después | Resumen oficial | Dif. |
|---|---|---:|---:|---:|---:|
| 2008 | todos ¹ | 30.013.851,92 | 25.282.795,57 | 25.282.795,60 | −0,03 |
| 2009 | todos ¹ | 29.274.242,70 | 29.290.267,70 | 29.290.267,73 | −0,03 |
| 2011 | todos ¹ | 34.229.182,37 | 59.409.808,02 | 59.409.807,95 | +0,07 |
| 2013 | TV | 33.259.509,59 | 40.883.724,16 | 40.883.724,16 | 0,00 |
| 2015 | Radio | 37.940.933,28 | 37.947.573,28 | 37.947.573,28 | 0,00 |
| 2016 | Internet | 0,00 | 10.631.199,48 | 10.631.199,48 | 0,00 |
| 2016 | Radio | 26.817.720,05 | 26.831.358,05 | 26.831.358,05 | 0,00 |
| 2017 | Vía pública | 71.630.370,22 | 74.026.533,22 | 74.026.533,22 | 0,00 |
| 2013 | Gráfica (aplicada aparte el 16/10) | 3.307.717,41 | 38.470.821,87 ² | 38.468.896,62 | +1.925,25 |

¹ 2008, 2009 y 2011 no tienen resumen por tipo de medio: el oficial es por mes, todos los tipos
juntos. Los centavos de diferencia son redondeo de la fuente (en 2009 sus propios meses suman 1
centavo menos que su total; en 2011 los totales impresos de los PDF por tipo ya suman 6 centavos
más que el resumen). En 2011 el reparto por mes del resumen no coincide con el de los PDF por tipo
(hasta 27 mil pesos en un mes), aunque el año cierra.
² Con `--aplicar grafica2013`.

## Archivos

| Archivo | Qué tiene |
|---|---|
| `corregir.py` | el script |
| `conciliacion.tsv` | por archivo: filas y total antes y después, total del PDF |
| `conciliacion_resumen_oficial.tsv` | por año y tipo, contra el resumen oficial |
| `medios_por_renglon.tsv` | cada renglón del PDF: el medio ya cargado o el nombre nuevo, y cuántas celdas entran |
| `manifest_crudos.tsv` | los PDF usados, con URL y SHA-256 |
| `verificacion.txt` | SHA-256 de entrada, salida y de las filas que no cambian |

## Pendiente después de aplicar

- `build_db.py`, `validar.py`, tests y `npm run build`.
- Cifras escritas a mano: hero y encabezado de `index.astro`, README, README.en y `AGENTS.md`
  (554.021 → 556.647 órdenes).
- Entrada en `CORRECCIONES.md`.
- `orders.id`: las filas de Santa Fe posteriores a Radio 2008 cambian de número.
