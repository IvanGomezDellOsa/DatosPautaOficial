# -*- coding: utf-8 -*-
"""
unificar.py  —  Script maestro de unificacion de pauta oficial.

1. Llama a los 4 extractores (CABA, Nacion, PBA, Santa Fe).
2. Concatena todo en una sola lista de registros.
3. Aplica reglas de calidad finales.
4. Imprime reporte de cobertura por jurisdiccion/año.
5. Guarda etl/data/pauta_oficial_unificado_v2.csv (UTF-8 sin BOM, separador ',').

Uso:   python3 etl/unificar.py        (desde la raiz del repo)

La ruta de los datos crudos se puede sobre-escribir con la env var DATOS_CRUDOS_BASE.
"""

import csv
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractores"))
import comun  # noqa: E402
from comun import COLUMNS, JURISDICCIONES_VALIDAS, OUTPUT_CSV, DATA_DIR, log, ANIO_MIN, ANIO_MAX  # noqa: E402

import extract_caba       # noqa: E402
import extract_nacion     # noqa: E402
import extract_pba        # noqa: E402
import extract_santa_fe   # noqa: E402


def _valida_fila(r, descartes):
    # monto
    m = r.get("monto")
    if m is None or not isinstance(m, (int, float)) or m <= 0:
        descartes["monto_invalido"] += 1
        return False
    # anio
    a = r.get("anio")
    if a is None or not (ANIO_MIN <= a <= ANIO_MAX):
        descartes["anio_fuera_de_rango"] += 1
        return False
    # jurisdiccion
    if r.get("jurisdiccion") not in JURISDICCIONES_VALIDAS:
        descartes["jurisdiccion_invalida"] += 1
        return False
    # al menos uno identificable (proveedor o medio); se admite via publica (tipo no nulo)
    if not r.get("proveedor") and not r.get("medio") and not r.get("tipo_de_medio"):
        descartes["sin_proveedor_ni_medio_ni_tipo"] += 1
        return False
    return True


def _reporte(registros):
    log("\n================ REPORTE DE COBERTURA ================")
    log(f"TOTAL filas: {len(registros)}")

    por_juris = Counter(r["jurisdiccion"] for r in registros)
    log("\nPor jurisdiccion:")
    for j, n in por_juris.most_common():
        log(f"  {j:10s} {n:>8d}")

    log("\nPor jurisdiccion x año:")
    grid = defaultdict(Counter)
    for r in registros:
        grid[r["jurisdiccion"]][r["anio"]] += 1
    for j in sorted(grid):
        pares = ", ".join(f"{a}:{n}" for a, n in sorted(grid[j].items()))
        log(f"  {j}: {pares}")

    log("\nCobertura de campos (no nulos):")
    n = max(len(registros), 1)
    for campo in ("fecha", "proveedor", "medio", "tipo_de_medio", "resolucion"):
        c = sum(1 for r in registros if r.get(campo))
        log(f"  {campo:14s} {c:>8d}  ({100.0 * c / n:5.1f}%)")
    log("=====================================================\n")


def unificar():
    log("### UNIFICACION DE PAUTA OFICIAL ###")
    log(f"Base de crudos: {comun.CRUDOS_BASE}")

    registros = []
    registros += extract_caba.extraer()
    registros += extract_nacion.extraer()
    registros += extract_pba.extraer()
    registros += extract_santa_fe.extraer()

    log(f"\nRegistros crudos extraidos: {len(registros)}")

    # Agrupabilidad: si una fila no tiene medio ni proveedor pero si tiene
    # tipo_de_medio, se vuelca el concepto a `medio` para que sea agrupable
    # (Via Publica ya viene con medio="Via Publica"; esto cubre CABA 2006/2007,
    #  cuyo unico dato identificable es el "tipo de producto").
    _VP = {"via publica", "vía pública", "via pública", "vía publica"}
    rellenados = 0
    for r in registros:
        if not r.get("medio") and not r.get("proveedor") and r.get("tipo_de_medio"):
            r["medio"] = r["tipo_de_medio"]
            rellenados += 1
        # normalizar casing de Via Publica para que agrupe en un unico valor
        for campo in ("medio", "tipo_de_medio"):
            v = r.get(campo)
            if v and v.strip().lower() in _VP:
                r[campo] = "Via Publica"
    if rellenados:
        log(f"Filas con medio rellenado desde tipo_de_medio: {rellenados}")

    descartes = Counter()
    limpios = [r for r in registros if _valida_fila(r, descartes)]
    if descartes:
        log("Descartes en control de calidad final:")
        for k, v in descartes.most_common():
            log(f"  {k}: {v}")

    _reporte(limpios)

    # --- escritura ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in limpios:
            fila = dict(r)
            # normalizar monto a numero plano (sin notacion cientifica rara)
            mv = fila["monto"]
            fila["monto"] = ("%.2f" % mv).rstrip("0").rstrip(".") if isinstance(mv, float) else mv
            w.writerow(fila)
    log(f"OK -> {OUTPUT_CSV}  ({len(limpios)} filas)")
    return limpios


if __name__ == "__main__":
    unificar()
