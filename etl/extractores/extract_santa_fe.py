# -*- coding: utf-8 -*-
"""
extract_santa_fe.py  —  Extrae Santa Fe.

IMPORTANTE: en la carpeta de crudos NO hay CSVs de Santa Fe (solo PDFs por año, que
NO se re-extraen aca). Los datos de Santa Fe ya fueron extraidos y curados previamente
en `santa_fe_curado.csv` (raiz de DatosPautaOficial), con el esquema:

    jurisdiccion,anio,fecha,tipo_de_medio,medio,proveedor,monto,resolucion,archivo_origen

Este extractor lee ese CSV curado, re-normaliza monto/strings y lo mapea al esquema
canonico. Si el archivo no existe, imprime advertencia y devuelve vacio.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import (  # noqa: E402
    CRUDOS_BASE, registro, normalizar_monto, normalizar_fecha, limpiar_str,
    leer_dicts, anio_de_texto, Contador, log,
)

JURIS = "Santa Fe"

# Fuente curada (fuera del repo, junto a los crudos)
SANTA_FE_CURADO = CRUDOS_BASE / "santa_fe_curado.csv"
# Rutas alternativas por si cambia la ubicacion
ALTERNATIVAS = [
    CRUDOS_BASE / "santa_fe_curado.csv",
    CRUDOS_BASE / "Datos_Pauta_Oficial_Curado" / "santa_fe_curado.csv",
]


def _ubicar_curado():
    for p in [SANTA_FE_CURADO] + ALTERNATIVAS:
        if p.exists():
            return p
    return None


def extraer():
    log("[Santa Fe] iniciando extraccion")
    registros = []
    cont = Contador("[Santa Fe]")

    fuente = _ubicar_curado()
    if fuente is None:
        log(f"[Santa Fe] ADVERTENCIA: no se encontro santa_fe_curado.csv en {CRUDOS_BASE}. "
            f"Los PDFs por año NO se re-extraen. Santa Fe queda PENDIENTE (0 filas).")
        return registros

    filas = leer_dicts(fuente)
    cols = {c.lower().strip(): c for c in (filas[0].keys() if filas else []) if c}

    def b(*claves):
        for k in claves:
            if k in cols:
                return cols[k]
        for k in claves:
            for low, orig in cols.items():
                if k in low:
                    return orig
        return None

    c_anio = b("anio", "año", "year")
    c_fecha = b("fecha")
    c_tipo = b("tipo_de_medio", "tipo")
    c_medio = b("medio")
    c_prov = b("proveedor")
    c_monto = b("monto", "importe", "total")
    c_res = b("resolucion", "resolución")
    c_org = b("archivo_origen", "origen")

    for r in filas:
        monto = normalizar_monto(r.get(c_monto)) if c_monto else None
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        anio = anio_de_texto(r.get(c_anio) or "") or anio_de_texto(r.get(c_fecha) or "")
        fecha = normalizar_fecha(r.get(c_fecha), anio) if c_fecha else None
        prov = limpiar_str(r.get(c_prov)) if c_prov else None
        medio = limpiar_str(r.get(c_medio)) if c_medio else None
        if prov is None and medio is None:
            cont.descartar("sin_prov_ni_medio")
            continue
        origen = limpiar_str(r.get(c_org)) if c_org else None
        registros.append(registro(
            JURIS, anio, monto, origen or fuente.name,
            fecha=fecha, proveedor=prov, medio=medio,
            tipo_de_medio=limpiar_str(r.get(c_tipo)) if c_tipo else None,
            resolucion=r.get(c_res) if c_res else None))
        cont.ok()

    cont.resumen()
    log(f"[Santa Fe] total: {len(registros)} registros (fuente: {fuente.name})")
    return registros


if __name__ == "__main__":
    regs = extraer()
    print(f"\nSanta Fe -> {len(regs)} registros")
    for r in regs[:3]:
        print(r)
    from collections import Counter
    print("por anio:", dict(sorted(Counter(r["anio"] for r in regs).items())))
    print("con proveedor:", sum(1 for r in regs if r["proveedor"]))
    print("con medio:", sum(1 for r in regs if r["medio"]))
