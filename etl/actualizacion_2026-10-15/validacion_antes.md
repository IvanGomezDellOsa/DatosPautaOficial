# Reporte de validacion — pauta_oficial_unificado

Archivo validado: `etl/data/pauta_oficial_unificado_v2.csv` de 8241b17, antes de esta actualización (SHA-256 65181475…)

**Total de filas:** 540413


## Filas por jurisdiccion

- Nación: 225367
- CABA: 209877
- Santa Fe: 61187
- PBA: 43982

## Cobertura de proveedor / medio

- proveedor nulo: 215506 (39.9%)
- medio nulo: 45253 (8.4%)
- ambos nulos (proveedor Y medio): 0 (0.0%)  ← deberian ser solo Via Publica

## Integridad de monto

- ✅ todos los montos son numericos y > 0

## Integridad de fecha

- ✅ todas las fechas son ISO (YYYY-MM-DD) o vacias

## Jurisdicciones / años fuera de rango

- jurisdicciones invalidas: ninguna ✅
- años fuera de 2003-2027: ninguno ✅

## Top-10 valores de `medio` que parecen TIPOS (revisar)

- `CANAL METRO`: 3389
- `CANAL 13`: 3077
- `AMBITO FINANCIERO`: 2979
- `PAGINA 12`: 2974
- `CANAL 9`: 2364
- `TN`: 2193
- `CANAL 26`: 2144
- `DIARIO POPULAR`: 2113
- `CRONICA`: 2081
- `C5N`: 1943

## Montos atipicos (solo informa: no se descarta ni modifica ninguna fila)

- ⚠️ ordenes >= 1000x la mediana de su (proveedor, jurisdiccion, anio): 34 (suma 7,487,573,455.02 nominal)
  - id 95698: CABA 2016 `EVENTOS PRODUCCIONES SA` monto=1,160,879,808.00 mediana=18,000.00
  - id 103834: CABA 2017 `ARTE RADIOTELEVISIVO ARGENTINO S.A.` monto=1,151,594,994.00 mediana=36,000.00
  - id 94408: CABA 2016 `IMPREBA S.A.` monto=392,120,344.00 mediana=392,120.34
  - id 95073: CABA 2016 `IMPREBA S.A.` monto=392,120,344.00 mediana=392,120.34
  - id 95105: CABA 2016 `IMPREBA S.A.` monto=392,120,344.00 mediana=392,120.34
  - id 95756: CABA 2016 `IMPREBA S.A.` monto=392,120,344.00 mediana=392,120.34
  - id 96276: CABA 2016 `IMPREBA S.A.` monto=392,120,344.00 mediana=392,120.34
  - id 95717: CABA 2016 `FOX SPORTS` monto=385,093,632.00 mediana=19,000.00
  - id 90770: CABA 2016 `ARTE RADIOTELEVISIVO ARGENTINO S.A.` monto=327,902,256.00 mediana=25,000.00
  - id 95724: CABA 2016 `LS4 RADIO CONTINENTAL SOCIEDAD ANONIMA` monto=302,636,125.00 mediana=48,875.00
  - id 95759: CABA 2016 `FOX LATIN AMERICAN CHANNEL S.R.L` monto=283,758,552.00 mediana=173,034.89
  - id 94578: CABA 2016 `FOX SPORTS` monto=195,985,152.00 mediana=19,000.00
  - id 96292: CABA 2016 `EDITORIAL PERFIL S.A.` monto=174,832,416.00 mediana=59,093.74
  - id 384644: Nación 2021 `SENTIDOS S.A.` monto=171,699,000.00 mediana=76,145.30
  - id 92523: CABA 2016 `IMC RADIOS S.A.` monto=156,389,475.00 mediana=94,743.00
  - id 381501: Nación 2020 `SENTIDOS S.A.` monto=120,049,508.10 mediana=24,381.50
  - id 389600: Nación 2022 `SENTIDOS S.A.` monto=111,275,372.25 mediana=69,981.26
  - id 95829: CABA 2016 `RADIO MITRE S.A.` monto=102,592,875.00 mediana=12,000.00
  - id 96316: CABA 2016 `RADIO MITRE S.A.` monto=102,592,875.00 mediana=12,000.00
  - id 381504: Nación 2020 `SENTIDOS S.A.` monto=95,587,743.68 mediana=24,381.50
  - id 95730: CABA 2016 `DIFUSORA BAIRES SOCIEDAD ANONIMA` monto=83,697,273.00 mediana=35,026.32
  - id 384651: Nación 2021 `SENTIDOS S.A.` monto=81,451,994.13 mediana=76,145.30
  - id 95134: CABA 2016 `EL CRONISTA COMERCIAL SA` monto=79,389,112.00 mediana=78,650.00
  - id 96359: CABA 2016 `RADIODIFUSORA DEL PLATA SA` monto=67,500,576.00 mediana=26,160.00
  - id 103258: CABA 2017 `FOX LATIN AMERICAN CHANNEL S.R.L` monto=63,515,925.00 mediana=53,158.00
  - id 381509: Nación 2020 `RADIO Y TELEVISION ARGENT. SE` monto=63,198,509.28 mediana=46,103.12
  - id 95064: CABA 2016 `ESECOM S.A.` monto=38,085,831.00 mediana=19,042.92
  - id 96346: CABA 2016 `ESECOM S.A.` monto=38,085,831.00 mediana=19,042.92
  - id 381517: Nación 2020 `SENTIDOS S.A.` monto=35,916,709.22 mediana=24,381.50
  - id 95841: CABA 2016 `EDITORIAL LA CAPITAL SA` monto=33,126,975.00 mediana=21,103.11
  - id 381522: Nación 2020 `SENTIDOS S.A.` monto=32,004,500.00 mediana=24,381.50
  - id 381526: Nación 2020 `SENTIDOS S.A.` monto=28,304,549.90 mediana=24,381.50
  - id 381528: Nación 2020 `SENTIDOS S.A.` monto=27,956,634.00 mediana=24,381.50
  - id 232032: Nación 2014 `Media Force S.A.` monto=11,867,531.46 mediana=9,074.25
- ⚠️ archivos con 'Total general' de pivot probablemente cargado como orden: 3 (2586 filas, suma 972,960,476.18 nominal)
  - `(nuevo v2)segundo_semestre_prov_rubro-2010.csv`: 954 de 977 proveedores (ids de ejemplo: [426943, 426945, 426947, 426949, 426951])
  - `inversion_1er_Semestre_2012_proveedor_rubro.csv`: 949 de 964 proveedores (ids de ejemplo: [433064, 433067, 433070, 433072, 433074])
  - `(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv`: 683 de 691 proveedores (ids de ejemplo: [429230, 429232, 429234, 429237, 429240])
