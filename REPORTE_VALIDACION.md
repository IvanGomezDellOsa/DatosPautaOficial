# Reporte de validacion — pauta_oficial_unificado

Archivo validado: `/sessions/festive-zen-gauss/mnt/Repositorio DatosPautaOficial/etl/data/pauta_oficial_unificado_v2.csv`

**Total de filas:** 506701


## Filas por jurisdiccion

- CABA: 207721
- Nación: 193811
- Santa Fe: 61187
- PBA: 43982

## Cobertura de proveedor / medio

- proveedor nulo: 224812 (44.4%)
- medio nulo: 13694 (2.7%)
- ambos nulos (proveedor Y medio): 0 (0.0%)  ← deberian ser solo Via Publica

## Integridad de monto

- ✅ todos los montos son numericos y > 0

## Integridad de fecha

- ✅ todas las fechas son ISO (YYYY-MM-DD) o vacias

## Jurisdicciones / años fuera de rango

- jurisdicciones invalidas: ninguna ✅
- años fuera de 2003-2025: ninguno ✅

## Top-10 valores de `medio` que parecen TIPOS (revisar)

- `CANAL METRO`: 3389
- `CANAL 13`: 3077
- `PAGINA 12`: 2974
- `AMBITO FINANCIERO`: 2927
- `CANAL 9`: 2364
- `TN`: 2193
- `CANAL 26`: 2144
- `DIARIO POPULAR`: 2095
- `CRONICA`: 2081
- `C5N`: 1943
