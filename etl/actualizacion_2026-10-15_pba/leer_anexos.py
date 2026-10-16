# -*- coding: utf-8 -*-
"""
leer_anexos.py  —  PBA: lee las órdenes de publicidad de los anexos PDF oficiales (normas.gba.gob.ar).

No toca el CSV unificado: solo lee los PDF y escribe dos archivos en DIR_SALIDA:
  - ordenes_anexos.csv: una fila por orden (OP, proveedor, medio, monto) con su anexo,
    resolución, expediente y período;
  - anexos.tsv: una fila por anexo, con la suma de sus órdenes, el total impreso en el anexo y
    si concilian al centavo.

Lectura: las tablas del anexo tienen bordes dibujados, así que se leen con
pdfplumber.extract_tables() celda por celda (columnas por el encabezado OP / Proveedor / Medio /
Monto). Un texto que ocupa dos renglones dentro de la misma celda se une con un espacio. La fila
de total es la que trae solo un monto, sin OP, proveedor ni medio. Cualquier otra fila que no sea
encabezado, expediente u orden se informa como "no reconocida": el anexo que tenga una no concilia.

Cada PDF se busca en CRUDOS/manifest_descargas.tsv (grupo D-PBA) y se rechaza si su SHA-256 no
coincide. El período, el tipo (aprobación, rectificación o rescisión) y la resolución salen de
la lista de resoluciones de normas.gba.gob.ar (NORMAS.tsv).

Uso (desde la raíz del repo):
  python -I etl/actualizacion_2026-10-15_pba/leer_anexos.py CRUDOS NORMAS.tsv DIR_SALIDA [ANEXO,ANEXO...]
"""

import csv
import hashlib
import re
import sys
from decimal import Decimal
from pathlib import Path

import pdfplumber

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
         "diciembre": 12}
MONTO = re.compile(r"^\$?\s*(\d{1,3}(?:([.,])\d{3})*|\d+)([.,])(\d{2})$")
EXPEDIENTE = re.compile(r"Expediente\s*(?:N\s*[°ºo]?\.?)?\s*:?\s*([0-9]{4}\s*-\s*[0-9]+(?:\s*[-/]\s*[0-9]{4})?)", re.I)
OP = re.compile(r"^(?:MINCOMPUB-)?\d{1,6}(?:/\d{4})?$")
ROTULO_TOTAL = re.compile(r"(?i)^total( general)?\s*\$?\s*:?$")
TOTAL_EN_CELDA = re.compile(r"(?i)^total(?: general)?\s*:?\s*(\$\s*[\d.,]+)$")
TITULO = re.compile(r"(?i)^(aprobatoria de )?[óo]rdenes de publicidad|^anexo")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def texto(celda):
    # los caracteres de control (p. ej. NUL) salen de fuentes sin mapa Unicode: se marcan con
    # U+FFFD para que la fila no se reconozca como orden y el anexo no concilie
    t = re.sub(r"[\x00-\x08\x0b-\x1f]", "�", celda or "")
    return re.sub(r"\s+", " ", t.replace("\n", " ")).strip()


def renglones(celda):
    """Los renglones de una celda tal como los corta el PDF, separados por un salto de renglón
    (vacío si es uno solo). Sirven para decidir después si un corte partió una palabra."""
    partes = [texto(p) for p in (celda or "").split("\n") if texto(p)]
    return "\n".join(partes) if len(partes) > 1 else ""


def monto(celda):
    """'$ 1.234,56' o '$ 1,234.56' -> Decimal('1234.56'); None si la celda no es un monto con
    dos decimales. El separador decimal es el último; el de miles tiene que ser el otro."""
    # "$ 3 85.000,00": algunos PDF parten un número con caracteres pegados; los espacios entre
    # dígitos se quitan y el resultado igual tiene que respetar los grupos de miles
    t = re.sub(r"(?<=\d) (?=[\d.,])|(?<=[.,]) (?=\d)", "", texto(celda))
    # "- $ 6.057.744,00": el guion es el final del texto del medio, que se corrió de celda; el
    # signo lo controla la conciliación con el total impreso
    t = re.sub(r"^-\s*(?=\$)", "", t)
    m = MONTO.match(t.replace("$ ", "$"))
    if not m or (m.group(2) and m.group(2) == m.group(3)):
        return None
    return Decimal(re.sub(r"[.,]", "", m.group(1)) + "." + m.group(4))


def periodo_y_tipo(norma):
    resumen = norma["resumen"]
    tipo = ("rescision" if re.match(r"(?i)\s*rescin", resumen) else
            "rectificacion" if re.match(r"(?i)\s*rectific", resumen) else "aprobacion")
    m = re.search(r"mes(?:es)? de (\w+)\s+(?:de |del )?(?:a[ñn]o\W{0,3})?(\d{4})", resumen, re.I)
    periodo = ""
    if m and m.group(1).lower() in MESES:
        periodo = f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}"
    return periodo, tipo


def leer_pdf(path):
    """Devuelve (ordenes, totales, no_reconocidas, expedientes, referencia) del anexo."""
    ordenes, totales, raras, expedientes = [], [], [], []
    cols = None
    expediente = ""
    ultima_linea = ""  # último renglón de texto antes de la hoja de firmas
    referencia = ""    # "Referencia: ..." de la hoja de firmas (GEDO)
    with pdfplumber.open(path) as pdf:
        for npag, pagina in enumerate(pdf.pages, start=1):
            tablas = pagina.extract_tables()
            lineas = [l.strip() for l in (pagina.extract_text() or "").split(chr(10)) if l.strip()]
            if any("Hoja Adicional de Firmas" in l for l in lineas):
                referencia = next((l for l in lineas if l.startswith("Referencia:")), referencia)
            elif lineas:
                ultima_linea = lineas[-1]
            for tabla in tablas:
                for fila in tabla:
                    celdas = [texto(c) for c in fila]
                    linea = " | ".join(celdas)
                    if not any(celdas):
                        continue
                    me = EXPEDIENTE.search(linea)
                    if me and not any(monto(c) is not None for c in celdas):
                        expediente = re.sub(r"\s+", "", me.group(1))
                        expedientes.append(expediente)
                        continue
                    bajo = [c.lower() for c in celdas]
                    if any(re.search(r"proveedor|preveedor|provedor", c) for c in bajo) and any("medio" in c for c in bajo):
                        cols = {}
                        for i, c in enumerate(bajo):
                            if c in ("op", "op.", "o.p", "o.p.", "orden", "orden de publicidad", "n° op", "nº op") and "op" not in cols:
                                cols["op"] = i
                            elif re.search(r"proveedor|preveedor|provedor", c) and "proveedor" not in cols:
                                cols["proveedor"] = i
                            elif "medio" in c and "medio" not in cols:
                                cols["medio"] = i
                            elif ("monto" in c or "importe" in c or c.startswith("total")) and "monto" not in cols:
                                cols["monto"] = i
                        if set(cols) != {"op", "proveedor", "medio", "monto"} or len(celdas) != 4:
                            raras.append((npag, "encabezado:" + linea))
                            cols = None
                        continue
                    llenas = [c for c in celdas if c]
                    mt = TOTAL_EN_CELDA.match(llenas[0]) if len(llenas) == 1 else None
                    if mt:  # "Total: $ 1.021.658.286,00" en una sola celda
                        llenas = ["Total", mt.group(1)]
                    if len(llenas) == 1 and TITULO.search(llenas[0]) and monto(llenas[0]) is None:
                        continue  # título de la tabla
                    if llenas and ROTULO_TOTAL.match(llenas[0]):
                        llenas = llenas[1:]
                    elif len(llenas) > 1 and ROTULO_TOTAL.match(llenas[-2]):
                        llenas = llenas[:-2] + llenas[-1:]
                    if llenas and all(monto(c) is not None for c in llenas) and len(set(llenas)) == 1:
                        totales.append((npag, expediente, monto(llenas[0]), len(ordenes)))
                        continue  # fila de total (a veces el monto se repite en la primera celda)
                    if cols is None or len(celdas) != 4:
                        raras.append((npag, linea))
                        continue
                    op, prov, medio, imp = (celdas[cols[k]] for k in ("op", "proveedor", "medio", "monto"))
                    m = monto(imp)
                    if m is not None and OP.match(op) and (prov or medio):
                        ordenes.append({"pagina": npag, "expediente": expediente, "op": op,
                                        "proveedor": prov, "medio": medio, "monto": m,
                                        "proveedor_renglones": renglones(fila[cols["proveedor"]]),
                                        "medio_renglones": renglones(fila[cols["medio"]]),
                                        "continuacion": ""})
                    elif not op and not imp and (prov or medio) and ordenes:
                        # el texto de una celda que siguió en otra fila: va con la orden anterior
                        previa = ordenes[-1]
                        for campo, valor in (("proveedor", prov), ("medio", medio)):
                            if valor:
                                partes = (previa[campo + "_renglones"] or previa[campo]).split(chr(10))
                                previa[campo + "_renglones"] = chr(10).join([p for p in partes if p] + [valor])
                                previa[campo] = texto(previa[campo] + " " + valor)
                        previa["continuacion"] = "si"
                    else:
                        raras.append((npag, linea))
    # Algunos anexos imprimen el total debajo de la tabla, fuera de los bordes (a veces en una
    # página aparte). Se toma solo si es el último renglón antes de la hoja de firmas y no es el
    # monto de la única orden.
    if not totales and monto(ultima_linea) is not None and len(ordenes) > 1:
        totales.append((0, expediente, monto(ultima_linea), len(ordenes)))
    return ordenes, totales, raras, expedientes, referencia


def conciliar(ordenes, totales):
    """El anexo concilia si hay al menos un total impreso y:
    - el último total es la suma de todas las órdenes, y cada total anterior es la suma de las
      órdenes desde el total previo (subtotales por expediente), o
    - hay un total por tramo y la suma de los tramos es la de todas las órdenes."""
    if not totales:
        return False, "sin total impreso"
    suma = sum((o["monto"] for o in ordenes), Decimal(0))
    previo, tramos_ok, acum = 0, True, Decimal(0)
    for _, _, tot, hasta in totales:
        tramo = sum((o["monto"] for o in ordenes[previo:hasta]), Decimal(0))
        if tramo == tot:
            acum += tot
            previo = hasta
        elif tot == sum((o["monto"] for o in ordenes[:hasta]), Decimal(0)) and hasta == len(ordenes):
            return True, "total general = suma de órdenes"
        else:
            tramos_ok = False
    if tramos_ok and previo == len(ordenes) and acum == suma:
        return True, "un total por tramo" if len(totales) > 1 else "total = suma de órdenes"
    return False, f"suma {suma} distinta de los totales {[str(t[2]) for t in totales]}"


def main():
    crudos, normas_tsv, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    salida.mkdir(parents=True, exist_ok=True)
    normas = {}
    for r in csv.DictReader(open(normas_tsv, encoding="utf-8"), delimiter="\t"):
        if r["anexo_url"]:
            normas.setdefault(r["anexo_url"], r)
    manifest = [r for r in csv.DictReader(open(crudos / "manifest_descargas.tsv", encoding="utf-8"), delimiter="\t")
                if r["grupo"] == "D-PBA"]
    if len(sys.argv) > 4:  # prueba: solo algunos anexos
        solo = set(sys.argv[4].split(","))
        manifest = [r for r in manifest if r["archivo"] in solo]
    vistos = {}
    filas, resumen = [], []
    for r in manifest:
        path = crudos / r["ruta"].replace("\\", "/")
        real = sha256(path)
        if real != r["sha256"]:
            raise SystemExit(f"ERROR {path}: SHA-256 {real} distinto del manifest ({r['sha256']})")
        norma = normas[r["url"]]
        periodo, tipo = periodo_y_tipo(norma)
        m = re.search(r"/resolucion/(\d{4})/(\d+)/", norma["resolucion_url"])
        resolucion = f"{m.group(2)}/{m.group(1)}"
        try:
            ordenes, totales, raras, expedientes, referencia = leer_pdf(path)
            error = ""
        except Exception as e:  # PDF ilegible
            ordenes, totales, raras, expedientes, referencia, error = [], [], [], [], "", repr(e)
        ok, motivo = conciliar(ordenes, totales) if not raras else (False, f"{len(raras)} filas no reconocidas")
        if error:
            ok, motivo = False, "error: " + error
        dup = vistos.get(real, "")
        vistos.setdefault(real, r["archivo"])
        suma = sum((o["monto"] for o in ordenes), Decimal(0))
        resumen.append({
            "anexo": r["archivo"], "n_manifest": r["n"], "sha256": real, "resolucion": resolucion,
            "resolucion_url": norma["resolucion_url"], "promulgacion": norma["promulgacion"],
            "tipo": tipo, "periodo": periodo, "expedientes": " ".join(dict.fromkeys(expedientes)),
            "ordenes": len(ordenes), "suma_ordenes": f"{suma:.2f}",
            "totales_impresos": " ".join(f"{t[2]:.2f}" for t in totales),
            "concilia": "si" if ok else "no", "motivo": motivo, "duplicado_de": dup,
            "no_reconocidas": texto(" || ".join(f"p{p}: {l}" for p, l in raras[:5])).replace("	", " "),
            "anexo_url": r["url"], "anexo_nombre": norma["anexo_nombre"], "referencia": referencia,
        })
        for o in ordenes:
            filas.append({"anexo": r["archivo"], "resolucion": resolucion, "periodo": periodo, "tipo": tipo,
                          **{k: (f"{v:.2f}" if k == "monto" else v) for k, v in o.items()}})
        print(r["archivo"], resolucion, tipo, periodo, len(ordenes), motivo, flush=True)
    with open(salida / "ordenes_anexos.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    with open(salida / "anexos.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(resumen[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(resumen)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
