# -*- coding: utf-8 -*-
"""
validar.py  —  Valida el CSV unificado y emite REPORTE_VALIDACION.md.

Chequea:
  - filas con proveedor=null, medio=null, ambos=null
  - montos negativos, cero o no numericos
  - fechas malformadas (ni ISO YYYY-MM-DD ni vacio)
  - jurisdicciones fuera del set esperado
  - top-10 valores de `medio` que parecen TIPOS en vez de nombres
    (heuristica: todo mayusculas + < 3 palabras + sin puntos/guiones)

Uso:  python3 etl/validar.py            (valida el v2 por defecto)
      python3 etl/validar.py <ruta.csv>
"""

import csv
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractores"))
import comun  # noqa: E402
from comun import OUTPUT_CSV, REPO_ROOT, JURISDICCIONES_VALIDAS, log, ANIO_MIN, ANIO_MAX  # noqa: E402

RE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPORTE = REPO_ROOT / "REPORTE_VALIDACION.md"


def _parece_tipo(medio):
    if not medio:
        return False
    s = medio.strip()
    if not s:
        return False
    if any(ch in s for ch in ".-/"):
        return False
    if len(s.split()) >= 3:
        return False
    return s.upper() == s and any(c.isalpha() for c in s)


def validar(ruta=None):
    ruta = ruta or OUTPUT_CSV
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))

    total = len(filas)
    prov_null = sum(1 for r in filas if not r["proveedor"])
    medio_null = sum(1 for r in filas if not r["medio"])
    ambos_null = sum(1 for r in filas if not r["proveedor"] and not r["medio"])

    montos_malos = []
    for i, r in enumerate(filas):
        try:
            v = float(r["monto"])
            if v <= 0:
                montos_malos.append((i, r["monto"]))
        except (ValueError, TypeError):
            montos_malos.append((i, r["monto"]))

    fechas_malas = [(i, r["fecha"]) for i, r in enumerate(filas)
                    if r["fecha"] and not RE_ISO.match(r["fecha"])]

    juris_malas = Counter(r["jurisdiccion"] for r in filas
                          if r["jurisdiccion"] not in JURISDICCIONES_VALIDAS)

    anios_malos = Counter()
    for r in filas:
        try:
            a = int(r["anio"])
            if not (ANIO_MIN <= a <= ANIO_MAX):
                anios_malos[r["anio"]] += 1
        except (ValueError, TypeError):
            anios_malos[r["anio"]] += 1

    medios_tipo = Counter(r["medio"] for r in filas if _parece_tipo(r["medio"]))

    por_juris = Counter(r["jurisdiccion"] for r in filas)

    # ----- escribir reporte -----
    L = []
    L.append("# Reporte de validacion — pauta_oficial_unificado\n")
    L.append(f"Archivo validado: `{ruta}`\n")
    L.append(f"**Total de filas:** {total}\n")

    L.append("\n## Filas por jurisdiccion\n")
    for j, n in por_juris.most_common():
        L.append(f"- {j}: {n}")

    L.append("\n## Cobertura de proveedor / medio\n")
    L.append(f"- proveedor nulo: {prov_null} ({100*prov_null/max(total,1):.1f}%)")
    L.append(f"- medio nulo: {medio_null} ({100*medio_null/max(total,1):.1f}%)")
    L.append(f"- ambos nulos (proveedor Y medio): {ambos_null} "
             f"({100*ambos_null/max(total,1):.1f}%)  ← deberian ser solo Via Publica")

    L.append("\n## Integridad de monto\n")
    if montos_malos:
        L.append(f"- ⚠️ montos <=0 o no numericos: {len(montos_malos)} (muestra: {montos_malos[:5]})")
    else:
        L.append("- ✅ todos los montos son numericos y > 0")

    L.append("\n## Integridad de fecha\n")
    if fechas_malas:
        L.append(f"- ⚠️ fechas malformadas: {len(fechas_malas)} (muestra: {fechas_malas[:5]})")
    else:
        L.append("- ✅ todas las fechas son ISO (YYYY-MM-DD) o vacias")

    L.append("\n## Jurisdicciones / años fuera de rango\n")
    L.append(f"- jurisdicciones invalidas: {dict(juris_malas) if juris_malas else 'ninguna ✅'}")
    L.append(f"- años fuera de {ANIO_MIN}-{ANIO_MAX}: {dict(anios_malos) if anios_malos else 'ninguno ✅'}")

    L.append("\n## Top-10 valores de `medio` que parecen TIPOS (revisar)\n")
    if medios_tipo:
        for m, n in medios_tipo.most_common(10):
            L.append(f"- `{m}`: {n}")
    else:
        L.append("- ninguno detectado ✅")

    REPORTE.write_text("\n".join(L) + "\n", encoding="utf-8")

    # ----- resumen a stderr -----
    log(f"[validar] total={total} | prov_null={prov_null} medio_null={medio_null} "
        f"ambos_null={ambos_null} | montos_malos={len(montos_malos)} "
        f"fechas_malas={len(fechas_malas)} juris_malas={sum(juris_malas.values())}")
    log(f"[validar] reporte -> {REPORTE}")
    return total


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    validar(arg)
