# Correcciones de datos

Acá registramos cada corrección de los datos publicados en Datos Pauta Oficial: qué cambió, por qué y con qué evidencia.

## 15 de octubre de 2026

Revisamos, celda por celda, los datos cargados contra los archivos oficiales de cada organismo. Encontramos errores **de carga, no de las fuentes**: los archivos oficiales estaban bien, pero nuestro programa había leído mal algunos. Los corregimos y, además, sumamos datos nuevos.

**En números:**
- El total histórico, en pesos de abril de 2026, baja de **$7,86 billones a $6,73 billones (−14,4 %)**.
- Las correcciones solas lo bajan un 17 %. Los datos nuevos lo suben un 2,6 %.
- Cambian solo CABA (2016, 2017 y 2025) y Nación (2009, 2010 y 2012). PBA y Santa Fe no cambian.

| | Qué cambió | Efecto (pesos de abril de 2026) |
|---|---|---:|
| 1 | CABA 2016 y 2017: 30 montos estaban multiplicados por mil | −$904.200 millones |
| 2 | Nación 2010 y 1er semestre 2012: el total de cada proveedor se contaba como una orden más | −$430.797 millones |
| 3 | Nación 2009: montos en el mes equivocado, montos perdidos y filas falsas | +$319 millones |
| 4 | Nación 2do semestre 2012: faltaba, se agrega | +$177.727 millones |
| 5 | CABA 2025: se agrega (parcial) | +$28.674 millones |

### 1. CABA 2016 y 2017: 30 montos multiplicados por mil

**Qué pasó.**
- Los archivos oficiales de CABA escriben el importe con punto decimal: `1160879.808` significa $1.160.879,81.
- En 30 celdas con tres decimales, el programa tomó ese punto como separador de miles y cargó $1.160.879.808.

**Evidencia.**
- [`pauta-publicitaria-2016.csv`](https://cdn.buenosaires.gob.ar/datosabiertos/datasets/pauta-publicitaria/pauta-publicitaria-2016.csv) (BA Data, sin cambios desde 2019) suma **$657.508.065,89**; la base sumaba $6.911.727.812,68.
- [`pauta-publicitaria-2017-total.csv`](https://cdn.buenosaires.gob.ar/datosabiertos/datasets/pauta-publicitaria/pauta-publicitaria-2017-total.csv) suma **$1.112.636.775,94**; la base sumaba $2.326.532.584,02.
- Ahora la base coincide al centavo con los dos archivos.

**Efecto.**
- Salen $7.468 millones nominales.
- Afectaba, entre otros, a IMPREBA S.A. (Diario Popular, 6 órdenes), Eventos Producciones (Canal 26), Arte Radiotelevisivo Argentino (TN), Fox, Alta Densidad (Crónica), Radio Continental, Editorial Perfil y Radio Mitre.
- IMPREBA S.A. figuraba como el proveedor que más pauta recibió en la historia. Corregido, es el décimo.
- La lista de los 30 montos, cada uno con su línea en el archivo oficial y el importe tal como está escrito, está en [`cambios_caba_x1000.csv`](etl/actualizacion_2026-10-15/cambios_caba_x1000.csv).

### 2. Nación 2010 y primer semestre de 2012: totales contados como órdenes

**Qué pasó.**
- Para estos períodos, el Gobierno nacional publicó planillas "por proveedor y rubro": una fila por proveedor, con lo pagado en cada rubro (TV, radio, gráfica, etc.) y una última columna con el total.
- El programa leía una versión en texto de esos PDF en la que muchas páginas venían desalineadas.
- Por eso cargó el total de 2.586 proveedores como si fuera una orden más, y lo que recibieron se contaba dos veces.
- En esas planillas también estaba corrido el rubro de 2.234 montos.

**Evidencia.**
- Ahora leemos los PDF oficiales directamente, con la posición exacta de cada número.
- Cada fila suma su total y cada columna suma el total de su rubro.
- Los tres semestres coinciden al centavo con el "Total general" publicado:

| Semestre | Total del PDF oficial | Lo que sumaba la base |
|---|---:|---:|
| enero-junio 2010 | $244.128.145,44 | $470.535.967,45 |
| julio-diciembre 2010 | $410.232.355,85 | $759.809.574,44 |
| enero-junio 2012 | $420.294.469,28 | $817.199.119,86 |

**Efecto.**
- Salen $973 millones nominales.
- Entra un proveedor que se había descartado por error porque su nombre empieza con "TOTAL": TOTAL PUBLIVIA SA, $70.785.

### 3. Nación 2009: montos en el mes equivocado

**Qué pasó.**
- Las planillas de 2009 están por mes.
- Por el mismo problema de lectura, 1.250 montos quedaron en otro mes. Por ejemplo, mayo sumaba $40,7 millones de más y octubre $35,5 millones de menos.
- Se perdieron 10 montos (proveedores sin medio y empresas cuyo nombre empieza con "TOTAL").
- Entraron 12 filas falsas de $9: era el encabezado de cada página.

**Evidencia.**
- Ahora cada monto es el del PDF oficial.
- Cada mes coincide con el total del PDF, salvo centavos: la propia planilla calculó su fila de totales antes de redondear cada monto, y la diferencia mayor es de 41 centavos.

**Efecto.**
- El año suma $521.067 más: los montos recuperados, menos las filas falsas.
- Cambia, sobre todo, la distribución por mes. El sitio no muestra el mes, pero el CSV del repositorio sí.

### 4. Nación, segundo semestre de 2012: se agrega

**Qué pasó.** Faltaba: se publicó solo en PDF y no se había cargado.

**Qué se agrega.**
- [`2dosemestre2012_01_prov_rubro.pdf`](https://www.argentina.gob.ar/sites/default/files/2dosemestre2012_01_prov_rubro.pdf): 1.395 montos de 1.093 proveedores, por **$518.719.290,15**.
- Coincide al centavo con el "Total general" del PDF.

### 5. CABA 2025: se agrega, pero está incompleto

**Qué se agrega.**
- El 20 de julio de 2026, BA Data publicó los datos de 2025 de Medios vecinales, Radio, Gráfica y Cine ([dataset](https://data.buenosaires.gob.ar/dataset/pauta-publicitaria)).
- Son 9.963 órdenes por $22.619 millones nominales.
- Cada archivo coincide al centavo con el oficial.

**Atención.**
- Todavía no se publicaron **TV abierta, TV cable, Web ni Vía pública**, que en 2024 fueron el 86 % de la pauta de CABA.
- Por eso el total de CABA 2025 no se puede comparar con el de 2024.

### Control externo

La Nación publicó los totales por semestre de la pauta nacional, con datos de Jefatura de Gabinete, Poder Ciudadano y Fundación LED. Después de corregir, la base coincide con esa tabla:

| Semestre | La Nación | Antes | Ahora |
|---|---:|---:|---:|
| 2º 2009 | $206.630.089 | $165.404.452 | $206.625.128 |
| 1º 2010 | $244.128.152 | $470.535.967 | $244.128.145 |
| 2º 2010 | $410.232.369 | $759.809.574 | $410.232.356 |
| 1º 2012 | $420.294.480 | $817.199.120 | $420.294.469 |
| 2º 2012 | $518.719.294 | (faltaba) | $518.719.290 |

- La Nación redondea a pesos cada proveedor; por eso hay diferencias de pocos pesos.
- En el 2º semestre de 2009, la diferencia de $4.961 es entre La Nación y el propio PDF oficial. La base sigue al PDF.

### Otros cambios que se ven en el sitio

- **Rankings históricos.** Con estos errores corregidos, el top 5 cambia:
  - Proveedores: Televisión Federal (Telefe), Arte Radiotelevisivo Argentino, Telearte (Canal 9), América TV y Editorial La Página.
  - Medios: Vía pública, Canal 13, Telefe, Clarín y Canal 9.
- **Número de orden (#).** Cada orden se numera según su posición en la base.
  - Las órdenes de CABA 2003-2024 conservan su número.
  - Las de Nación, PBA y Santa Fe cambian de número.

### Lo que sabemos y todavía no corregimos

- **Nación, primer semestre de 2013.**
  - La fuente que usamos para 2013 informa importes **sin IVA** ("importe neto"). El resto de Nación está con IVA.
  - Contra el PDF oficial del semestre, la base suma $87,9 millones menos.
  - Estamos evaluando cómo corregirlo sin perder el detalle por orden.
- **Nación, junio de 2009.** No figura en ninguna publicación oficial.
- **CABA 2023.** Gráfica, Cine y Medios vecinales se publicaron solo en Excel y todavía no están en la base.

### Cómo verificarlo

En [`etl/actualizacion_2026-10-15/`](etl/actualizacion_2026-10-15/LEEME.md) están:
- cada archivo oficial usado, con su dirección y su huella digital (SHA-256);
- la conciliación de cada archivo contra su total oficial;
- cada fila que cambió;
- el programa que hizo los cambios.

El resto de la base quedó igual, fila por fila.
