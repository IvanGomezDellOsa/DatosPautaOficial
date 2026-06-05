# -*- coding: utf-8 -*-
"""
extract_caba.py  —  Extrae y normaliza TODAS las fuentes CABA.

Formatos reales detectados (no coinciden 1:1 con el catalogo del prompt):

  A) Viejo 2003-2006   "Pauta 2003.csv".."Pauta 2006.csv"
     Header:  Agencia;Medio especifico;Jurisdiccion;Tipo de Medio;Importe
     sep=';' encoding=UTF-8-BOM monto europeo. proveedor=Agencia.   <-- BUG previo: se descartaba Agencia

  B) Especial 2007     "Pauta 2007 enero a mayo.csv"
     Header ancho: Año;SP;Campaña;Titulo;0;P.I.;Fecha de Publicacion;...;Tipo de Producto;Cantidad;Medida;Total;Ubicacion; Bruta ; Neto
     No hay medio ni proveedor. monto = Neto (o Bruta). tipo = Tipo de Producto.

  C) MES 2008-2009     "Pauta 2008.csv", "Publicidad Oficial CABA *2009*.csv"
     3 filas basura, luego header:  MES,TIPO,Medio,Total   monto "$ 11.694,41" (europeo).
     proveedor=None, medio=Medio, tipo=TIPO, fecha = mes(MES)+anio.

  D) 2010              "Pauta 2010 CABA.csv"
     Header: Año,Mes,Tipo,Subtipo,Medio,Campaña,Título,Fecha Publicación,Importe,Descripción
     monto europeo, fecha ISO.

  E) Moderno combinado (con columna TIPO):
       - root 2011-2014: pauta-publicitaria-2011..2014.csv  (TIPO[_DE_MEDIO];MEDIO;FECHA_PUBLICACION;IMPORTE)
       - subcarpetas 2015/2016/2017: pauta-publicitaria-YYYY[-total].csv (incluye RAZON_SOCIAL=proveedor)
     Se detecta Via Publica FILA A FILA por el valor de la columna TIPO.

  F) Moderno por-tipo (2018-2024): un archivo por categoria (Fecha,Medio,Importe).
     El tipo sale del NOMBRE del archivo. Via Publica -> medio=None.

REGLA ANTI-DUPLICADO: para 2015/2016/2017 existen combinado Y por-tipo. Se usa SOLO el
combinado (mas rico: trae proveedor). Para 2018-2024 solo hay por-tipo. Para 2011-2014
solo existe el combinado en root.

REGLA VIA PUBLICA: se colapsa TODO Via Publica a medio="Via Publica" y tipo_de_medio="Via Publica"
(se elimina la distincion de soporte: GRANDES FORMATOS, PANTALLAS LED, etc.), para que el grupo
sea agrupable bajo un unico medio.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import (  # noqa: E402
    DIR_CABA, registro, normalizar_monto, normalizar_fecha, limpiar_str,
    leer_filas, detectar_sep, leer_texto, anio_de_texto, Contador, log,
)

JURIS = "CABA"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _es_via_publica(texto):
    if not texto:
        return False
    t = texto.upper()
    return "VIA P" in t or "VÍA P" in t or "VIA-PUB" in t or t.strip() == "VP"


def _tipo_desde_nombre(nombre):
    """Deriva un tipo_de_medio canonico desde el nombre de archivo per-tipo."""
    n = nombre.lower()
    if "via" in n and ("publica" in n or "púb" in n or "pub" in n):
        return "Via Publica"
    if "vp" in re.split(r"[-_ .]", n):
        return "Via Publica"
    if "tv-cable" in n or "tv_cable" in n or "cable" in n:
        return "TV Cable"
    if "tv-abierta" in n or "tv_abierta" in n or "tv abierta" in n or "abierta" in n:
        return "TV Abierta"
    if "tv" in re.split(r"[-_ .]", n):
        return "TV"
    if "radio" in n:
        return "Radio"
    if "web" in n:
        return "Web"
    if "cine" in n:
        return "Cine"
    if "grafic" in n or "gráfic" in n:
        return "Medios Gráficos"
    if "vecinal" in n:
        return "Medios Vecinales"
    return None


def _indices(header):
    """Devuelve dict con indices de columnas relevantes (case-insensitive)."""
    H = [(h or "").strip().upper() for h in header]
    idx = {"fecha": None, "importe": None, "tipo": None, "medio": None, "razon": None}
    for i, h in enumerate(H):
        hn = h.replace("Ó", "O").replace("Á", "A").replace("Í", "I")
        if idx["fecha"] is None and "FECHA" in hn:
            idx["fecha"] = i
        if idx["importe"] is None and ("IMPORTE" in hn or hn in ("MONTO", "TOTAL")):
            idx["importe"] = i
        if idx["tipo"] is None and "TIPO" in hn:
            idx["tipo"] = i
        if idx["razon"] is None and "RAZON" in hn:
            idx["razon"] = i
    # medio: preferir columna EXACTA "MEDIO" (evita PROVINCIA_MEDIO etc.)
    for i, h in enumerate(H):
        if h == "MEDIO":
            idx["medio"] = i
            break
    if idx["medio"] is None:
        for i, h in enumerate(H):
            if "MEDIO" in h and "TIPO" not in h and "RAZON" not in h:
                idx["medio"] = i
                break
    return idx


def _cell(row, i):
    if i is None or i >= len(row):
        return None
    return row[i]


# ---------------------------------------------------------------------------
# A) Viejo 2003-2006
# ---------------------------------------------------------------------------

def _parse_viejo(path, anio, cont):
    """Formato 2003-2005: tiene columna Agencia. Orden de columnas variable -> por nombre."""
    out = []
    filas = leer_filas(path, ";")
    if not filas:
        return out
    header = [(h or "").strip().lower() for h in filas[0]]

    def col(*claves):
        for i, h in enumerate(header):
            if any(c == h for c in claves):
                return i
        for i, h in enumerate(header):
            if any(c in h for c in claves):
                return i
        return None

    i_prov = col("agencia")
    i_medio = col("medio especifico", "medio")
    i_tipo = col("tipo de medio", "tipo de producto", "tipo")
    i_monto = col("importe", "neto", "total")
    for row in filas[1:]:
        monto = normalizar_monto(_cell(row, i_monto))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        out.append(registro(
            JURIS, anio, monto, path.name,
            proveedor=_cell(row, i_prov), medio=_cell(row, i_medio),
            tipo_de_medio=_cell(row, i_tipo)))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# B) Especial 2007
# ---------------------------------------------------------------------------

def _parse_2007(path, anio, cont):
    out = []
    filas = leer_filas(path, ";")
    if not filas:
        return out
    header = [(h or "").strip().lower() for h in filas[0]]

    def col(*claves):
        for i, h in enumerate(header):
            if any(k in h for k in claves):
                return i
        return None

    i_neto = col("neto")
    i_bruta = col("bruta", "bruto")
    i_total = col("total")
    i_tipo = col("tipo de producto", "tipo")
    i_fecha = col("fecha de publicacion", "fecha")
    for row in filas[1:]:
        monto = normalizar_monto(_cell(row, i_neto)) or normalizar_monto(_cell(row, i_bruta))
        if monto is None:
            monto = normalizar_monto(_cell(row, i_total))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        fecha = normalizar_fecha(_cell(row, i_fecha), anio)
        out.append(registro(
            JURIS, anio, monto, path.name,
            fecha=fecha, tipo_de_medio=_cell(row, i_tipo)))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# C) MES 2008-2009
# ---------------------------------------------------------------------------

def _parse_mes(path, anio, cont):
    out = []
    sep = detectar_sep(path)
    filas = leer_filas(path, sep)
    # localizar la fila de header (la que contiene "MES")
    h_idx = None
    for i, row in enumerate(filas[:8]):
        celdas = [(c or "").strip().upper() for c in row]
        if "MES" in celdas:
            h_idx = i
            break
    if h_idx is None:
        cont.descartar("sin_header_MES", 1)
        return out
    header = [(c or "").strip().upper() for c in filas[h_idx]]

    def col(nombre):
        for i, h in enumerate(header):
            if h == nombre:
                return i
        for i, h in enumerate(header):
            if nombre in h:
                return i
        return None

    i_mes = col("MES")
    i_tipo = col("TIPO")
    i_medio = col("MEDIO")
    i_total = col("TOTAL")
    for row in filas[h_idx + 1:]:
        monto = normalizar_monto(_cell(row, i_total))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        fecha = normalizar_fecha(_cell(row, i_mes), anio)
        out.append(registro(
            JURIS, anio, monto, path.name,
            fecha=fecha, medio=_cell(row, i_medio), tipo_de_medio=_cell(row, i_tipo)))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# D) 2010
# ---------------------------------------------------------------------------

def _parse_2010(path, anio, cont):
    out = []
    filas = leer_filas(path, ",")
    if not filas:
        return out
    header = [(h or "").strip().lower() for h in filas[0]]

    def col(*claves):
        for i, h in enumerate(header):
            if any(k == h or k in h for k in claves):
                return i
        return None

    i_anio = col("año", "ano")
    i_tipo = col("tipo")
    i_medio = col("medio")
    i_fecha = col("fecha publicación", "fecha publicacion", "fecha")
    i_importe = col("importe")
    for row in filas[1:]:
        monto = normalizar_monto(_cell(row, i_importe))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        a = _cell(row, i_anio) or anio
        fecha = normalizar_fecha(_cell(row, i_fecha), a)
        tipo = _cell(row, i_tipo)
        medio = _cell(row, i_medio)
        if _es_via_publica(tipo):
            medio = "Via Publica"          # colapsa todo Via Publica a un unico medio agrupable
            tipo_final = "Via Publica"
        else:
            tipo_final = tipo
        out.append(registro(
            JURIS, a, monto, path.name,
            fecha=fecha, medio=medio, tipo_de_medio=tipo_final))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# E) Moderno combinado (con columna TIPO) -> VP fila a fila
# ---------------------------------------------------------------------------

def _parse_combinado(path, anio, cont):
    out = []
    sep = detectar_sep(path)
    filas = leer_filas(path, sep)
    if len(filas) < 2:
        return out
    # localizar la fila de header real (algunos archivos traen titulos arriba)
    h_idx, idx = None, None
    for i, fila in enumerate(filas[:8]):
        cand = _indices(fila)
        if cand["importe"] is not None and (cand["medio"] is not None or cand["fecha"] is not None):
            h_idx, idx = i, cand
            break
    if idx is None:
        cont.descartar("sin_columna_importe")
        return out
    for row in filas[h_idx + 1:]:
        monto = normalizar_monto(_cell(row, idx["importe"]))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        fecha = normalizar_fecha(_cell(row, idx["fecha"]), anio)
        tipo = limpiar_str(_cell(row, idx["tipo"]))
        medio = limpiar_str(_cell(row, idx["medio"]))
        prov = limpiar_str(_cell(row, idx["razon"]))
        # saltar filas de subtotal ("Total XXX")
        if (medio and medio.lower().startswith("total ")) or (tipo and tipo.lower().startswith("total ")):
            cont.descartar("subtotal")
            continue
        if _es_via_publica(tipo) or _es_via_publica(medio):
            medio = "Via Publica"          # colapsa todo Via Publica a un unico medio agrupable
            tipo_final = "Via Publica"
        else:
            tipo_final = tipo
        if medio is None and prov is None and not tipo_final:
            cont.descartar("sin_datos")
            continue
        out.append(registro(
            JURIS, anio, monto, path.name,
            fecha=fecha, proveedor=prov, medio=medio, tipo_de_medio=tipo_final))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# F) Moderno por-tipo (tipo desde nombre de archivo)
# ---------------------------------------------------------------------------

def _parse_pertype(path, anio, cont):
    out = []
    tipo_archivo = _tipo_desde_nombre(path.name)
    es_vp = (tipo_archivo == "Via Publica")
    sep = detectar_sep(path)
    filas = leer_filas(path, sep)
    if len(filas) < 2:
        return out
    # Algunos archivos (p.ej. medios-graficos-2022.csv, cine-2022.csv) tienen
    # cada linea envuelta en comillas extra: '"FECHA,""MEDIO"",""IMPORTE"""'.
    # El parser CSV los lee como UNA sola celda por fila con el contenido interno.
    # Detectamos por: header de 1 columna que contiene comas, y re-parseamos.
    if len(filas[0]) == 1 and "," in (filas[0][0] or ""):
        import io as _io, csv as _csv_mod
        filas = [
            list(_csv_mod.reader([f[0]]))[0]
            for f in filas
            if f and (f[0] or "").strip()
        ]
    idx = _indices(filas[0])
    if idx["importe"] is None:
        cont.descartar("sin_columna_importe")
        return out
    for row in filas[1:]:
        monto = normalizar_monto(_cell(row, idx["importe"]))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        fecha = normalizar_fecha(_cell(row, idx["fecha"]), anio)
        medio = limpiar_str(_cell(row, idx["medio"]))
        prov = limpiar_str(_cell(row, idx["razon"]))
        if es_vp:
            medio = "Via Publica"          # colapsa todo Via Publica a un unico medio agrupable
            tipo_final = "Via Publica"
        else:
            tipo_final = tipo_archivo
        if medio is None and prov is None and not tipo_final:
            cont.descartar("sin_datos")
            continue
        out.append(registro(
            JURIS, anio, monto, path.name,
            fecha=fecha, proveedor=prov, medio=medio, tipo_de_medio=tipo_final))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# Deteccion de formato para archivos de root
# ---------------------------------------------------------------------------

def _detectar_formato_root(path):
    sep = detectar_sep(path)
    filas = leer_filas(path, sep)[:8]
    # celdas de las primeras filas, normalizadas
    celdas = []
    for fila in filas:
        celdas.append([(c or "").strip().lower() for c in fila])
    plano = " ".join(c for fila in celdas for c in fila)

    def hay_celda(valor):
        return any(c == valor for fila in celdas for c in fila)

    if hay_celda("agencia"):
        return "viejo"
    if hay_celda("subtipo"):
        return "2010"
    if "bruta" in plano or " bruto " in (" " + plano + " "):
        return "esp_2007"          # 2006/2007 (Bruta;Neto), sin medio ni agencia
    if hay_celda("mes"):
        return "mes"               # 2008 / 2009-enero-abril (MES,TIPO,Medio,Total)
    return "combinado"             # resto (incl. 2009 julio-dic estilo prompt)


# ---------------------------------------------------------------------------
# Extractor principal
# ---------------------------------------------------------------------------

def extraer():
    log("[CABA] iniciando extraccion")
    registros = []
    cont = Contador("[CABA]")

    if not DIR_CABA.exists():
        log(f"[CABA] ADVERTENCIA: no existe {DIR_CABA}")
        return registros

    # --- archivos en root de CABA ---
    for f in sorted(DIR_CABA.glob("*.csv")):
        anio = anio_de_texto(f.name)
        if anio is None:
            cont.descartar("sin_anio_en_nombre")
            continue
        fmt = _detectar_formato_root(f)
        if fmt == "viejo":
            registros += _parse_viejo(f, anio, cont)
        elif fmt == "esp_2007":
            registros += _parse_2007(f, anio, cont)
        elif fmt == "mes":
            registros += _parse_mes(f, anio, cont)
        elif fmt == "2010":
            registros += _parse_2010(f, anio, cont)
        else:
            registros += _parse_combinado(f, anio, cont)

    # --- subcarpetas por año ---
    for ydir in sorted(p for p in DIR_CABA.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}", p.name)):
        anio = int(ydir.name)
        csvs = sorted(ydir.glob("*.csv"))
        combinados = [f for f in csvs
                      if re.search(r"pauta-publicitaria-\d{4}(-total)?\.csv$", f.name.lower())]
        if combinados:
            # 2015/2016/2017: usar SOLO el combinado (evita duplicar con per-tipo)
            for f in combinados:
                registros += _parse_combinado(f, anio, cont)
        else:
            # 2018-2024: per-tipo
            for f in csvs:
                registros += _parse_pertype(f, anio, cont)

    cont.resumen()
    log(f"[CABA] total: {len(registros)} registros")
    return registros


if __name__ == "__main__":
    regs = extraer()
    print(f"\nCABA -> {len(regs)} registros")
    # muestra
    for r in regs[:3]:
        print(r)
    # cobertura rapida
    from collections import Counter
    poranio = Counter(r["anio"] for r in regs)
    print("por anio:", dict(sorted(poranio.items())))
    print("con proveedor:", sum(1 for r in regs if r["proveedor"]))
    print("con medio:", sum(1 for r in regs if r["medio"]))
