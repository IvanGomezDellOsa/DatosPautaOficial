# -*- coding: utf-8 -*-
"""
agregar_ilegibles.py  —  PBA, etapa 3 (16/10/2026): carga los 3 anexos cuya fuente no trae texto.

257/2022 (septiembre 2022), 138/2023 (marzo 2023) y 142/2023 (abril 2023): el PDF se ve bien,
pero la fuente embebida no dice qué letra es cada glifo (pdfplumber devuelve "\\x00").

Cómo se leen, sin OCR:
  - Cada glifo es un dibujo de la fuente TrueType embebida. Su firma es el SHA-1 de sus contornos
    y su ancho de avance: el mismo carácter de la misma fuente tiene siempre el mismo dibujo.
  - Las firmas se rotulan con los anexos de PBA que sí traen texto y concilian al centavo
    (anexos.tsv, concilia = si, promulgados en 2022-2023), más las letras que sí tienen texto en
    los propios 3 anexos. Se exige que ninguna firma tenga dos rótulos y que todos los glifos sin
    texto de los 3 anexos tengan rótulo.
  - Con el texto repuesto se corre el mismo lector (leer_anexos.leer_pdf) y la misma conciliación
    que en la etapa 1: la suma de las órdenes tiene que dar el total impreso al pie del anexo.

Antes de agregar se controla que las órdenes no estén ya en la base: ningún bloque de PBA de la
base comparte más de la mitad de las órdenes (monto, proveedor y medio) con un anexo.

El mes sale del resumen oficial de cada resolución (pba_resoluciones_normas_gba.tsv). Las filas
van al final del bloque de PBA, con el mismo formato que agregar.py.

Uso (desde la raíz del repo):
  python etl/actualizacion_2026-10-15_pba/agregar_ilegibles.py ENTRADA.csv CRUDOS [--salida CSV]
CRUDOS es crudos_2026-10-14 de la auditoría de fuentes (ver AGENTS.md). Requiere fontTools.
Sin --salida solo verifica e informa.
"""

import argparse
import csv
import hashlib
import io
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pdfplumber
from fontTools.ttLib import TTFont
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parents[0] / "actualizacion_2026-10-15"))
import leer_anexos  # noqa: E402
import regenerar  # noqa: E402,F401  (agrega etl/ y etl/extractores al path)
from regenerar import a_lineas, comun, fila_dict, posprocesar, sha256  # noqa: E402

ENTRADA_SHA256 = "585d1b80fd8a6dd06c1eeefcb4629d095fec1fb40b08801f07af6ea9ea816df6"  # con Gráfica 2013 de Santa Fe
ANEXOS = {  # anexo -> resolución
    "yBo8ORVz.pdf": "257/2022",
    "30PEDyxP.pdf": "138/2023",
    "dV9KZYxO.pdf": "142/2023",
}


# --- glifos -------------------------------------------------------------------------------

def fuentes(path):
    """{BaseFont: TTFont} de las fuentes Type0 con FontFile2 y CIDToGIDMap Identity."""
    doc = PDFDocument(PDFParser(open(path, "rb")))
    res = {}
    for pg in PDFPage.create_pages(doc):
        for _, v in resolve1(resolve1(pg.resources).get("Font", {})).items():
            v = resolve1(v)
            if "DescendantFonts" not in v or v["BaseFont"].name in res:
                continue
            d = resolve1(resolve1(v["DescendantFonts"])[0])
            fd = resolve1(d["FontDescriptor"])
            c2g = resolve1(d.get("CIDToGIDMap"))
            if "FontFile2" not in fd or (c2g is not None and getattr(c2g, "name", None) != "Identity"):
                continue
            res[v["BaseFont"].name] = TTFont(io.BytesIO(resolve1(fd["FontFile2"]).get_data()))
    return res


def firma(tt, gid):
    glyf = tt["glyf"]
    gn = tt.getGlyphOrder()[gid]
    coords, fin, flags = glyf[gn].getCoordinates(glyf)
    datos = (list(coords), list(fin), [f & 1 for f in flags], tt["hmtx"][gn][0])
    return hashlib.sha1(repr(datos).encode()).hexdigest()


class _Agregador(PDFPageAggregator):
    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        self.cur_item._objs[-1].cid = cid
        return adv


def caracteres(path):
    rm = PDFResourceManager()
    dev = _Agregador(rm, laparams=None)
    it = PDFPageInterpreter(rm, dev)
    out = defaultdict(list)
    with open(path, "rb") as f:
        for pn, page in enumerate(PDFPage.get_pages(f), 1):
            it.process_page(page)
            out[pn] = [(o.x0, o.fontname, o.cid, o.get_text()) for o in dev.get_result() if isinstance(o, LTChar)]
    return out


def rotular(paths):
    lib = defaultdict(Counter)
    for p in paths:
        ff = fuentes(p)
        for chars in caracteres(p).values():
            for _, fn, cid, t in chars:
                if fn in ff and t not in ("\x00", "") and not t.startswith("(cid"):
                    try:
                        lib[firma(ff[fn], cid)][t] += 1
                    except (IndexError, KeyError):
                        pass
    ambiguas = {k: v for k, v in lib.items() if len(v) > 1}
    if ambiguas:
        raise SystemExit(f"ERROR: {len(ambiguas)} firmas con dos rótulos: {list(ambiguas.values())[:3]}")
    return {k: next(iter(v)) for k, v in lib.items()}


def abrir_decodificado(lib, decodificados):
    original = pdfplumber.open

    def abrir(path, *a, **k):
        pdf = original(path, *a, **k)
        ff = fuentes(str(path))
        por_pag = caracteres(str(path))
        n = 0
        for pg in pdf.pages:
            pcs, mcs = pg.chars, por_pag[pg.page_number]
            if len(pcs) != len(mcs):
                raise SystemExit(f"ERROR {path}: p{pg.page_number} distinta cantidad de caracteres")
            for c, (x0, fn, cid, _) in zip(pcs, mcs):
                if abs(c["x0"] - x0) > 0.01 or c["fontname"] != fn:
                    raise SystemExit(f"ERROR {path}: p{pg.page_number} caracteres desalineados")
                if c["text"] == "\x00":
                    s = firma(ff[fn], cid)
                    if s not in lib:
                        raise SystemExit(f"ERROR {path}: glifo sin rótulo ({fn}, {cid})")
                    c["text"] = lib[s]
                    n += 1
        decodificados[Path(path).name] = n
        return pdf
    return abrir


# --- carga --------------------------------------------------------------------------------

def clave(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("crudos")
    ap.add_argument("--salida")
    a = ap.parse_args()
    if sha256(a.entrada) != ENTRADA_SHA256:
        raise SystemExit(f"ERROR: {a.entrada} no es el CSV esperado (SHA-256 {sha256(a.entrada)})")
    crudos = Path(a.crudos)
    manifest = {r["archivo"]: r for r in csv.DictReader(open(crudos / "manifest_descargas.tsv", encoding="utf-8"), delimiter="\t")
                if r["grupo"] == "D-PBA"}
    ruta = lambda an: crudos / manifest[an]["ruta"].replace("\\", "/")  # noqa: E731
    for an in ANEXOS:
        if sha256(ruta(an)) != manifest[an]["sha256"]:
            raise SystemExit(f"ERROR {an}: SHA-256 distinto del manifest")
    anexos = {r["anexo"]: r for r in csv.DictReader(open(AQUI / "anexos.tsv", encoding="utf-8"), delimiter="\t")}
    normas = {r["anexo_url"]: r for r in csv.DictReader(open(AQUI / "pba_resoluciones_normas_gba.tsv", encoding="utf-8"), delimiter="\t")}

    refs = [ruta(an) for an, r in anexos.items()
            if r["concilia"] == "si" and r["promulgacion"][-4:] in ("2022", "2023") and an in manifest]
    lib = rotular(refs + [ruta(an) for an in ANEXOS])
    print(f"firmas rotuladas: {len(lib)} (de {len(refs)} anexos legibles que concilian, 2022-2023)")

    decodificados = {}
    leer_anexos.pdfplumber.open = abrir_decodificado(lib, decodificados)

    base = defaultdict(Counter)
    for r in csv.DictReader(open(a.entrada, encoding="utf-8")):
        if r["jurisdiccion"] == "PBA":
            base[r["archivo_origen"]][(Decimal(r["monto"]), clave(r["proveedor"]), clave(r["medio"]))] += 1

    registros, informe = [], []
    for an, res in ANEXOS.items():
        x = anexos[an]
        if x["resolucion"] != res or x["tipo"] != "aprobacion" or x["duplicado_de"]:
            raise SystemExit(f"ERROR {an}: no es el anexo de aprobación de {res}")
        periodo, tipo = leer_anexos.periodo_y_tipo(normas[x["anexo_url"]])
        if tipo != "aprobacion" or len(periodo) != 7:
            raise SystemExit(f"ERROR {res}: sin mes en el resumen oficial")
        ordenes, totales, raras, expedientes, referencia = leer_anexos.leer_pdf(ruta(an))
        if raras:
            raise SystemExit(f"ERROR {an}: filas no reconocidas {raras[:3]}")
        ok, motivo = leer_anexos.conciliar(ordenes, totales)
        if not ok:
            raise SystemExit(f"ERROR {an}: {motivo}")
        suma = sum((o["monto"] for o in ordenes), Decimal(0))
        propias = Counter((o["monto"], clave(o["proveedor"]), clave(o["medio"])) for o in ordenes)
        archivo, comparten = max(((arch, sum((c & propias).values())) for arch, c in base.items()), key=lambda t: t[1])
        if comparten * 2 > len(ordenes):
            raise SystemExit(f"ERROR {res}: {archivo} ya tiene {comparten} de sus {len(ordenes)} órdenes")
        for o in ordenes:
            m = o["monto"]
            if "%.2f" % float(m) != f"{m:.2f}":
                raise SystemExit(f"ERROR {res}: el monto {m} no se puede escribir exacto")
            registros.append(comun.registro(
                "PBA", int(periodo[:4]), float(m), an, fecha=f"{periodo}-01",
                proveedor=o["proveedor"], medio=o["medio"], resolucion=x["resolucion_url"]))
        informe.append(dict(resolucion=res, anexo=an, periodo=periodo, expediente=" ".join(dict.fromkeys(expedientes)),
                            glifos_decodificados=decodificados[an], ordenes=len(ordenes), suma=f"{suma:.2f}",
                            total_impreso=" ".join(f"{t[2]:.2f}" for t in totales), conciliacion=motivo,
                            bloque_base_mas_parecido=f"{archivo} ({comparten} órdenes iguales)"))

    limpios, descartes = posprocesar(registros)
    if descartes or len(limpios) != len(registros):
        raise SystemExit(f"ERROR: el control de calidad de unificar.py descartaría filas: {descartes}")
    nuevas = a_lineas(limpios)
    with open(a.entrada, encoding="utf-8", newline="") as f:
        lineas = f.readlines()
    encabezado, datos = lineas[0], lineas[1:]
    ult_pba = max(i for i, l in enumerate(datos) if l.startswith("PBA,"))
    salida = [encabezado] + datos[:ult_pba + 1] + nuevas + datos[ult_pba + 1:]
    resto = salida[:ult_pba + 2] + salida[ult_pba + 2 + len(nuevas):]
    if resto != lineas:
        raise SystemExit("ERROR: cambió una fila que no debía cambiar")
    suma_nuevas = sum(Decimal(fila_dict(l)["monto"]) for l in nuevas)
    print(f"filas: {len(datos)} -> {len(salida) - 1} (+{len(nuevas)}); monto agregado {suma_nuevas:.2f}")
    print(f"primer id nuevo: {ult_pba + 2}; las filas de Santa Fe corren su id en {len(nuevas)}")
    for r in informe:
        print(r)
    with open(AQUI / "conciliacion_etapa3.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(informe[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(informe)
    if a.salida:
        txt = "".join(salida)
        with open(a.salida, "w", encoding="utf-8", newline="") as f:
            f.write(txt)
        print("escrito", a.salida, hashlib.sha256(txt.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
