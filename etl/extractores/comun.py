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
DIR_PBA_NUEVOS = CRUDOS_BASE / "PBA Nuevos datos sin curar"
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

    def ok(self, n=1):
        self.extraidas += n

    def descartar(self, motivo, n=1):
        self.descartes[motivo] = self.descartes.get(motivo, 0) + n

    def resumen(self):
        partes = [f"{self.etiqueta}: {self.extraidas} filas extraidas"]
        if self.descartes:
            det = ", ".join(f"{k}={v}" for k, v in sorted(self.descartes.items()))
            partes.append(f"descartadas: {det}")
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

def normalizar_monto(raw):
    """Convierte un monto en string a float positivo, o None.

    Soporta:
      - europeo:  "1.210,00"  -> 1210.0
      - americano:"$ 28,991.36" -> 28991.36 ; "$ 300,000" -> 300000.0
      - limpio:   "10000.0" -> 10000.0
      - con $/espacios/comillas: " $  300,000 " -> 300000.0
      - parentesis o signo - => valor absoluto (los montos van siempre positivos)
    Devuelve None si vale 0, esta vacio o no parsea.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # parentesis contable => negativo
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    # quedarse solo con digitos , . -
    s = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
    s = s.replace("-", "")  # signo se ignora (siempre positivo)
    if not s:
        return None

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
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
    """Extrae el primer anio de 4 digitos (2003-2025) de un string."""
    for m in re.findall(r"(20[0-2]\d)", str(texto)):
        a = int(m)
        if 2003 <= a <= 2025:
            return a
    return None
