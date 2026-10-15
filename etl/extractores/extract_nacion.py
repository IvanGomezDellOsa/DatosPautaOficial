# -*- coding: utf-8 -*-
"""
extract_nacion.py  —  Extrae y normaliza las fuentes de Nacion (Telam / JGM).

Formatos reales:

  1) LIMPIO (root):
     - pauta-oficial-*.csv (2014-2019):
         orden_de_publicidad,total,descripcion_anunciante,campania,rubro,
         nombre_o_denominacion_proveedor,medio,tipo_de_orden,periodo
     - publicidad-oficial-*.csv (2020-2022):
         rubro,nombre_o_denominacion_proveedor,medio,provincia_medio,ciudad_medio,
         total_con_iva,publicidad_jgm,publicidad_desc,publicidad_canje
     Se mapea por NOMBRE de columna (tolera ambos juegos).

  2) 2011 (subcarpeta) nacion_2011_proveedor.csv  -> CSV limpio:
         Año,SEMESTRE,Rubro,RAZON SOCIAL,Importe   (sin medio)

  3) PIVOT de ancho fijo (subcarpetas 2009, 2010, 2012):
     - 2009: por MES   (DENOMINACION | MEDIO | may-09 | jul-09 | ...)
     - 2010/2012: por RUBRO (RAZON SOCIAL | CABLE | CINE | GRAFICA | RADIO | TV | VIA PUBLICA | WEB | Total general)
     Cada linea es un unico campo entre comillas con columnas alineadas por espacios.
     Se detectan posiciones de columna en el header y se asigna cada numero a la
     columna mas cercana por posicion (maneja celdas vacias).
     En los pivots por rubro el "Total general" de cada fila se reconoce por aritmetica
     (ultimo numero = suma de los anteriores) y la tabla se concilia contra su Total
     general: las paginas sin encabezado vienen corridas (ver _pivot_rubro).
     Dedup de versiones duplicadas: se prefieren los archivos "(nuevo v2)".

  4) PDF oficial de esos pivots: si esta en la carpeta del año junto al CSV (ver PDF_DE_PIVOT),
     se lee el PDF por coordenadas en lugar del texto, que no permite saber la columna (rubro
     o mes) de cada monto. Ver _parse_pivot_pdf.
"""

import hashlib
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import (  # noqa: E402
    DIR_NACION, DIR_CURADO, registro, normalizar_fecha, parser_montos,
    limpiar_str, leer_dicts, leer_texto, anio_de_texto, Contador, log,
)

JURIS = "Nación"

RUBRO_CANON = {
    "CABLE": "TV Cable", "TV CABLE": "TV Cable",
    "T.V.": "TV", "TV": "TV", "T V": "TV",
    "GRAFICA": "Gráfica", "GRÁFICA": "Gráfica", "MEDIOS GRAFICOS": "Gráfica",
    "RADIO": "Radio",
    "CINE": "Cine",
    "WEB": "Web", "INTERNET": "Web",
    "VIA PUBLICA": "Via Publica", "VIA PUBLIC": "Via Publica", "VÍA PÚBLICA": "Via Publica",
}


def _canon_rubro(lab):
    if not lab:
        return None
    k = lab.strip().upper().replace("Í", "I").replace("Ó", "O").replace("Á", "A")
    return RUBRO_CANON.get(k, lab.strip())


# ---------------------------------------------------------------------------
# 1) LIMPIO
# ---------------------------------------------------------------------------

def _parse_limpio(path, cont):
    out = []
    filas = leer_dicts(path)
    if not filas:
        return out
    cols = {c.lower().strip(): c for c in filas[0].keys() if c}

    def buscar(*claves):
        for k in claves:
            if k in cols:
                return cols[k]
        for k in claves:
            for low, orig in cols.items():
                if k in low:
                    return orig
        return None

    c_monto = buscar("total_con_iva", "total")
    c_prov = buscar("nombre_o_denominacion_proveedor", "razon social", "proveedor", "denominacion")
    c_medio = buscar("medio")           # 'medio' exacto antes que provincia_medio
    if c_medio and c_medio.lower() not in ("medio",):
        # si solo matcheo por substring algo como provincia_medio, evitarlo
        if "provincia" in c_medio.lower() or "ciudad" in c_medio.lower():
            c_medio = cols.get("medio")
    c_rubro = buscar("rubro")
    c_fecha = buscar("periodo", "fecha")
    c_res = buscar("orden_de_publicidad", "orden")
    anio_archivo = anio_de_texto(path.name)
    leer_monto = parser_montos((r.get(c_monto) for r in filas) if c_monto else (),
                               f"[Nación] {path.name}")

    for r in filas:
        monto = leer_monto(r.get(c_monto)) if c_monto else None
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        fecha = normalizar_fecha(r.get(c_fecha), anio_archivo) if c_fecha else None
        anio = anio_de_texto(r.get(c_fecha) or "") or anio_archivo
        prov = limpiar_str(r.get(c_prov)) if c_prov else None
        medio = limpiar_str(r.get(c_medio)) if c_medio else None
        if prov is None and medio is None:
            cont.descartar("sin_prov_ni_medio")
            continue
        out.append(registro(
            JURIS, anio, monto, path.name,
            fecha=fecha, proveedor=prov, medio=medio,
            tipo_de_medio=_canon_rubro(limpiar_str(r.get(c_rubro))) if c_rubro else None,
            resolucion=r.get(c_res) if c_res else None))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# 2) 2011
# ---------------------------------------------------------------------------

def _parse_2011(path, cont):
    out = []
    filas = leer_dicts(path)
    cols = {c.lower().strip(): c for c in (filas[0].keys() if filas else []) if c}

    def b(*claves):
        for k in claves:
            for low, orig in cols.items():
                if k == low or k in low:
                    return orig
        return None

    c_prov = b("razon social", "razon", "proveedor")
    c_rubro = b("rubro")
    c_monto = b("importe", "total")
    leer_monto = parser_montos((r.get(c_monto) for r in filas) if c_monto else (),
                               f"[Nación] {path.name}")
    for r in filas:
        monto = leer_monto(r.get(c_monto)) if c_monto else None
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        out.append(registro(
            JURIS, 2011, monto, path.name,
            proveedor=limpiar_str(r.get(c_prov)) if c_prov else None,
            tipo_de_medio=_canon_rubro(limpiar_str(r.get(c_rubro))) if c_rubro else None))
        cont.ok()
    return out


# ---------------------------------------------------------------------------
# 3) PIVOT ancho fijo
# ---------------------------------------------------------------------------

def _split_pos(linea):
    """Tokeniza una linea respetando columnas separadas por 2+ espacios.
    Devuelve [(start_char, texto)]. Conserva espacios simples internos."""
    res = []
    for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", linea):
        txt = m.group().strip()
        if txt:
            res.append((m.start(), txt))
    return res


def _unquote(l):
    """Cada linea es un unico campo CSV entre comillas: se sacan las comillas envolventes y se
    desescapan las internas ('LUCRO""NOSOTROS""' -> 'LUCRO"NOSOTROS"')."""
    l = l.rstrip("\r")
    if len(l) >= 2 and l[0] == '"' and l[-1] == '"':
        l = l[1:-1].replace('""', '"')
    return l


def _es_fila_total(prov, modo):
    """Filas de totales del pivot, que no son proveedores.

    En los pivots por mes (proveedor x medio) Excel intercala subtotales "Total <proveedor>",
    asi que se salta toda fila que empiece con "total". En los pivots por rubro no hay
    subtotales: solo la fila "Total general", y un proveedor puede llamarse "TOTAL PUBLIVIA SA"
    (antes se descartaba)."""
    p = prov.strip().lower()
    if p.startswith("suma de"):
        return True
    if modo == "mes":
        return p.startswith("total")
    return re.fullmatch(r"total( general)?", p) is not None


def _centavos(monto):
    return round(monto * 100)


def _parse_pivot(path, anio, cont):
    out = []
    txt, _ = leer_texto(path)
    lineas = [_unquote(l) for l in txt.split("\n")]

    # detectar modo y fila de header
    modo, h = None, None
    for i, l in enumerate(lineas):
        u = l.upper()
        if "TOTAL GENERAL" in u:
            modo, h = "rubro", i
            break
        if re.search(r"\b[A-Za-z]{3}-\d{2}\b", l):
            modo, h = "mes", i
            break
    if h is None:
        cont.descartar("sin_header_pivot")
        return out

    cols = _split_pos(lineas[h])
    n_text = 2 if modo == "mes" else 1
    if len(cols) <= n_text:
        cont.descartar("header_pivot_corto")
        return out
    val_cols = cols[n_text:]   # incluye "Total general" para absorber ese token

    filas, total_tabla = [], None
    for l in lineas[h + 1:]:
        if not l.strip():
            continue
        toks = _split_pos(l)
        if len(toks) <= 1:
            continue
        prov = toks[0][1]
        if _es_fila_total(prov, modo):
            if modo == "rubro" and prov.strip().lower().startswith("total"):
                total_tabla = toks[-1][1]   # Total general de la tabla, para conciliar
            continue
        # Saltar filas donde prov parece un numero (totales de columna scrapeados
        # como si fueran nombres de proveedor, ej: "116.778.592,23").
        if prov and re.fullmatch(r"[\d.,\s]+", prov.strip()):
            cont.descartar("fila_total_numerica")
            continue
        medio = toks[1][1] if (modo == "mes" and len(toks) > 1) else None
        filas.append((prov, medio, toks[n_text:]))

    leer_monto = parser_montos((tv for _, _, nums in filas for _, tv in nums),
                               f"[Nación] {path.name}")
    if modo == "rubro":
        return _pivot_rubro(path, anio, filas, val_cols, leer_monto, total_tabla, cont)

    for prov, medio, nums in filas:
        emitio = False
        for ts, tv in nums:
            monto = leer_monto(tv)
            if monto is None:
                continue
            # columna mas cercana por posicion
            col = min(val_cols, key=lambda c: abs(c[0] - ts))
            lab = col[1]
            if "total" in lab.lower():
                continue   # token de Total general -> descartar
            fecha = normalizar_fecha(lab, anio)
            out.append(registro(
                JURIS, anio, monto, path.name,
                fecha=fecha, proveedor=limpiar_str(prov), medio=limpiar_str(medio)))
            cont.ok()
            emitio = True
        if not emitio:
            cont.descartar("fila_sin_valores")
    return out


def _pivot_rubro(path, anio, filas, val_cols, leer_monto, total_tabla, cont):
    """Pivot por rubro: una fila por proveedor con un monto por rubro y el "Total general".

    El total de cada fila se reconoce por aritmetica: es el ultimo numero y es igual a la suma
    de los anteriores. No se usa su posicion porque en los textos convertidos desde PDF las
    paginas sin encabezado quedan corridas (hasta 4 columnas y de forma no uniforme en
    2010-S2): por posicion el total caia en "Web" o "Via Publica" y se cargaba como orden.

    El rubro solo sale de la posicion. Si en alguna fila el total no cae en la columna
    "Total general", o dos montos caen en la misma columna, las posiciones del archivo no
    siguen al encabezado: el rubro de todo el archivo queda vacio y se avisa. Es preferible
    no tener el rubro a publicar uno equivocado; el PDF oficial si permite leerlo.

    Al final se concilia la suma de lo cargado contra el Total general de la tabla."""
    i_total = next(k for k, (_, lab) in enumerate(val_cols) if "total" in lab.lower())

    def col(ts):
        # columna cuyo encabezado empieza mas cerca del numero
        return min(range(len(val_cols)), key=lambda k: abs(val_cols[k][0] - ts))

    out, lecturas, corridas = [], [], 0
    for prov, _, toks in filas:
        nums = [(col(ts), m) for ts, tv in toks for m in [leer_monto(tv)] if m is not None]
        if not nums:
            cont.descartar("fila_sin_valores")
            continue
        *rubros, (c_tot, m_tot) = nums
        if rubros and _centavos(m_tot) == sum(_centavos(m) for _, m in rubros):
            cs = [c for c, _ in rubros] + [c_tot]
            if c_tot != i_total or any(a >= b for a, b in zip(cs, cs[1:])):
                corridas += 1
        else:
            # la fila no concilia: se usa la posicion (lo que cae en "Total general" no se carga)
            cont.avisar("pivot_fila_no_concilia")
            rubros = [(c, m) for c, m in nums if c != i_total]
        if not rubros:
            cont.descartar("fila_sin_valores")
            continue
        lecturas.append((prov, rubros))

    rubro_confiable = corridas == 0
    if not rubro_confiable:
        log(f"  [Nación] {path.name}: ADVERTENCIA en {corridas} filas las columnas no siguen al "
            f"encabezado; el rubro (tipo_de_medio) queda vacio en todo el archivo")
        cont.avisar("pivot_rubro_sin_dato", sum(len(r) for _, r in lecturas))
    for prov, rubros in lecturas:
        for c, monto in rubros:
            out.append(registro(
                JURIS, anio, monto, path.name, proveedor=limpiar_str(prov),
                tipo_de_medio=_canon_rubro(val_cols[c][1]) if rubro_confiable else None))
            cont.ok()

    suma = sum(_centavos(r["monto"]) for r in out)
    total = leer_monto(total_tabla) if total_tabla else None
    if total is None:
        log(f"  [Nación] {path.name}: ADVERTENCIA sin fila 'Total general': no se puede conciliar")
        cont.avisar("pivot_sin_total_general")
    elif suma != _centavos(total):
        log(f"  [Nación] {path.name}: ADVERTENCIA NO concilia: filas cargadas suman "
            f"{suma / 100:,.2f} y el Total general es {total:,.2f}")
        cont.avisar("pivot_no_concilia_total_general")
    else:
        log(f"  [Nación] {path.name}: concilia con el Total general ({total:,.2f})")
    return out


# ---------------------------------------------------------------------------
# 4) PIVOT desde el PDF oficial (por coordenadas)
# ---------------------------------------------------------------------------

# PDF oficial de cada pivot y su SHA-256: argentina.gob.ar/sites/default/files/<pdf> (pagina
# "Pauta oficial", argentina.gob.ar/node/1759). Solo se lee el PDF revisado: si el archivo de la
# carpeta es otro (otra version publicada, el "sin IVA"), se avisa y se lee el texto.
PDF_DE_PIVOT = {
    "(nuevo v2) Pauta_por_Proveedor_conIVA-_-2009-mayo-oct.csv": (
        "pauta_por_proveedor_con_iva_2009.pdf",
        "8fd2e1d35b8210a3bc43e64d966d3a23e879b64ecb3fae5a23a9894553c1c3b4"),
    "(nuevo v2) Pauta_por_proveedor_conIVA_nov_dic_2009.csv": (
        "pauta_por_proveedor_coniva_nov_dic_2009.pdf",
        "8fd88ffc3a05fb493e20629b8e1089ded00bd4c2e78eed9e0b6ae47b0156098b"),
    "(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv": (
        "pauta_por_proveedor_coniva_ene_jun_2010.pdf",
        "e9d500b6f6c1bec06f971dc411ce9493327eab10eb841698e5188991b859a783"),
    "(nuevo v2)segundo_semestre_prov_rubro-2010.csv": (
        "segundo_semestre_prov_rubro_2010.pdf",
        "e0bee281c2b33e71e6e985086eb61cbf391c1efd95a120aeaada44521a3aead3"),
    "inversion_1er_Semestre_2012_proveedor_rubro.csv": (
        "inversion_1er_semestre_2012_proveedor_rubro.pdf",
        "a1bd51106c8f2844678d78c64505aee562c932f6fa14b065d640a39f421c5448"),
}

_RE_NUM_PDF = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_RE_MES = re.compile(r"[A-Za-z]{3}-\d{2}")


def _lineas_pdf(pagina):
    """Lineas de una pagina de pdfplumber: listas de palabras {text, x0, x1} de izquierda a
    derecha. Une los pedazos pegados de un mismo numero (en 2010-S2 "169.860.514,46" viene
    como "1" y "69.860.514,46")."""
    filas = []
    for w in sorted(pagina.extract_words(x_tolerance=1, y_tolerance=2),
                    key=lambda w: (w["top"], w["x0"])):
        if filas and abs(filas[-1][0] - w["top"]) <= 2:
            filas[-1][1].append(w)
        else:
            filas.append((w["top"], [w]))
    lineas = []
    for _, ws in filas:
        linea = []
        for w in sorted(ws, key=lambda w: w["x0"]):
            w = {"text": w["text"], "x0": w["x0"], "x1": w["x1"]}
            if (linea and re.fullmatch(r"[\d.,]+", linea[-1]["text"])
                    and re.fullmatch(r"[\d.,]+", w["text"]) and w["x0"] - linea[-1]["x1"] < 0.6):
                linea[-1] = dict(linea[-1], text=linea[-1]["text"] + w["text"], x1=w["x1"])
            else:
                linea.append(w)
        lineas.append(linea)
    return lineas


def _centavos_pdf(txt):
    return int(txt.replace(".", "").replace(",", ""))


def _tabla_pdf(lineas):
    """Lee un pivot desde las lineas del PDF (todas las paginas, en orden) y lo concilia.

    El encabezado es la primera linea con "Total general" (pivot por rubro) o con meses
    ("may-09", pivot por mes). Sus etiquetas son las palabras separadas por menos de 6 puntos;
    la primera (o las dos primeras en el pivot por mes: DENOMINACION y MEDIO) son de texto y el
    resto son las columnas de montos. Los montos estan alineados a la derecha: la columna de
    cada uno es la ultima cuyo encabezado empieza antes de donde termina el numero.

    Devuelve (modo, columnas, filas, problemas): columnas = [etiqueta], filas =
    [(proveedor, medio, [(columna, texto)])] sin la fila de totales. problemas es la lista de lo
    que no concilia, vacia si todo concilia:
      - en cada columna todos los montos terminan en el mismo x (+-1 punto): asi la columna de
        cada numero no depende de las sumas (en los 5 PDFs varian 0,1 puntos);
      - cada fila tiene un monto por columna y, si hay columna Total general, sus rubros suman
        ese total al centavo;
      - cada columna suma lo que dice la fila de totales (la "Total general" del pivot por
        rubro; en el pivot por mes, la ultima, que no tiene nombre). En el pivot por rubro, al
        centavo. Los pivots por mes (2009) no tienen total por fila y sus totales de columna se
        calcularon antes de redondear cada celda: cada celda puede diferir medio centavo, asi que
        se acepta hasta (celdas + 1) / 2 centavos. En 2009 la diferencia mayor es de 41 centavos
        en 531 celdas (cota 2,66) y la celda mas chica es de 87,12: una celda perdida o en otra
        columna no entra en la tolerancia."""
    modo = enc = None
    filas, totales, problemas = [], None, []
    bordes = {}   # columna -> x1 de sus montos
    for l in lineas:
        txt = " ".join(w["text"] for w in l)
        if modo is None:
            if "total general" in txt.lower():
                modo = "rubro"
            elif any(_RE_MES.fullmatch(w["text"]) for w in l):
                modo = "mes"
            else:
                continue
            etiquetas = []
            for w in l:
                if etiquetas and w["x0"] - etiquetas[-1][2] < 6:
                    etiquetas[-1] = (etiquetas[-1][0], etiquetas[-1][1] + " " + w["text"], w["x1"])
                else:
                    etiquetas.append((w["x0"], w["text"], w["x1"]))
            n_texto = 2 if modo == "mes" else 1
            x_medio = etiquetas[1][0] if modo == "mes" else None
            xs = [x0 for x0, _, _ in etiquetas[n_texto:]]
            columnas = [lab for _, lab, _ in etiquetas[n_texto:]]
            enc = txt
            continue
        if txt == enc:
            continue   # encabezado repetido en cada pagina
        nums = [w for w in l if w["x1"] >= xs[0] and _RE_NUM_PDF.fullmatch(w["text"])]
        textos = [w for w in l if w["x1"] < xs[0] and w["text"] != "$"]
        otros = [w["text"] for w in l if w["x1"] >= xs[0] and w not in nums
                 and w["text"] not in ("$", "-")]
        if otros:
            problemas.append(f"texto en la zona de montos: {txt!r}")
        if not nums:
            continue   # titulo, pie de pagina o fila sin montos (todo "-")
        prov = " ".join(w["text"] for w in textos if x_medio is None or w["x0"] < x_medio - 2)
        medio = " ".join(w["text"] for w in textos if x_medio is not None and w["x0"] >= x_medio - 2)
        celdas = [(max(k for k, x in enumerate(xs) if x <= w["x1"]), w["text"]) for w in nums]
        for (c, _), w in zip(celdas, nums):
            bordes.setdefault(c, []).append(w["x1"])
        if not prov or re.fullmatch(r"total( general)?", prov, re.I):
            if totales is not None:
                problemas.append(f"dos filas de totales: {txt!r}")
            totales = celdas
            continue
        # "TOTAL F.M. S.R.L." o "TOTAL PUBLIVIA SA" son proveedores: los PDFs no tienen
        # subtotales "Total <proveedor>" (si los tuvieran, las columnas no conciliarian)
        filas.append((prov, medio or None, celdas))

    if modo is None:
        return None, [], [], ["sin encabezado"]
    i_tot = next((k for k, lab in enumerate(columnas) if "total" in lab.lower()), None)
    if modo == "rubro" and i_tot is None:
        problemas.append("el encabezado no tiene la columna Total general")
    for c, xs1 in sorted(bordes.items()):
        if max(xs1) - min(xs1) > 1:
            problemas.append(f"columna {columnas[c]}: los montos no estan alineados "
                             f"(terminan entre x={min(xs1):.1f} y x={max(xs1):.1f})")
    por_col, n_col = [0] * len(columnas), [0] * len(columnas)
    for prov, _, celdas in filas:
        cs = [c for c, _ in celdas]
        if len(set(cs)) != len(cs):
            problemas.append(f"{prov}: dos montos en la misma columna")
        if i_tot is not None:
            tot = [_centavos_pdf(t) for c, t in celdas if c == i_tot]
            rubros = sum(_centavos_pdf(t) for c, t in celdas if c != i_tot)
            if tot != [rubros]:
                problemas.append(f"{prov}: los rubros suman {rubros / 100:,.2f} y el total es {tot}")
        for c, t in celdas:
            por_col[c] += _centavos_pdf(t)
            n_col[c] += 1
    if totales is None:
        problemas.append("sin fila de totales")
    else:
        fila_tot = {}
        for c, t in totales:
            if c in fila_tot:
                problemas.append(f"fila de totales: dos montos en {columnas[c]}")
            fila_tot[c] = _centavos_pdf(t)
        for c, lab in enumerate(columnas):
            tolerancia = 0 if modo == "rubro" else (n_col[c] + 1) // 2
            if abs(por_col[c] - fila_tot.get(c, 0)) > tolerancia:
                problemas.append(f"columna {lab}: las filas suman {por_col[c] / 100:,.2f} y el "
                                 f"total es {fila_tot.get(c, 0) / 100:,.2f}")
    return modo, columnas, filas, problemas


def _parse_pivot_pdf(path, anio, archivo, cont):
    """Registros del pivot leidos del PDF oficial, o None si el PDF no concilia.

    En el texto convertido desde el PDF las paginas sin encabezado vienen corridas (hasta 4
    columnas, de forma no uniforme), asi que la columna de cada monto, que es el rubro o el mes,
    no se puede leer de ahi. En el PDF cada palabra tiene su posicion real. Se carga solo si
    toda la tabla concilia (ver _tabla_pdf): si no, el llamador lee el texto.
    archivo: el archivo_origen de los registros (el nombre del CSV al que reemplaza)."""
    try:
        import pdfplumber
    except ImportError:
        raise SystemExit(f"[Nación] {path.name} necesita pdfplumber: pip install pdfplumber")
    with pdfplumber.open(path) as pdf:
        lineas = [l for p in pdf.pages for l in _lineas_pdf(p)]
    modo, columnas, filas, problemas = _tabla_pdf(lineas)
    if problemas:
        log(f"  [Nación] {path.name}: ADVERTENCIA el PDF no concilia ({len(problemas)} problemas, "
            f"p.ej. {problemas[0]}); se lee el texto")
        cont.avisar("pivot_pdf_no_concilia")
        return None
    out = []
    for prov, medio, celdas in filas:
        n = len(out)
        for c, t in celdas:
            monto = comun.normalizar_monto(t, ",")
            if monto is None or "total" in columnas[c].lower():
                continue   # celda 0,00 o el Total general de la fila
            if modo == "rubro":
                out.append(registro(JURIS, anio, monto, archivo, proveedor=limpiar_str(prov),
                                    tipo_de_medio=_canon_rubro(columnas[c])))
            else:
                out.append(registro(JURIS, anio, monto, archivo,
                                    fecha=normalizar_fecha(columnas[c], anio),
                                    proveedor=limpiar_str(prov), medio=limpiar_str(medio)))
        if len(out) == n:
            cont.descartar("fila_sin_valores")
    cont.ok(len(out))
    log(f"  [Nación] {path.name}: se lee el PDF oficial, que concilia "
        f"({len(out)} celdas, {sum(_centavos(r['monto']) for r in out) / 100:,.2f})")
    return out


def _pdf_oficial(csv_path):
    """PDF oficial del pivot que esta en la carpeta del CSV y es el revisado, o None."""
    nombre, sha = PDF_DE_PIVOT.get(csv_path.name, (None, None))
    pdf = csv_path.parent / nombre if nombre else None
    if pdf is None or not pdf.exists():
        return None
    real = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if real != sha:
        log(f"  [Nación] {pdf.name}: ADVERTENCIA no es el PDF revisado (SHA-256 {real}); se lee "
            f"el texto")
        return None
    return pdf


def _seleccionar_versiones(csvs):
    """Dedup: preferir '(nuevo v2)' > '(nuevo)' > nombre plano."""
    v2 = [f for f in csvs if "v2" in f.name.lower()]
    if v2:
        return v2
    nuevo = [f for f in csvs if "nuevo" in f.name.lower()]
    if nuevo:
        return nuevo
    return csvs


# ---------------------------------------------------------------------------
# Extractor principal
# ---------------------------------------------------------------------------

def _parse_curado(path, cont):
    """Lee un CSV curado de Nación (cols: proveedor, semestre, importe, tipo_de_medio).
    Usado como fallback para años sin fuente cruda en Datos crudos Pauta Oficial."""
    out = []
    filas = leer_dicts(path)
    leer_monto = parser_montos((d.get("importe") or d.get("total") for d in filas),
                               f"[Nación] {path.name}")
    for d in filas:
        monto = leer_monto(d.get("importe") or d.get("total"))
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        # semestre puede ser "2013-H1" → anio=2013
        sem = str(d.get("semestre") or "")
        anio = anio_de_texto(sem) or anio_de_texto(path.name)
        if not anio:
            cont.descartar("sin_anio")
            continue
        prov = limpiar_str(d.get("proveedor"))
        medio = limpiar_str(d.get("medio"))
        tipo = limpiar_str(d.get("tipo_de_medio"))
        if prov is None and medio is None:
            cont.descartar("sin_prov_ni_medio")
            continue
        out.append(registro(
            JURIS, anio, monto, path.name,
            proveedor=prov, medio=medio, tipo_de_medio=tipo))
        cont.ok()
    return out


# Nombre exacto del CSV que cubre enero 2013 – mayo 2014.
# Se parsea con un lector dedicado (solo toma filas de 2013;
# las de 2014 ya están cubiertas por pauta-oficial-2014.csv).
_CSV_ENE2013 = "DatosPublicidadOficialEnero2013_Mayo2014.csv"


def _parse_enero2013(path, cont):
    """Parsea DatosPublicidadOficialEnero2013_Mayo2014.csv.

    Columnas (separadas por ';'):
      ORDEN DE PUBLICIDAD ; IMPORTE NETO ; ANUNCIANTE ; CAMPAÑA ;
      RUBRO ; NOMBRE O RAZON SOCIAL DEL PROVEEDOR ; PREST.

    'PREST.' tiene formato 'abr-13', 'ene-14', etc.
    Solo se extraen filas de 2013 para evitar duplicados con pauta-oficial-2014.csv.
    """
    import csv as _csv
    out = []
    txt = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as fh:
                txt = fh.read()
            break
        except UnicodeDecodeError:
            continue
    if not txt:
        return out

    rows = list(_csv.reader(__import__("io").StringIO(txt), delimiter=";"))
    if not rows:
        return out

    # Mapear columnas por nombre (insensible a mayúsculas)
    hdr = [c.strip().lower() for c in rows[0]]
    def ci(name):
        for i, h in enumerate(hdr):
            if name in h:
                return i
        return None

    i_res   = ci("orden")
    i_monto = ci("importe")
    i_rubro = ci("rubro")
    i_prov  = ci("nombre") or ci("razon social")
    i_fecha = ci("prest")
    leer_monto = parser_montos(
        (row[i_monto] for row in rows[1:] if i_monto is not None and i_monto < len(row)),
        f"[Nación] {path.name}")

    for row in rows[1:]:
        if i_fecha is None or i_fecha >= len(row):
            continue
        fecha_raw = row[i_fecha].strip()
        # normalizar_fecha convierte "abr-13" → "2013-04-01"
        fecha = normalizar_fecha(fecha_raw)
        if not fecha or not fecha.startswith("2013"):
            cont.descartar("fila_no_2013")
            continue
        monto = leer_monto(row[i_monto] if i_monto is not None else None)
        if monto is None:
            cont.descartar("monto_invalido")
            continue
        prov = limpiar_str(row[i_prov] if i_prov is not None else None)
        tipo = _canon_rubro(row[i_rubro].strip() if i_rubro is not None else None)
        res  = limpiar_str(row[i_res] if i_res is not None else None)
        out.append(registro(
            JURIS, 2013, monto, path.name,
            fecha=fecha, proveedor=prov, tipo_de_medio=tipo, resolucion=res,
        ))
        cont.ok()
    return out


def extraer():
    log("[Nación] iniciando extraccion")
    registros = []
    cont = Contador("[Nación]")

    if not DIR_NACION.exists():
        log(f"[Nación] ADVERTENCIA: no existe {DIR_NACION}")
        return registros

    # --- archivos limpios en root (saltear el CSV mixto 2013-2014) ---
    for f in sorted(DIR_NACION.glob("*.csv")):
        if f.name == _CSV_ENE2013:
            continue   # se procesa por separado abajo
        registros += _parse_limpio(f, cont)

    # --- CSV enero 2013 – mayo 2014: solo filas de 2013 ---
    f_2013 = DIR_NACION / _CSV_ENE2013
    if f_2013.exists():
        log(f"[Nación] leyendo fuente cruda 2013: {_CSV_ENE2013}")
        registros += _parse_enero2013(f_2013, cont)

    # --- subcarpetas de años pivot / 2011 ---
    for ydir in sorted(p for p in DIR_NACION.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}", p.name)):
        anio = int(ydir.name)
        csvs = sorted(ydir.glob("*.csv"))
        if not csvs:
            continue
        if anio == 2011:
            for f in csvs:
                registros += _parse_2011(f, cont)
            continue
        for f in _seleccionar_versiones(csvs):
            pdf = _pdf_oficial(f)
            regs = _parse_pivot_pdf(pdf, anio, f.name, cont) if pdf else None
            registros += regs if regs is not None else _parse_pivot(f, anio, cont)

    # --- fallback: curado para años sin fuente cruda ---
    anios_cubiertos = {r["anio"] for r in registros if r["anio"]}
    dir_curado_nacion = DIR_CURADO / "Nacion"
    if dir_curado_nacion.exists():
        for f in sorted(dir_curado_nacion.glob("Nacion_*.csv")):
            anio_f = anio_de_texto(f.name)
            if anio_f and anio_f not in anios_cubiertos:
                log(f"[Nación] leyendo curado (sin fuente cruda): {f.name}")
                registros += _parse_curado(f, cont)

    cont.resumen()
    log(f"[Nación] total: {len(registros)} registros")
    return registros


if __name__ == "__main__":
    regs = extraer()
    print(f"\nNación -> {len(regs)} registros")
    for r in regs[:3]:
        print(r)
    from collections import Counter
    print("por anio:", dict(sorted(Counter(r["anio"] for r in regs).items())))
    print("con proveedor:", sum(1 for r in regs if r["proveedor"]))
    print("con medio:", sum(1 for r in regs if r["medio"]))
