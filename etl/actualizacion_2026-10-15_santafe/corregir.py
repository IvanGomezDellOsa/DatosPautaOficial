# -*- coding: utf-8 -*-
"""
corregir.py  —  Santa Fe: corrige los errores de carga encontrados por la auditoría de fuentes.

Santa Fe no se re-extrae en el ETL: sus filas vienen de un CSV curado a mano (santa_fe_curado.csv,
fuera del repo). Este script lee los PDF oficiales por geometría y corrige solo lo confirmado:

  radio2008     `Radio 2008 (II).pdf` es el mismo cuadro que `Radio 2008.pdf` (el portal publica
                los dos; solo cambia el pie "Página N de 2"). Se quitan sus 564 filas.
  sf2011        Gráfica, Internet, Radio y TV 2011: el curado cargó solo los primeros medios de
                cada PDF. Se agregan los medios que faltan.
  tv2013        TV 2013: lo mismo (faltan 10 medios).
  vp2017        Vía pública 2017: falta PUBLICIDAD SARMIENTO.
  internet2016  Internet 2016: no estaba. El PDF usa una fuente sin mapa Unicode: cada letra y
                cada dígito están reemplazados por otro símbolo, siempre el mismo. Se decodifica
                con una tabla fija (MAPA_2016), verificada contra la imagen de cada página, y
                cada monto se controla con la suma de su fila y con el resumen oficial.
  chicos        Celdas sueltas que el curado no leyó: octubre de 2 medios de Vía pública 2009
                (el PDF pega los títulos "Septiembre" y "Octubre") y FM 88.9 PASION de María
                Luisa en Radio 2015 y 2016 (localidad de dos palabras).
  grafica2013   Gráfica 2013 (faltan 97 medios). NO se aplica por defecto: el detalle concilia
                al centavo con su propia fila de totales, pero suma 1.925,25 más que el resumen
                oficial por tipo de medio, todo en julio. Queda para decisión del usuario.

Reglas:
- Las filas que ya están en la base quedan idénticas byte a byte y en el mismo orden. Las filas
  nuevas de un archivo van al final de su bloque; Internet 2016, al final del CSV (junto a
  Estática 2016, el otro archivo de 2016 que el curado agregó al final).
- Cada fila del PDF se valida con su total impreso, y cada columna con la fila de totales.
- Cada fila de la base se empareja con una celda del PDF (mismo mes y monto, y el mismo renglón
  para todo el medio). Si alguna no aparece, no se carga nada.
- El nombre de un medio nuevo sigue el formato de las filas del mismo archivo: "Medio
  (Localidad)" o "Localidad (Medio)"; sin localidad, el texto tal cual.

Uso (desde la raíz del repo; `-I` para no importar nada de la carpeta de crudos):
  python -I etl/actualizacion_2026-10-15_santafe/corregir.py ENTRADA.csv CRUDOS
      [--aplicar radio2008,sf2011,...] [--salida etl/data/pauta_oficial_unificado_v2.csv]
      [--informe DIR]

ENTRADA.csv es el CSV publicado antes (SHA-256 ENTRADA_SHA256). CRUDOS es la carpeta
crudos_2026-10-14 de la auditoría de fuentes, con su manifest_descargas.tsv. Requiere pdfplumber.
"""

import argparse
import csv
import hashlib
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "actualizacion_2026-10-15"))
from regenerar import a_lineas, clave, comun, fila_dict, leer_manifest, sha256, _tsv  # noqa: E402

ENTRADA_SHA256 = "dbe7b01fc41e9051972b237799ad8de24c475fe10ba0f3f1b02e5dfbb431c74a"
JURIS = "Santa Fe"

# archivo_origen -> n del manifest de la auditoría
RADIO_2008, RADIO_2008_II = ("Radio 2008.pdf", 172), ("Radio 2008 (II).pdf", 173)

# completar: (corrección, n, archivo_origen, año, tipo_de_medio, x donde empieza la segunda
#             columna de texto (None: una sola), renglón suelto de un nombre partido: va con la
#             fila "siguiente" o la "anterior")
COMPLETAR = [
    ("sf2011", 193, "Gràfica 2011.pdf", 2011, "Gráfica", 151, "siguiente"),
    ("sf2011", 194, "Internet 2011.pdf", 2011, "Digital", 195, "siguiente"),
    ("sf2011", 196, "Radio 2011.pdf", 2011, "Radio", 184, "siguiente"),
    ("sf2011", 197, "TV 2011.pdf", 2011, "TV", 170, "siguiente"),
    ("grafica2013", 91, "GRAFICA 2013.pdf", 2013, "Gráfica", 170, "siguiente"),
    ("tv2013", 95, "TELE 2013.pdf", 2013, "TV", 170, "siguiente"),
    ("vp2017", 126, "Vía pública 2017.pdf", 2017, "Via Publica", None, "siguiente"),
    ("chicos", 182, "Vía pública 2009.pdf", 2009, "Via Publica", None, "siguiente"),
    ("chicos", 109, "Radios 2015.pdf", 2015, "Radio", 110, "siguiente"),
    ("chicos", 116, "Informe inversión en radio 2016.pdf", 2016, "Radio", 80, "anterior"),
]
INTERNET_2016 = (115, "Informe inversión publicitaria internet 2016.pdf", 2016, "Digital")
CORRECCIONES = ["radio2008", "sf2011", "tv2013", "vp2017", "internet2016", "chicos", "grafica2013"]
POR_DEFECTO = [c for c in CORRECCIONES if c != "grafica2013"]

# 2011: filas del PDF cuyo total impreso difiere en 1 centavo de la suma de sus meses (la planilla
# de origen redondeó cada celda por separado). Se cargan las celdas tal como están impresas.
REDONDEO_FUENTE = {"Gràfica 2011.pdf": 5, "TV 2011.pdf": 1}

# Resúmenes oficiales: n del manifest. Por tipo de medio (2013-2017) o por mes, todos los tipos
# juntos (2008, 2009 y 2011).
RESUMEN_TIPO = {2013: 97, 2015: 112, 2016: 120, 2017: 127}
RESUMEN_MES = {2008: 178, 2009: 185, 2011: 200}
TIPO_RESUMEN = {"Gráfico": "Gráfica", "Televisivo": "TV", "Radial": "Radio", "Internet": "Digital",
                "Estática": "Via Publica"}

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
         "diciembre": 12}
NOMBRES_MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
NUM = re.compile(r"^(\d{1,3}(\.\d{3})*(,\d\d?)?|\d+(,\d\d?)?|,\d\d)$")
PIE = re.compile(r"(?i)(p[aá]gina:?\s*)?\d+\s*de\s*\d+")        # "Página 1 de 3"
FRAG = re.compile(r"^[\d.,]+$")
ES_TOTAL = re.compile(r"(?i)^total(es)?:?$")
# renglones de texto que no son parte de un nombre: pie de página, fecha del reporte, títulos
RUIDO = re.compile(r"(?i)p[aá]gina|fecha del reporte|informe de|enero a|tipo de medio|ministerio|"
                   r"secretar[ií]a|direcci[oó]n general|inversion en publicidad|subtotal")


def dec(s):
    s = s.replace(".", "").replace(",", ".")
    return Decimal("0" + s if s.startswith(".") else s)


def monto_txt(v):
    """Como unificar.py: 2 decimales, sin ceros ni punto finales."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


# ---------------------------------------------------------------------------
# Lectura geométrica de los PDF "Informe de gastos de publicidad por medio"
# ---------------------------------------------------------------------------

def _lineas(page):
    ws = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
    lineas = []
    for w in sorted(ws, key=lambda w: (round(w["top"]), w["x0"])):
        if lineas and abs(lineas[-1][0] - w["top"]) <= 2.5:
            lineas[-1][1].append(w)
        else:
            lineas.append([w["top"], [w]])
    res = []
    for top, ws in lineas:
        unidas = []
        for w in sorted(ws, key=lambda w: w["x0"]):   # números partidos en dos fragmentos
            if unidas and FRAG.match(w["text"]) and FRAG.match(unidas[-1]["text"]) \
                    and w["x0"] - unidas[-1]["x1"] < 1.5:
                unidas[-1] = {**unidas[-1], "text": unidas[-1]["text"] + w["text"], "x1": w["x1"]}
            else:
                unidas.append(dict(w))
        res.append((top, unidas))
    return res


def _titulos(linea):
    """Columnas de un renglón de títulos: [(mes o "total", x)], o None si no es de títulos.
    Separa los títulos pegados ("SeptiembrOectubre") repartiendo el ancho de la palabra."""
    cols, solo = [], True
    for w in linea:
        t = w["text"].lower()
        if t in MESES:
            cols.append((MESES[t], w["x0"]))
        elif t == "total":
            cols.append(("total", w["x0"]))
        elif t.isalpha() and sum(1 for m in NOMBRES_MES if m[1:5] in t) >= 2:
            pos = sorted((t.find(m[1:5]) - 1, MESES[m]) for m in NOMBRES_MES if m[1:5] in t)
            cols += [(m, w["x0"] + (w["x1"] - w["x0"]) * max(p, 0) / len(t)) for p, m in pos]
        elif t not in ("medio", "localidad", "nombremedio", "nombre", "del"):
            solo = False
    meses = sum(1 for c, _ in cols if c != "total")
    return cols if (meses >= 3 or (cols and solo)) else None


def leer_pdf(path, xloc, sueltos_con):
    """Filas del PDF: [{medio, loc, celdas {mes: Decimal}, total, pagina}] y la fila de totales.
    Las tablas anchas partidas por columnas (ene-oct en unas páginas, nov-dic-total en otras)
    se unen por orden de fila, y cada fila unida tiene que cuadrar con su total."""
    grupos, firma, cols, sueltos, previa = [], None, None, [], None
    with pdfplumber.open(path) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            for top, linea in _lineas(page):
                junto = " ".join(w["text"] for w in linea)
                con_montos = any("," in w["text"] and NUM.match(w["text"]) for w in linea)
                if not con_montos and (PIE.fullmatch(junto) or RUIDO.search(junto)):
                    continue     # (un medio puede llamarse "PAGINA 12")
                t = _titulos(linea)
                if t:
                    cols, sueltos, previa = t, [], None
                    if tuple(c for c, _ in t) != firma:
                        firma = tuple(c for c, _ in t)
                        grupos.append([])
                    continue
                if cols is None:
                    continue
                x_min = min(x for _, x in cols) - 2
                nums = [w for w in linea if NUM.match(w["text"]) and w["x1"] > x_min]
                texto = [w for w in linea if w not in nums and not (w["text"] == "-" and w["x0"] > x_min)]
                if not nums:
                    if sueltos_con == "anterior" and previa is not None:
                        previa["sueltos"] += texto
                    else:
                        sueltos += texto
                    continue
                celdas, total = {}, None
                for w in nums:
                    cand = [(c, x) for c, x in cols if x < w["x1"] - 2]
                    if not cand:
                        raise SystemExit(f"ERROR {path.name} p{pn}: monto sin columna {w['text']}")
                    col = max(cand, key=lambda cx: cx[1])[0]
                    if col == "total":
                        if total is not None:
                            raise SystemExit(f"ERROR {path.name} p{pn}: dos totales en una fila")
                        total = dec(w["text"])
                    elif col in celdas:
                        raise SystemExit(f"ERROR {path.name} p{pn}: dos montos en {col}")
                    else:
                        celdas[col] = dec(w["text"])
                fila = {"pagina": pn, "texto": texto, "sueltos": sueltos, "celdas": celdas, "total": total}
                sueltos, previa = [], fila
                grupos[-1].append(fila)
    filas = grupos[0]
    for g in grupos[1:]:
        if len(g) != len(filas) or any(b["texto"] or b["sueltos"] for b in g):
            raise SystemExit(f"ERROR {path.name}: tabla partida con filas que no se corresponden")
        for a, b in zip(filas, g):
            for m, v in b["celdas"].items():
                if m in a["celdas"]:
                    raise SystemExit(f"ERROR {path.name}: mes repetido al unir columnas")
                a["celdas"][m] = v
            if b["total"] is not None:
                if a["total"] is not None:
                    raise SystemExit(f"ERROR {path.name}: total repetido al unir columnas")
                a["total"] = b["total"]
    res, totales = [], None
    for f in filas:
        texto = " ".join(w["text"] for w in f["texto"])
        if ES_TOTAL.match(texto):
            totales = f
            continue

        def partes(ws):
            if xloc is None:
                return " ".join(w["text"] for w in ws), ""
            return (" ".join(w["text"] for w in ws if w["x0"] < xloc - 2),
                    " ".join(w["text"] for w in ws if w["x0"] >= xloc - 2))
        izq, der = partes(f["texto"])
        s_izq, s_der = partes(f["sueltos"])
        if sueltos_con == "siguiente":   # el renglón suelto está arriba: se lee primero
            izq, der = " ".join(x for x in (s_izq, izq) if x), " ".join(x for x in (s_der, der) if x)
        else:
            izq, der = " ".join(x for x in (izq, s_izq) if x), " ".join(x for x in (der, s_der) if x)
        res.append({"pagina": f["pagina"], "izq": izq, "der": der,
                    "celdas": {m: v for m, v in f["celdas"].items() if v}, "total": f["total"]})
    if totales is None:
        raise SystemExit(f"ERROR {path.name}: no se encontró la fila de totales")
    return res, totales


def nombre(fila):
    """"Izquierda (derecha)", en el orden de las columnas del PDF, como el resto del archivo:
    "Medio (Localidad)" o "Localidad (Medio)". Sin segunda columna, o si repite lo que dice la
    primera (sin distinguir mayúsculas ni tildes), el texto de la primera, como hizo el curado."""
    izq, der = fila["izq"], fila["der"]
    plano = lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    if not der or plano(der) in plano(izq):
        return izq
    return f"{izq} ({der})" if izq else der


# ---------------------------------------------------------------------------
# Internet 2016: fuente sin mapa Unicode
# ---------------------------------------------------------------------------

# Código del PDF -> carácter. Los dígitos y los separadores están en el texto como otros signos
# ASCII ("30.240,00" se lee ")*+,-*.**"); el resto como (cid:N). Verificado contra la imagen de
# las 5 páginas (incluidos los acentos graves de "San Josè" y "Constituciòn", que la fuente
# escribe así).
MAPA_2016 = {
    "*": "0", "4": "1", ",": "2", ")": "3", "-": "4", "1": "5", "/": "6", "3": "7", "0": "8",
    "2": "9", "+": ".", ".": ",",
    "<1>": "M", "<2>": "i", "<3>": "n", "<4>": "s", "<5>": "t", "<6>": "e", "<7>": "r", "<8>": "o",
    "<9>": " ", "<10>": "d", "<11>": "G", "<12>": "b", "<13>": "y", "<14>": "R", "<15>": "f",
    "<16>": "m", "<17>": "a", "<18>": "l", "<19>": "E", "<20>": "S", "<21>": "c", "<23>": "C",
    "<24>": "u", "<26>": "D", "<27>": "P", "<28>": "A", "<29>": "v", "<30>": "T", "<31>": "p",
    "7": "W", "8": "w", '"': "L", "!": "I", "'": "O", "#": "F", "$": "z", "%": "J", "&": "g",
    "(": "N", "9": "U", "6": "B", ":": "Z", "5": "V", "<": "H", ";": "Y", "=": "è", ">": "q",
    "?": "h", "@": "j", "A": "Ñ", "B": "X", "C": "ñ", "D": "ú", "E": "Q", "F": "ò", "G": "/",
    "H": "-", "I": "k",
}
FUENTE_2016 = "DYYRVH+ArialMT"
MONTO_2016 = re.compile(r"^\d{1,3}(\.\d{3})*,\d\d$")


def leer_internet_2016(path):
    """[{medio, loc, celdas, total}]: cada fila trae 13 montos (12 meses y total, con 0,00
    escrito) en columnas de x fija, y la localidad en el renglón de abajo."""
    filas, xs = [], defaultdict(set)
    with pdfplumber.open(path) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            chars = sorted((c for c in page.chars if c["fontname"].endswith(FUENTE_2016)),
                           key=lambda c: (round(c["top"]), c["x0"]))
            renglones = []
            for c in chars:
                if renglones and abs(renglones[-1][0] - c["top"]) <= 2.5:
                    renglones[-1][1].append(c)
                else:
                    renglones.append([c["top"], [c]])
            datos, textos = [], []
            for top, cs in renglones:
                palabras = []
                for c in sorted(cs, key=lambda c: c["x0"]):
                    m = re.fullmatch(r"\(cid:(\d+)\)", c["text"])
                    cod = f"<{m.group(1)}>" if m else c["text"]
                    if cod not in MAPA_2016:
                        raise SystemExit(f"ERROR Internet 2016 p{pn}: código sin tabla {cod!r}")
                    if palabras and c["x0"] - palabras[-1]["x1"] < 1.0:
                        palabras[-1]["t"] += MAPA_2016[cod]
                        palabras[-1]["x1"] = c["x1"]
                    else:
                        palabras.append({"t": MAPA_2016[cod], "x0": c["x0"], "x1": c["x1"]})
                if palabras[0]["t"] == "Localidad":
                    continue
                montos = [p for p in palabras if MONTO_2016.match(p["t"])]
                (datos if montos else textos).append([top, palabras, montos])
            for top, palabras, _ in textos:
                duenos = [d for d in datos if 0 < top - d[0] <= 8]
                if len(duenos) != 1 or len(duenos[0]) > 3:
                    raise SystemExit(f"ERROR Internet 2016 p{pn}: localidad sin fila ({top:.0f})")
                duenos[0].append(" ".join(p["t"] for p in palabras))
            for d in datos:
                top, palabras, montos = d[:3]
                if len(montos) != 13 or len(d) != 4:
                    raise SystemExit(f"ERROR Internet 2016 p{pn}: fila incompleta ({top:.0f})")
                for i, p in enumerate(montos):
                    xs[i].add(round(p["x0"]))
                v = [dec(p["t"]) for p in montos]
                filas.append({"pagina": pn, "izq": " ".join(p["t"] for p in palabras if p not in montos),
                              "der": d[3], "celdas": {m + 1: v[m] for m in range(12) if v[m]},
                              "total": v[12]})
    # cada columna en la misma x en todas las páginas (los montos están alineados a la izquierda)
    if any(max(x) - min(x) > 1 for x in xs.values()) or \
            sorted(min(x) for x in xs.values()) != [min(xs[i]) for i in range(13)]:
        raise SystemExit("ERROR Internet 2016: las columnas no están alineadas")
    return filas


# ---------------------------------------------------------------------------
# Resúmenes oficiales
# ---------------------------------------------------------------------------

MONEDA = re.compile(r"^\d{1,3}(\.\d{3})*,\d\d$|^\d+,\d\d$")


def leer_resumen_tipo(path):
    """{tipo_de_medio: [12 meses, total]} del "Informe mensual de publicidad por tipo de medio"."""
    res = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for linea in (page.extract_text() or "").splitlines():
                toks = linea.split()
                if toks and toks[0] in TIPO_RESUMEN:
                    nums = [Decimal(0) if t == "-" else dec(t) for t in toks[1:] if MONEDA.match(t) or t == "-"]
                    if len(nums) < 13:
                        raise SystemExit(f"ERROR {path.name}: fila incompleta {linea!r}")
                    if sum(nums[:12]) != nums[12]:
                        raise SystemExit(f"ERROR {path.name}: la fila {toks[0]} no suma su total")
                    res[TIPO_RESUMEN[toks[0]]] = nums[:13]
    return res


def leer_resumen_mes(path):
    """[12 meses, total] de la columna TOTAL del "Resumen inversión en publicidad" anual."""
    meses, total = {}, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for linea in (page.extract_text() or "").splitlines():
                toks = linea.split()
                if not toks:
                    continue
                nums = [dec(t) for t in toks[1:] if MONEDA.match(t)]
                if toks[0].lower() in MESES and len(nums) == 3:
                    meses[MESES[toks[0].lower()]] = nums[2]
                elif toks[0].upper().startswith("TOTAL") and len(nums) == 3:
                    total = nums[2]
    # 2009: los meses suman 1 centavo menos que el total impreso (redondeo de la fuente)
    if len(meses) != 12 or total is None or abs(sum(meses.values()) - total) > Decimal("0.01"):
        raise SystemExit(f"ERROR {path.name}: resumen mensual incompleto")
    return [meses[m] for m in range(1, 13)] + [total]


# ---------------------------------------------------------------------------

def crudo(carpeta, manifest, n, nombre_esperado=None):
    fila = manifest[n]
    path = Path(carpeta) / fila["ruta"].replace("\\", "/")
    if fila["grupo"] != "C-SantaFe" or (nombre_esperado and fila["archivo"] != nombre_esperado):
        raise SystemExit(f"ERROR: la fila {n} del manifest no es {nombre_esperado}")
    real = sha256(path)
    if real != fila["sha256"]:
        raise SystemExit(f"ERROR {path}: SHA-256 {real} distinto del manifest ({fila['sha256']})")
    return path, fila


def emparejar(archivo, filas_pdf, filas_base):
    """Empareja cada medio de la base con una fila del PDF: todas sus celdas (mes, monto) en ese
    renglón, y el nombre más parecido entre los renglones posibles. Devuelve {fila: medio}."""
    grupos = defaultdict(list)
    for r in filas_base:
        grupos[r["medio"]].append((int(r["fecha"][5:7]), Decimal(r["monto"])))
    asignado = {}
    for medio, celdas in grupos.items():
        if len(set(celdas)) != len(celdas):
            raise SystemExit(f"ERROR {archivo}: {medio} tiene dos montos en el mismo mes")
        cand = [k for k, f in enumerate(filas_pdf)
                if k not in asignado and all(f["celdas"].get(m) == v for m, v in celdas)]
        if not cand:
            raise SystemExit(f"ERROR {archivo}: {medio} no está en ningún renglón del PDF")
        def parecido(k):
            f = filas_pdf[k]
            return max(SequenceMatcher(None, norm(medio), norm(t)).ratio()
                       for t in (f["izq"] + f["der"], f["der"] + f["izq"], f["izq"]))
        cand.sort(key=parecido, reverse=True)
        if len(cand) > 1 and parecido(cand[0]) - parecido(cand[1]) < 0.15:
            raise SystemExit(f"ERROR {archivo}: {medio} es ambiguo entre renglones {cand[:2]}")
        if parecido(cand[0]) < 0.4:
            raise SystemExit(f"ERROR {archivo}: {medio} no se parece a {filas_pdf[cand[0]]['izq']}")
        asignado[cand[0]] = medio
    return asignado


def registro(anio, mes, medio, tipo, monto, archivo):
    return comun.registro(JURIS, anio, monto_txt(monto), archivo, fecha=f"{anio}-{mes:02d}-01",
                          medio=medio, tipo_de_medio=tipo)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("crudos")
    ap.add_argument("--aplicar", default=",".join(POR_DEFECTO))
    ap.add_argument("--salida")
    ap.add_argument("--informe")
    a = ap.parse_args()
    aplicar = [c.strip() for c in a.aplicar.split(",") if c.strip()]
    if not set(aplicar) <= set(CORRECCIONES):
        raise SystemExit(f"ERROR: correcciones válidas: {CORRECCIONES}")

    if sha256(a.entrada) != ENTRADA_SHA256:
        raise SystemExit(f"ERROR: {a.entrada} no es el CSV revisado (SHA-256 {sha256(a.entrada)})")
    manifest = leer_manifest(a.crudos)
    texto = Path(a.entrada).read_bytes().decode("utf-8")
    encabezado, *viejas = texto.split("\n")
    if viejas[-1] != "":
        raise SystemExit("ERROR: el CSV no termina en salto de línea")
    viejas = [l + "\n" for l in viejas[:-1]]
    claves = [clave(l) for l in viejas]
    bloques = defaultdict(list)
    for i, k in enumerate(claves):
        if k[0] == JURIS:
            bloques[k[1]].append(i)
    for archivo, ids in bloques.items():
        if ids != list(range(ids[0], ids[-1] + 1)):
            raise SystemExit(f"ERROR: {archivo} no es un bloque contiguo")

    quitar = set()                    # índices de filas viejas que salen
    agregar = defaultdict(list)       # índice de la última fila del bloque -> líneas nuevas
    al_final = []                     # líneas nuevas al final del CSV
    informe, emparejados, usados = [], [], []

    # --- Radio 2008 (II) ---------------------------------------------------------------------
    if "radio2008" in aplicar:
        pa, ma = crudo(a.crudos, manifest, RADIO_2008[1], RADIO_2008[0])
        pb, mb = crudo(a.crudos, manifest, RADIO_2008_II[1], RADIO_2008_II[0])
        usados += [(RADIO_2008[0], pa, ma), (RADIO_2008_II[0], pb, mb)]

        def palabras(p):
            with pdfplumber.open(p) as pdf:
                return [(n, w["text"], round(w["x0"], 1), round(w["top"], 1))
                        for n, pg in enumerate(pdf.pages, 1) for w in pg.extract_words()]
        wa, wb = palabras(pa), palabras(pb)
        pie = [w for w in wb if w not in set(wa)]
        if [w for w in wa if w not in set(wb)] or \
                " ".join(t for _, t, _, _ in pie) != "Página 1 de 2 Página 2 de 2":
            raise SystemExit("ERROR: Radio 2008 (II) no es el mismo cuadro que Radio 2008")
        fa = [fila_dict(viejas[i]) for i in bloques[RADIO_2008[0]]]
        fb = [fila_dict(viejas[i]) for i in bloques[RADIO_2008_II[0]]]
        sin_origen = lambda fs: [{k: v for k, v in f.items() if k != "archivo_origen"} for f in fs]
        if sin_origen(fa) != sin_origen(fb):
            raise SystemExit("ERROR: las filas de Radio 2008 y Radio 2008 (II) no son idénticas")
        quitar |= set(bloques[RADIO_2008_II[0]])
        tot = sum(Decimal(f["monto"]) for f in fb)
        informe.append({"correccion": "radio2008", "archivo_origen": RADIO_2008_II[0],
                        "filas_antes": len(fb), "filas_despues": 0, "total_antes": tot,
                        "total_despues": Decimal(0), "total_pdf": None,
                        "nota": f"mismo cuadro que {RADIO_2008[0]}: {len(wa)} palabras en la misma "
                                f"posición; {len(fb)} filas idénticas en la base"})

    # --- medios que faltan en archivos ya cargados ----------------------------------------------
    for corr, n, archivo, anio, tipo, xloc, sueltos_con in COMPLETAR:
        if corr not in aplicar:
            continue
        path, man = crudo(a.crudos, manifest, n)
        usados.append((archivo, path, man))
        filas_pdf, totales = leer_pdf(path, xloc, sueltos_con)
        no_cuadran = [f for f in filas_pdf if f["total"] is None or
                      abs(sum(f["celdas"].values()) - f["total"]) > Decimal("0.01")]
        de_un_centavo = [f for f in filas_pdf if f not in no_cuadran and sum(f["celdas"].values()) != f["total"]]
        if no_cuadran or len(de_un_centavo) != REDONDEO_FUENTE.get(archivo, 0):
            raise SystemExit(f"ERROR {archivo}: filas que no cuadran con su total "
                             f"{[(f['izq'], f['total']) for f in no_cuadran + de_un_centavo]}")
        suma_mes = Counter()
        for f in filas_pdf:
            suma_mes.update(f["celdas"])
        dif_mes = {m: suma_mes[m] - totales["celdas"].get(m, 0) for m in range(1, 13)}
        if any(abs(d) > Decimal("0.01") for d in dif_mes.values()):
            raise SystemExit(f"ERROR {archivo}: las columnas no suman la fila de totales {dif_mes}")
        total_pdf = sum(suma_mes.values())

        ids = bloques[archivo]
        filas_base = [fila_dict(viejas[i]) for i in ids]
        if any(f["anio"] != str(anio) or f["tipo_de_medio"] != tipo or f["proveedor"] or f["resolucion"]
               for f in filas_base):
            raise SystemExit(f"ERROR {archivo}: filas de la base con otro año, tipo o campos")
        asignado = emparejar(archivo, filas_pdf, filas_base)
        nuevas = []
        for k, f in enumerate(filas_pdf):
            en_base = {int(r["fecha"][5:7]) for r in filas_base if r["medio"] == asignado.get(k)}
            medio = asignado.get(k) or nombre(f)
            for mes in sorted(f["celdas"]):
                if mes not in en_base:
                    nuevas.append(registro(anio, mes, medio, tipo, f["celdas"][mes], archivo))
            emparejados.append([archivo, f["pagina"], f["izq"], f["der"], asignado.get(k, ""),
                                "" if k in asignado else medio,
                                len(f["celdas"]) - len(en_base), f"{sum(f['celdas'].values()):.2f}"])
        lineas = a_lineas(nuevas)
        agregar[ids[-1]] += lineas
        antes = sum(Decimal(f["monto"]) for f in filas_base)
        despues = antes + sum(Decimal(fila_dict(l)["monto"]) for l in lineas)
        if despues != total_pdf:
            raise SystemExit(f"ERROR {archivo}: no concilia con el PDF ({despues} contra {total_pdf})")
        informe.append({"correccion": corr, "archivo_origen": archivo, "filas_antes": len(ids),
                        "filas_despues": len(ids) + len(lineas), "total_antes": antes,
                        "total_despues": despues, "total_pdf": total_pdf, "total_impreso": totales["total"],
                        "nota": f"{len(filas_pdf)} medios en el PDF, {len(asignado)} ya cargados (el formato "
                                f"de nombre reproduce {sum(1 for k, m in asignado.items() if nombre(filas_pdf[k]) == m)})"
                                + (f"; {len(de_un_centavo)} filas con total impreso a 1 centavo de la "
                                   f"suma de sus meses (redondeo de la fuente)" if de_un_centavo else "")})

    # --- Internet 2016 -------------------------------------------------------------------------
    if "internet2016" in aplicar:
        n, archivo, anio, tipo = INTERNET_2016
        if archivo in bloques:
            raise SystemExit(f"ERROR: {archivo} ya está en el CSV")
        path, man = crudo(a.crudos, manifest, n)
        usados.append((archivo, path, man))
        filas_pdf = leer_internet_2016(path)
        if any(sum(f["celdas"].values()) != f["total"] for f in filas_pdf):
            raise SystemExit("ERROR Internet 2016: filas que no cuadran con su total")
        nuevas = [registro(anio, mes, nombre(f), tipo, f["celdas"][mes], archivo)
                  for f in filas_pdf for mes in sorted(f["celdas"])]
        for f in filas_pdf:
            emparejados.append([archivo, f["pagina"], f["izq"], f["der"], "", nombre(f),
                                len(f["celdas"]), f"{f['total']:.2f}"])
        al_final += a_lineas(nuevas)
        total = sum(f["total"] for f in filas_pdf)
        informe.append({"correccion": "internet2016", "archivo_origen": archivo, "filas_antes": 0,
                        "filas_despues": len(nuevas), "total_antes": Decimal(0), "total_despues": total,
                        "total_pdf": total, "nota": f"{len(filas_pdf)} medios; fuente sin mapa Unicode, "
                                                    f"decodificada con MAPA_2016"})

    # --- armado y verificación -------------------------------------------------------------------
    nuevas_lineas = []
    for i, l in enumerate(viejas):
        if i not in quitar:
            nuevas_lineas.append(l)
        nuevas_lineas += agregar.get(i, [])
    nuevas_lineas += al_final
    agregadas = {id(l) for ls in agregar.values() for l in ls} | {id(l) for l in al_final}
    resto_nuevo = [l for l in nuevas_lineas if id(l) not in agregadas]
    resto_viejo = [l for i, l in enumerate(viejas) if i not in quitar]
    if resto_nuevo != resto_viejo:
        raise SystemExit("ERROR: cambió alguna fila que no es parte de la corrección")
    h_resto = hashlib.sha256("".join(resto_viejo).encode("utf-8")).hexdigest()
    salida_txt = encabezado + "\n" + "".join(nuevas_lineas)
    h_salida = hashlib.sha256(salida_txt.encode("utf-8")).hexdigest()

    # --- conciliación con los resúmenes oficiales ----------------------------------------------
    def sumas(lineas):
        s = defaultdict(Counter)
        for l in lineas:
            f = fila_dict(l)
            if f["jurisdiccion"] == JURIS:
                s[(int(f["anio"]), f["tipo_de_medio"])][int(f["fecha"][5:7])] += Decimal(f["monto"])
        return s
    s_antes, s_despues = sumas(viejas), sumas(nuevas_lineas)
    tocados = {(int(fila_dict(l)["anio"]), fila_dict(l)["tipo_de_medio"])
               for l in [viejas[i] for i in quitar] + [l for ls in agregar.values() for l in ls] + al_final}
    conc = []
    for anio, n in sorted(RESUMEN_TIPO.items()):
        path, man = crudo(a.crudos, manifest, n)
        usados.append((f"resumen {anio}", path, man))
        for tipo, valores in sorted(leer_resumen_tipo(path).items()):
            if (anio, tipo) not in tocados and not (anio == 2013 and tipo == "Gráfica"):
                continue
            ant, des = sum(s_antes[(anio, tipo)].values()), sum(s_despues[(anio, tipo)].values())
            meses = [m for m in range(1, 13) if s_despues[(anio, tipo)][m] != valores[m - 1]]
            conc.append([anio, tipo, f"{ant:.2f}", f"{des:.2f}", f"{valores[12]:.2f}",
                         f"{des - valores[12]:.2f}",
                         "; ".join(f"{NOMBRES_MES[m - 1]} {s_despues[(anio, tipo)][m] - valores[m - 1]:+.2f}"
                                   for m in meses), man["archivo"]])
    for anio, n in sorted(RESUMEN_MES.items()):
        if not any(t[0] == anio for t in tocados):
            continue
        path, man = crudo(a.crudos, manifest, n)
        usados.append((f"resumen {anio}", path, man))
        valores = leer_resumen_mes(path)
        ant = sum(sum(c.values()) for (an, _), c in s_antes.items() if an == anio)
        mes_des = Counter()
        for (an, _), c in s_despues.items():
            if an == anio:
                mes_des.update(c)
        des = sum(mes_des.values())
        meses = [m for m in range(1, 13) if mes_des[m] != valores[m - 1]]
        conc.append([anio, "todos (el resumen no separa por tipo)", f"{ant:.2f}", f"{des:.2f}",
                     f"{valores[12]:.2f}", f"{des - valores[12]:.2f}",
                     "; ".join(f"{NOMBRES_MES[m - 1]} {mes_des[m] - valores[m - 1]:+.2f}" for m in meses),
                     man["archivo"]])

    # --- salida --------------------------------------------------------------------------------
    print(f"Entrada: {len(viejas)} filas, SHA-256 {ENTRADA_SHA256}")
    print(f"Correcciones: {', '.join(c for c in CORRECCIONES if c in aplicar)}")
    print(f"Las {len(resto_viejo)} filas que quedan de la entrada siguen idénticas byte a byte y en "
          f"el mismo orden (SHA-256 {h_resto})")
    print(f"Salida: {len(nuevas_lineas)} filas, SHA-256 {h_salida}\n")
    print(f"{'archivo_origen':46s} {'filas':>13s} {'total antes':>16s} {'total después':>16s} {'total PDF':>16s}")
    for r in informe:
        pdf_txt = "" if r["total_pdf"] is None else f"{r['total_pdf']:,.2f}"
        print(f"{r['archivo_origen'][:46]:46s} {r['filas_antes']:>5d} → {r['filas_despues']:>5d} "
              f"{r['total_antes']:>16,.2f} {r['total_despues']:>16,.2f} {pdf_txt:>16s}")
        print(f"{'':46s} {r['nota']}")
    print(f"\n{'año':4s} {'tipo':38s} {'antes':>16s} {'después':>16s} {'resumen oficial':>16s} {'dif':>10s}")
    for c in conc:
        print(f"{c[0]:<4d} {c[1]:38s} {Decimal(c[2]):>16,.2f} {Decimal(c[3]):>16,.2f} "
              f"{Decimal(c[4]):>16,.2f} {Decimal(c[5]):>10,.2f}" + (f"\n{'':4s} meses: {c[6]}" if c[6] else ""))

    if a.informe:
        carpeta = Path(a.informe)
        carpeta.mkdir(parents=True, exist_ok=True)
        _tsv(carpeta / "conciliacion.tsv",
             [["correccion", "archivo_origen", "filas_antes", "filas_despues", "total_antes",
               "total_despues", "total_pdf_celdas", "total_impreso_pdf", "nota"]]
             + [[r["correccion"], r["archivo_origen"], r["filas_antes"], r["filas_despues"],
                 f"{r['total_antes']:.2f}", f"{r['total_despues']:.2f}",
                 "" if r["total_pdf"] is None else f"{r['total_pdf']:.2f}",
                 f"{r['total_impreso']:.2f}" if r.get("total_impreso") is not None else "",
                 r["nota"]] for r in informe])
        _tsv(carpeta / "conciliacion_resumen_oficial.tsv",
             [["anio", "tipo_de_medio", "total_antes", "total_despues", "total_resumen_oficial",
               "diferencia", "meses_con_diferencia", "resumen_oficial"]] + conc)
        _tsv(carpeta / "medios_por_renglon.tsv",
             [["archivo_origen", "pagina", "medio_pdf", "localidad_pdf", "medio_ya_en_base",
               "medio_nuevo", "celdas_agregadas", "total_renglon"]] + emparejados)
        vistos = set()
        _tsv(carpeta / "manifest_crudos.tsv",
             [["uso", "crudo", "url", "bytes", "sha256", "last_modified", "descargado_utc", "manifest"]]
             + [[uso, p.name, m["url"], m["bytes"], m["sha256"], m["last_modified"], m["descargado_utc"],
                 f"n={m['n']}"] for uso, p, m in usados
                if not (m["n"] in vistos or vistos.add(m["n"]))])
        with open(carpeta / "verificacion.txt", "w", encoding="utf-8", newline="\n") as f:
            f.write(f"entrada: {len(viejas)} filas, SHA-256 {ENTRADA_SHA256}\n")
            f.write(f"correcciones: {', '.join(c for c in CORRECCIONES if c in aplicar)}\n")
            f.write(f"salida: {len(nuevas_lineas)} filas, SHA-256 {h_salida}\n")
            f.write(f"filas que salen: {len(quitar)}; filas que entran: {len(agregadas)}\n")
            f.write(f"las {len(resto_viejo)} filas que quedan de la entrada siguen idénticas byte a byte "
                    f"y en el mismo orden; SHA-256 {h_resto}\n")
    if a.salida:
        Path(a.salida).write_bytes(salida_txt.encode("utf-8"))
        print(f"\nEscrito {a.salida}")


if __name__ == "__main__":
    main()
