# Reporte de validacion — pauta_oficial_unificado

Archivo validado: `C:\Users\IvanGomezD\Desktop\0\Git-Repositorios\Repositorio DatosPautaOficial\.claude\worktrees\upbeat-driscoll-dd6cd2\etl\data\pauta_oficial_unificado_v2.csv`

**Total de filas:** 554021


## Filas por jurisdiccion

- CABA: 224677
- Nación: 224175
- Santa Fe: 61187
- PBA: 43982

## Cobertura de proveedor / medio

- proveedor nulo: 230306 (41.6%)
- medio nulo: 44075 (8.0%)
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
- `AMBITO FINANCIERO`: 3019
- `PAGINA 12`: 2974
- `CANAL 9`: 2364
- `TN`: 2193
- `DIARIO POPULAR`: 2153
- `CANAL 26`: 2144
- `CRONICA`: 2081
- `C5N`: 1943

## Montos atipicos (solo informa: no se descarta ni modifica ninguna fila)

- ⚠️ ordenes >= 1000x la mediana de su (proveedor, jurisdiccion, anio): 11 (suma 779,312,052.02 nominal)
  - id 399444: Nación 2021 `SENTIDOS S.A.` monto=171,699,000.00 mediana=76,145.30
  - id 396301: Nación 2020 `SENTIDOS S.A.` monto=120,049,508.10 mediana=24,381.50
  - id 404400: Nación 2022 `SENTIDOS S.A.` monto=111,275,372.25 mediana=69,981.26
  - id 396304: Nación 2020 `SENTIDOS S.A.` monto=95,587,743.68 mediana=24,381.50
  - id 399451: Nación 2021 `SENTIDOS S.A.` monto=81,451,994.13 mediana=76,145.30
  - id 396309: Nación 2020 `RADIO Y TELEVISION ARGENT. SE` monto=63,198,509.28 mediana=46,103.12
  - id 396317: Nación 2020 `SENTIDOS S.A.` monto=35,916,709.22 mediana=24,381.50
  - id 396322: Nación 2020 `SENTIDOS S.A.` monto=32,004,500.00 mediana=24,381.50
  - id 396326: Nación 2020 `SENTIDOS S.A.` monto=28,304,549.90 mediana=24,381.50
  - id 396328: Nación 2020 `SENTIDOS S.A.` monto=27,956,634.00 mediana=24,381.50
  - id 246832: Nación 2014 `Media Force S.A.` monto=11,867,531.46 mediana=9,074.25
- ⚠️ archivos con 'Total general' de pivot probablemente cargado como orden: 0 (0 filas, suma 0.00 nominal)
