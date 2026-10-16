# -*- coding: utf-8 -*-
"""
comun.py  —  Helpers compartidos por los extractores de pauta oficial.

Centraliza:
  - Rutas a los datos crudos (configurables por env var DATOS_CRUDOS_BASE)
  - Normalizacion de montos (formato europeo / americano / limpio)
  - Normalizacion de fechas (ISO, M/D/YYYY, "Julio", "may-09")
  - Limpieza de strings ("" -> None, sacar comillas)
  - Lectura robusta de CSV (deteccion de encoding y separador)
  - Esquema canonico del registro de salida

El esquema de salida (9 columnas):
    jurisdiccion, anio, fecha, proveedor, medio, tipo_de_medio,
    monto, resolucion, archivo_origen
"""

import csv
import io
import os
import re
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
# Raiz del repo = dos niveles arriba de este archivo (etl/extractores/comun.py)
REPO_ROOT = Path(__file__).resolve().parents[2]

# Base de los datos crudos. Por defecto la ruta Windows del proyecto; se puede
# sobre-escribir con la variable de entorno DATOS_CRUDOS_BASE (util para testear
# en otro sistema).
_DEFAULT_CRUDOS_BASE = r"C:\Users\IvanGomezD\Desktop\0\ClaudeCoWork\DatosPautaOficial"
CRUDOS_BASE = Path(os.environ.get("DATOS_CRUDOS_BASE", _DEFAULT_CRUDOS_BASE))

DATOS_CRUDOS = CRUDOS_BASE / "Datos crudos Pauta Oficial"
DIR_CABA = DATOS_CRUDOS / "CABA"
DIR_NACION = DATOS_CRUDOS / "Nacion"
DIR_PBA = DATOS_CRUDOS / "PBA"
DIR_SANTA_FE = DATOS_CRUDOS / "Santa Fe"
DIR_PBA_NUEVOS = DATOS_CRUDOS / "PBA Nuevos datos sin curar"
DIR_CURADO = CRUDOS_BASE / "Datos_Pauta_Oficial_Curado"

# Salida
DATA_DIR = REPO_ROOT / "etl" / "data"
OUTPUT_CSV = DATA_DIR / "pauta_oficial_unificado_v2.csv"

# Esquema canonico
COLUMNS = [
    "jurisdiccion",
    "anio",
    "fecha",
    "proveedor",
    "medio",
    "tipo_de_medio",
    "monto",
    "resolucion",
    "archivo_origen",
]

JURISDICCIONES_VALIDAS = {"CABA", "Nación", "PBA", "Santa Fe"}

# Rango de años aceptado por el pipeline. El techo es dinámico (año actual +1)
# para que cargar datos de un año nuevo no los descarte silenciosamente como
# "fuera de rango"; el piso 2003 filtra basura de parseo (fechas rotas, etc.).
ANIO_MIN = 2003
ANIO_MAX = date.today().year + 1

# ---------------------------------------------------------------------------
# Logging simple a stderr (no contamina el stdout que pueda capturarse)
# ---------------------------------------------------------------------------

def log(msg):
    print(msg, file=sys.stderr, flush=True)


class Contador:
    """Acumulador de motivos de descarte para reportes por funcion."""

    def __init__(self, etiqueta):
        self.etiqueta = etiqueta
        self.extraidas = 0
        self.descartes = {}
        self.avisos = {}

    def ok(self, n=1):
        self.extraidas += n

    def descartar(self, motivo, n=1):
        self.descartes[motivo] = self.descartes.get(motivo, 0) + n

    def avisar(self, motivo, n=1):
        """Filas que se cargan pero con algo para revisar (no son descartes)."""
        self.avisos[motivo] = self.avisos.get(motivo, 0) + n

    def resumen(self):
        partes = [f"{self.etiqueta}: {self.extraidas} filas extraidas"]
        if self.descartes:
            det = ", ".join(f"{k}={v}" for k, v in sorted(self.descartes.items()))
            partes.append(f"descartadas: {det}")
        if self.avisos:
            det = ", ".join(f"{k}={v}" for k, v in sorted(self.avisos.items()))
            partes.append(f"avisos: {det}")
        log("  " + " | ".join(partes))


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------

def limpiar_str(s):
    """strip, saca comillas envolventes, '' / 'nan' / '-' -> None."""
    if s is None:
        return None
    s = str(s).replace(" ", " ").strip()
    # sacar comillas envolventes repetidas
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ("\"", "'"):
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "-", "s/d", "n/a",
                                 "(en blanco)", "en blanco", "(vacío)", "(vacio)",
                                 "sin datos", "s/n", "varios"):
        return None
    return s


# ---------------------------------------------------------------------------
# Montos
# ---------------------------------------------------------------------------

def _solo_numero(raw):
    """Deja solo digitos y separadores ("$ (1.210,00)" -> "1.210,00"). '' si no queda nada."""
    if raw is None:
        return ""
    s = str(raw).strip()
    # parentesis contable => negativo
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    # signo se ignora (siempre positivo)
    return "".join(ch for ch in s if ch.isdigit() or ch in ".,")


def _voto_decimal(s):
    """Separador decimal que delata una celda por si sola, o None si es ambigua.

    "1.234,56" / "1,234.56": el de la derecha es el decimal. "1.234.567": el repetido es de
    miles. "392120.34" / "6036629,5" / "1234.5678": un solo separador seguido de 1-2 o de 4+
    digitos es el decimal. "1160879.808", "4.500" o "48000" no votan: un separador seguido de
    exactamente 3 digitos puede ser de miles o decimal."""
    if "." in s and "," in s:
        return "," if s.rfind(",") > s.rfind(".") else "."
    for sep, otro in ((".", ","), (",", ".")):
        if sep in s:
            if s.count(sep) > 1:
                return otro
            return None if len(s.split(sep)[1]) == 3 else sep
    return None


def votos_decimal(valores):
    """Cuenta cuantas celdas de una columna delatan cada separador decimal."""
    votos = {",": 0, ".": 0}
    for raw in valores:
        v = _voto_decimal(_solo_numero(raw))
        if v:
            votos[v] += 1
    return votos


# Votos minimos para decidir el separador de una columna: una celda mal tipeada sola no
# alcanza para reinterpretar todas las celdas ambiguas.
MIN_VOTOS_DECIMAL = 2


def detectar_decimal(valores):
    """Separador decimal ("," o ".") de una columna de montos, o None si no se puede decidir.

    Decide solo con las celdas sin ambiguedad (ver _voto_decimal): al menos MIN_VOTOS_DECIMAL
    a favor y ninguna en contra. Si la columna se contradice o no tiene celdas que decidan,
    devuelve None y normalizar_monto aplica la regla celda por celda."""
    votos = votos_decimal(valores)
    for sep, otro in ((".", ","), (",", ".")):
        if votos[sep] >= MIN_VOTOS_DECIMAL and votos[otro] == 0:
            return sep
    return None


def parser_montos(valores, origen):
    """Decide el separador decimal de una columna y devuelve la funcion raw -> monto.

    Informa por log la decision cuando cambia la lectura de alguna celda respecto de la regla
    celda por celda, y avisa si la columna se contradice (ahi se usa la regla por celda)."""
    valores = list(valores)
    votos = votos_decimal(valores)
    dec = detectar_decimal(valores)
    if dec:
        cambian = sum(1 for v in valores if normalizar_monto(v, dec) != normalizar_monto(v))
        if cambian:
            log(f"  {origen}: separador decimal '{dec}' ({votos[dec]} celdas lo indican); "
                f"{cambian} celdas ambiguas se leen como decimales")
    elif votos[","] and votos["."]:
        log(f"  {origen}: ADVERTENCIA separador decimal contradictorio ({votos[',']} celdas "
            f"con ',' y {votos['.']} con '.'); se usa la regla celda por celda")
    return lambda raw: normalizar_monto(raw, dec)


def normalizar_monto(raw, decimal=None):
    """Convierte un monto en string a float positivo, o None.

    decimal: separador decimal de la columna ("," o "."), decidido con detectar_decimal.
    Con el separador conocido se parsea sin ambiguedad:
      - decimal=".": "1160879.808" -> 1160879.808 ; "1,234.5" -> 1234.5
      - decimal=",": "4.500" -> 4500.0 ; "1151594,994" -> 1151594.994
    Sin el separador (None) se decide celda por celda:
      - europeo:  "1.210,00"  -> 1210.0
      - americano:"$ 28,991.36" -> 28991.36 ; "$ 300,000" -> 300000.0
      - limpio:   "10000.0" -> 10000.0
      - con $/espacios/comillas: " $  300,000 " -> 300000.0
      - un solo separador + 3 digitos se toma como miles: "4.500" -> 4500.0 (por eso
        conviene pasar `decimal`: en una columna con punto decimal, "1160879.808" es decimal)
      - parentesis o signo - => valor absoluto (los montos van siempre positivos)
    Devuelve None si vale 0, esta vacio o no parsea.
    """
    s = _solo_numero(raw)
    if not s:
        return None

    has_dot = "." in s
    has_comma = "," in s

    if decimal in (",", "."):
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif has_dot and has_comma:
        # el separador mas a la derecha es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # europeo
        else:
            s = s.replace(",", "")                      # americano
    elif has_comma:
        partes = s.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2):
            s = s.replace(",", ".")   # coma decimal: "1210,50"
        else:
            s = s.replace(",", "")    # coma de miles: "300,000"
    elif has_dot:
        partes = s.split(".")
        if len(partes) == 2 and len(partes[1]) == 3:
            s = s.replace(".", "")    # ambiguo "4.500" -> miles -> 4500
        elif s.count(".") > 1:
            s = s.replace(".", "")    # multi punto = miles "1.234.567"
        # si no, punto decimal normal ("10000.0", "1.5")

    try:
        v = float(s)
    except ValueError:
        return None
    if v == 0:
        return None
    return abs(v)


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    # abreviaturas es/en (3 letras)
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}


def _iso(y, mo, d):
    if not (2000 <= y <= 2030):
        return None
    if not (1 <= mo <= 12):
        return None
    if not (1 <= d <= 31):
        d = 1
    return f"{y:04d}-{mo:02d}-{d:02d}"


def normalizar_fecha(raw, anio_default=None):
    """Devuelve fecha ISO (YYYY-MM-DD) o None. Nunca formato parcial."""
    if raw is None:
        return None
    s = str(raw).strip().strip("\"").strip()
    if not s:
        return None
    sl = s.lower()

    # ISO YYYY-MM-DD (con o sin hora)
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # M/D/YYYY (CABA usa formato americano: "1/15/2021") o D/M/YYYY
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 50 else 1900
        mo, d = a, b           # asumimos M/D/Y
        if mo > 12 and d <= 12:  # imposible como mes -> era D/M/Y
            mo, d = b, a
        return _iso(y, mo, d)

    # YYYY/MM/DD
    m = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # "may-09" / "mayo-2009" / "may/09"
    m = re.match(r"^([a-záéíóú]+)[\-/ ](\d{2,4})$", sl)
    if m:
        mo = MESES.get(m.group(1)) or MESES.get(m.group(1)[:3])
        if mo:
            y = int(m.group(2))
            if y < 100:
                y += 2000 if y < 50 else 1900
            return _iso(y, mo, 1)

    # nombre de mes solo: "Julio" (usa anio_default)
    mo = MESES.get(sl) or MESES.get(sl[:3])
    if mo and anio_default:
        try:
            return _iso(int(anio_default), mo, 1)
        except (TypeError, ValueError):
            return None

    return None


# ---------------------------------------------------------------------------
# Lectura de CSV robusta
# ---------------------------------------------------------------------------

def leer_texto(path):
    """Lee un archivo de texto probando varios encodings. Devuelve (texto, enc)."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return f.read(), enc
        except UnicodeDecodeError:
            continue
    with open(path, encoding="latin-1", errors="replace", newline="") as f:
        return f.read(), "latin-1"


def detectar_sep(path):
    """Detecta ';' vs ',' mirando la primera linea no vacia."""
    txt, _ = leer_texto(path)
    for linea in txt.splitlines():
        if linea.strip():
            return ";" if linea.count(";") > linea.count(",") else ","
    return ","


def leer_filas(path, sep=None):
    """Devuelve lista de filas (cada fila = lista de celdas) de un CSV."""
    if sep is None:
        sep = detectar_sep(path)
    txt, _ = leer_texto(path)
    return list(csv.reader(io.StringIO(txt), delimiter=sep))


def leer_dicts(path, sep=None):
    """Devuelve lista de dicts usando la primera fila como header."""
    if sep is None:
        sep = detectar_sep(path)
    txt, _ = leer_texto(path)
    return list(csv.DictReader(io.StringIO(txt), delimiter=sep))


# ---------------------------------------------------------------------------
# Lectura de XLSX (solo libreria estandar)
# ---------------------------------------------------------------------------

_NS_XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# formatos de fecha predefinidos de Excel (ECMA-376, 18.8.30)
_FMT_FECHA = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


def _es_formato_fecha(codigo):
    """True si un formato numerico propio (p.ej. 'yyyy\\-mm\\-dd;@') muestra una fecha."""
    sin_literales = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.|_.', "", codigo.split(";")[0])
    return bool(re.search(r"[dmy]", sin_literales, re.I))


def _texto_xlsx(si):
    """Texto visible de un <si> o <is>: un <t> directo o los <t> de cada tramo <r> (sin las
    guias foneticas <rPh>)."""
    partes = si.findall(f"{_NS_XLSX}t") + [t for r in si.findall(f"{_NS_XLSX}r")
                                           for t in r.findall(f"{_NS_XLSX}t")]
    return "".join(t.text or "" for t in partes)


def _columna_xlsx(ref):
    """'C12' -> 2 (columnas desde 0)."""
    col = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        col = col * 26 + ord(ch) - 64
    return col - 1


def leer_xlsx(path):
    """Devuelve las filas de la primera hoja de un XLSX (lista de celdas, como leer_filas).

    Las celdas de texto quedan como str; las numericas como float (el valor guardado, sin el
    formato de pantalla), salvo las que tienen formato de fecha, que quedan como date. Las
    celdas vacias son None y se saltean las filas sin ningun valor."""
    import xml.etree.ElementTree as ET
    import zipfile
    from datetime import timedelta

    with zipfile.ZipFile(path) as z:
        nombres = set(z.namelist())
        libro = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        hoja = libro.find(f"{_NS_XLSX}sheets/{_NS_XLSX}sheet")
        destino = next(r.get("Target") for r in rels if r.get("Id") == hoja.get(_NS_REL_ID))
        destino = destino[1:] if destino.startswith("/") else "xl/" + destino
        textos = []
        if "xl/sharedStrings.xml" in nombres:
            textos = [_texto_xlsx(si) for si in
                      ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS_XLSX}si")]
        estilo_fecha = []
        if "xl/styles.xml" in nombres:
            estilos = ET.fromstring(z.read("xl/styles.xml"))
            propios = {int(f.get("numFmtId")): f.get("formatCode")
                       for f in estilos.iter(f"{_NS_XLSX}numFmt")}
            xfs = estilos.find(f"{_NS_XLSX}cellXfs")
            for xf in (xfs if xfs is not None else []):
                fmt = int(xf.get("numFmtId", 0))
                estilo_fecha.append(fmt in _FMT_FECHA
                                    or (fmt in propios and _es_formato_fecha(propios[fmt])))
        pr = libro.find(f"{_NS_XLSX}workbookPr")
        base = (date(1904, 1, 1) if pr is not None and pr.get("date1904") in ("1", "true")
                else date(1899, 12, 30))
        datos = ET.fromstring(z.read(destino))

    filas = []
    for row in datos.iter(f"{_NS_XLSX}row"):
        celdas, col = {}, -1
        for c in row.findall(f"{_NS_XLSX}c"):
            col = _columna_xlsx(c.get("r")) if c.get("r") else col + 1
            t, v = c.get("t"), c.find(f"{_NS_XLSX}v")
            if t == "inlineStr":
                celdas[col] = _texto_xlsx(c.find(f"{_NS_XLSX}is"))
            elif v is None or v.text is None:
                continue
            elif t == "s":
                celdas[col] = textos[int(v.text)]
            elif t in ("str", "e", "d"):
                celdas[col] = v.text
            elif t == "b":
                celdas[col] = "VERDADERO" if v.text == "1" else "FALSO"
            else:
                valor = float(v.text)
                s = int(c.get("s", 0))
                if s < len(estilo_fecha) and estilo_fecha[s]:
                    valor = base + timedelta(days=int(valor))
                celdas[col] = valor
        if celdas:
            filas.append([celdas.get(i) for i in range(max(celdas) + 1)])
    return filas


# ---------------------------------------------------------------------------
# Registro canonico
# ---------------------------------------------------------------------------

def registro(jurisdiccion, anio, monto, archivo_origen,
             fecha=None, proveedor=None, medio=None,
             tipo_de_medio=None, resolucion=None):
    """Crea un dict con el esquema canonico (campos limpios)."""
    try:
        anio_i = int(anio)
    except (TypeError, ValueError):
        anio_i = None
    return {
        "jurisdiccion": jurisdiccion,
        "anio": anio_i,
        "fecha": fecha if fecha else None,
        "proveedor": limpiar_str(proveedor),
        "medio": limpiar_str(medio),
        "tipo_de_medio": limpiar_str(tipo_de_medio),
        "monto": monto,
        "resolucion": limpiar_str(resolucion),
        "archivo_origen": archivo_origen,
    }


def anio_de_texto(texto):
    """Extrae el primer anio de 4 digitos dentro del rango valido de un string."""
    for m in re.findall(r"(20\d\d)", str(texto)):
        a = int(m)
        if ANIO_MIN <= a <= ANIO_MAX:
            return a
    return None
