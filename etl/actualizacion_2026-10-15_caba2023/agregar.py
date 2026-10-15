# -*- coding: utf-8 -*-
"""
agregar.py  —  CABA 2023: agrega Cine, Medios Gráficos y Medios Vecinales, publicados solo en XLSX.

Lee los 3 XLSX oficiales de BA Data con el ETL del repo (extract_caba._parse_pertype, el mismo
código que usa unificar.py), aplica lo mismo que unificar.py después de extraer y los inserta
donde los pone extract_caba.extraer(): en el bloque de la carpeta 2023, junto con los CSV, en el
orden de los nombres de archivo. Todo lo demás del CSV unificado queda idéntico byte a byte, y el
script lo verifica antes de escribir. Usa las mismas funciones que
etl/actualizacion_2026-10-15/regenerar.py.

Cada XLSX se busca por su número de fila en CRUDOS/manifest_descargas.tsv (con URL y SHA-256) y se
rechaza si su SHA-256 no coincide con el manifest y con extract_caba.XLSX_SIN_CSV. Un archivo que
no concilia al centavo con la suma de su columna de importe no se carga, y cada fila cargada se
compara con la misma fila del XLSX leída sin el ETL (fecha, medio y monto).

Uso (desde la raíz del repo; `-I` para no importar nada de la carpeta de crudos):
  python -I etl/actualizacion_2026-10-15_caba2023/agregar.py ENTRADA.csv CRUDOS
      [--salida etl/data/pauta_oficial_unificado_v2.csv] [--informe DIR]

ENTRADA.csv es el CSV unificado publicado antes (SHA-256 ENTRADA_SHA256;
`git show 485d51c:etl/data/pauta_oficial_unificado_v2.csv`). Sin --salida solo verifica e
informa. --informe escribe conciliacion.tsv, manifest_crudos.tsv y verificacion.txt.
"""

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "actualizacion_2026-10-15"))
import regenerar  # noqa: E402  (agrega etl/ y etl/extractores al path)
from regenerar import (  # noqa: E402
    a_lineas, centavos, clave, comun, fila_dict, leer_manifest, posprocesar, sha256, _tsv)
import extract_caba  # noqa: E402

ENTRADA_SHA256 = "edd5ea3ce9c1d02dc16ec06e91ec5cdf155f9f5d01a4a287ecff7fd23febf5ac"
JURIS, ANIO = "CABA", 2023

# (n del manifest, archivo). "BA DATA 2023 - Medios Vecinales.xlsx" (n=3) es el mismo archivo
# publicado antes (09/08/2024, idéntico byte a byte): no se carga, se verifica que sea igual.
ARCHIVOS = [
    (4, "BA_DATA_2023_Medios_Vecinales.xlsx"),
    (1, "pauta-publicitaria-cine-2023.xlsx"),
    (2, "pauta-publicitaria-medios-graficos-2023.xlsx"),
]
REPETIDO = (3, "BA DATA 2023 - Medios Vecinales.xlsx", 4)

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def crudo(carpeta, manifest, n, nombre):
    fila = manifest[n]
    path = Path(carpeta) / fila["ruta"].replace("\\", "/")
    if fila["archivo"] != nombre or path.name != nombre:
        raise SystemExit(f"ERROR: la fila {n} del manifest no es {nombre}")
    real = sha256(path)
    if real != fila["sha256"]:
        raise SystemExit(f"ERROR {path}: SHA-256 {real} distinto del manifest ({fila['sha256']})")
    return path, fila


def leer_hoja(path):
    """Filas del XLSX oficial leídas del XML de la hoja, sin el lector del ETL:
    [(número de fila, {columna: (tipo, valor guardado)})], tipo "texto" para los textos."""
    with zipfile.ZipFile(path) as z:
        hojas = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if hojas != ["xl/worksheets/sheet1.xml"]:
            raise SystemExit(f"ERROR {path.name}: se esperaba una sola hoja ({hojas})")
        textos = [("".join(t.text or "" for t in si.iter(_M + "t")))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_M + "si")]
        hoja = ET.fromstring(z.read(hojas[0]))
    filas = []
    for row in hoja.iter(_M + "row"):
        celdas = {}
        for c in row.findall(_M + "c"):
            v = c.find(_M + "v")
            if v is None:
                continue
            col = re.match(r"[A-Z]+", c.get("r")).group()
            celdas[col] = ("texto", textos[int(v.text)]) if c.get("t") == "s" else (c.get("t"), v.text)
        if celdas:
            filas.append((int(row.get("r")), celdas))
    return filas


def columna(filas, patron, path):
    _, encabezado = filas[0]
    cols = [k for k, (t, v) in encabezado.items() if t == "texto" and re.search(patron, v, re.I)]
    if len(cols) != 1:
        raise SystemExit(f"ERROR {path.name}: columna {patron} ambigua {encabezado}")
    return cols[0]


def total_xlsx_oficial(path):
    """Suma exacta (Decimal) de la columna de importe del XLSX oficial: el valor guardado de cada
    celda, no el que muestra Excel. La columna es la del encabezado (fila 1) que dice "importe"
    o "monto"; toda celda de esa columna debajo del encabezado tiene que ser numérica. Devuelve
    (centavos, filas, detalle): la suma redondeada al centavo una sola vez."""
    filas = leer_hoja(path)
    col = columna(filas, r"importe|monto", path)
    suma, n, raros = Decimal(0), 0, []
    for r, celdas in filas[1:]:
        t, v = celdas.get(col, (None, None))
        if t not in (None, "n") or v is None:
            raros.append((r, t, v))
            continue
        suma += Decimal(v)
        n += 1
    if raros:
        raise SystemExit(f"ERROR {path.name}: celdas de importe no numéricas: {raros[:5]}")
    return int((suma * 100).quantize(Decimal(1))), n, f"suma exacta {suma}"


def control_por_fila(path, lineas):
    """Compara cada fila cargada con la misma fila del XLSX leída sin el ETL: fecha (número de
    serie de Excel contado desde 1899-12-30), medio (con los espacios colapsados) y monto (el
    valor guardado, redondeado al centavo). Devuelve la cantidad de filas comparadas."""
    filas = leer_hoja(path)
    c_fecha, c_medio = columna(filas, r"^fecha$", path), columna(filas, r"^medio$", path)
    c_monto = columna(filas, r"importe|monto", path)
    if len(filas) - 1 != len(lineas):
        raise SystemExit(f"ERROR {path.name}: {len(filas) - 1} filas en el XLSX y {len(lineas)} cargadas")
    for (r, celdas), linea in zip(filas[1:], lineas):
        f = fila_dict(linea)
        serie = Decimal(celdas[c_fecha][1])
        esperado = {
            "fecha": (date(1899, 12, 30) + timedelta(days=int(serie))).isoformat(),
            "medio": " ".join(celdas[c_medio][1].split()),
            "monto": Decimal(celdas[c_monto][1]).quantize(Decimal("0.01")),
        }
        cargado = {"fecha": f["fecha"], "medio": f["medio"], "monto": Decimal(f["monto"])}
        if serie != int(serie) or esperado != cargado or f["proveedor"] or f["resolucion"]:
            raise SystemExit(f"ERROR {path.name} fila {r}: XLSX {esperado}, cargado {f}")
    return len(lineas)


def orden_extraer(nombres):
    """Orden de los archivos de una carpeta en extract_caba.extraer() (sorted de Path). En
    Windows, donde se generó el CSV, Path ordena sin distinguir mayúsculas; se exige que el
    orden sea el mismo en cualquier sistema."""
    win = sorted(nombres, key=PureWindowsPath)
    if win != sorted(nombres, key=PurePosixPath):
        raise SystemExit(f"ERROR: el orden de {nombres} depende del sistema")
    return win


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("crudos")
    ap.add_argument("--salida")
    ap.add_argument("--informe")
    a = ap.parse_args()

    if sha256(a.entrada) != ENTRADA_SHA256:
        raise SystemExit(f"ERROR: {a.entrada} no es el CSV revisado (SHA-256 {sha256(a.entrada)})")
    manifest = leer_manifest(a.crudos)
    n_rep, nombre_rep, n_igual = REPETIDO
    if (manifest[n_rep]["archivo"], manifest[n_rep]["sha256"]) != (nombre_rep, manifest[n_igual]["sha256"]):
        raise SystemExit(f"ERROR: {nombre_rep} no es idéntico a {manifest[n_igual]['archivo']}")
    crudo(a.crudos, manifest, n_rep, nombre_rep)

    texto = Path(a.entrada).read_bytes().decode("utf-8")
    encabezado, *viejas = texto.split("\n")
    if viejas[-1] != "":
        raise SystemExit("ERROR: el CSV no termina en salto de línea")
    viejas = [l + "\n" for l in viejas[:-1]]
    claves = [clave(l) for l in viejas]
    anios = [fila_dict(l)["anio"] for l in viejas]

    # bloque de la carpeta 2023 de CABA: contiguo, cada archivo contiguo y en el orden de extraer()
    en_2023 = [i for i, (k, an) in enumerate(zip(claves, anios)) if k[0] == JURIS and an == str(ANIO)]
    ini, fin = en_2023[0], en_2023[-1]
    if en_2023 != list(range(ini, fin + 1)):
        raise SystemExit("ERROR: CABA 2023 no es un bloque contiguo")
    existentes = list(dict.fromkeys(k[1] for k in claves[ini:fin + 1]))
    if any(k[0] == JURIS and k[1] in existentes for k in claves[:ini] + claves[fin + 1:]):
        raise SystemExit("ERROR: un archivo de CABA 2023 tiene filas fuera del bloque")
    if existentes != orden_extraer(existentes):
        raise SystemExit(f"ERROR: CABA 2023 no está en el orden de extraer(): {existentes}")
    tramos = 1 + sum(1 for i in range(ini + 1, fin + 1) if claves[i] != claves[i - 1])
    if tramos != len(existentes):
        raise SystemExit("ERROR: un archivo de CABA 2023 no es contiguo")

    nuevas_por_archivo, informe = {}, []
    for n, nombre in ARCHIVOS:
        if nombre in existentes or any(k == (JURIS, nombre) for k in claves):
            raise SystemExit(f"ERROR: {nombre} ya está en el CSV")
        path, man = crudo(a.crudos, manifest, n, nombre)
        if extract_caba.XLSX_SIN_CSV.get(nombre) != man["sha256"]:
            raise SystemExit(f"ERROR: {nombre} no es el XLSX revisado de extract_caba.XLSX_SIN_CSV")
        cont = comun.Contador(f"[agregar] {nombre}")
        crudos = extract_caba._parse_pertype(path, ANIO, cont)
        cont.resumen()
        regs, descartes = posprocesar(crudos)
        oficial, n_oficial, det = total_xlsx_oficial(path)
        if cont.descartes or descartes or len(regs) != n_oficial:
            raise SystemExit(f"ERROR {nombre}: el ETL descarta filas ({cont.descartes}, "
                             f"{dict(descartes)}; {len(regs)} de {n_oficial})")
        if any(r["jurisdiccion"] != JURIS or r["anio"] != ANIO or r["archivo_origen"] != nombre
               or not (r["fecha"] or "").startswith(f"{ANIO}-") for r in regs):
            raise SystemExit(f"ERROR {nombre}: registros con otra jurisdicción, año, fecha o archivo")
        lineas = a_lineas(regs)
        comparadas = control_por_fila(path, lineas)
        despues = sum(centavos(fila_dict(l)["monto"]) for l in lineas)
        if despues != oficial:
            raise SystemExit(f"ERROR {nombre}: no concilia ({despues / 100:,.2f} contra "
                             f"{oficial / 100:,.2f}); no se carga")
        nuevas_por_archivo[nombre] = lineas
        montos = [r["monto"] for r in regs]
        informe.append({
            "archivo_origen": nombre, "tipo_de_medio": regs[0]["tipo_de_medio"], "filas": len(lineas),
            "total": despues, "total_oficial": oficial, "diferencia": despues - oficial,
            "total_oficial_fuente": f"suma de la columna de importe del XLSX oficial ({n_oficial} "
                                    f"filas; {det})",
            "fechas": f"{min(r['fecha'] for r in regs)} a {max(r['fecha'] for r in regs)}",
            "montos": f"{min(montos):.2f} a {max(montos):.2f}",
            "repetidas": sum(c - 1 for c in Counter(lineas).values() if c > 1),
            "comparadas": comparadas,
            "crudo": path.name, "man": man, "manifest": f"n={n}",
        })

    # --- armado: el bloque 2023 en el orden de extraer(), con los archivos nuevos -------------
    orden = orden_extraer(existentes + list(nuevas_por_archivo))
    bloque = []
    for nombre in orden:
        bloque += nuevas_por_archivo.get(nombre) or [l for l, k in zip(viejas[ini:fin + 1], claves[ini:fin + 1])
                                                     if k[1] == nombre]
    nuevas = viejas[:ini] + bloque + viejas[fin + 1:]

    # --- verificación: lo que no es de los archivos nuevos queda idéntico ----------------------
    nuevos = {(JURIS, nombre) for nombre in nuevas_por_archivo}
    resto_nuevo = [l for l in nuevas if clave(l) not in nuevos]
    if resto_nuevo != viejas:
        raise SystemExit("ERROR: cambió alguna fila fuera de los archivos nuevos")
    h_resto = hashlib.sha256("".join(viejas).encode("utf-8")).hexdigest()
    for r in informe:
        ids = [i + 1 for i, l in enumerate(nuevas) if clave(l) == (JURIS, r["archivo_origen"])]
        if ids != list(range(ids[0], ids[-1] + 1)):
            raise SystemExit(f"ERROR: {r['archivo_origen']} no quedó contiguo")
        r["ids"] = f"{ids[0]}-{ids[-1]}"
    salida_txt = encabezado + "\n" + "".join(nuevas)
    h_salida = hashlib.sha256(salida_txt.encode("utf-8")).hexdigest()

    print(f"Entrada: {len(viejas)} filas, SHA-256 {ENTRADA_SHA256}")
    print(f"Las {len(viejas)} filas de la entrada siguen idénticas byte a byte y en el mismo orden "
          f"(SHA-256 {h_resto})")
    print(f"Salida: {len(nuevas)} filas, SHA-256 {h_salida}")
    print(f"Orden de la carpeta 2023: {', '.join(orden)}")
    print()
    print(f"{'archivo_origen':46s} {'filas':>6s} {'ids':>15s} {'total cargado':>18s} "
          f"{'total oficial':>18s} {'dif':>5s}")
    for r in informe:
        print(f"{r['archivo_origen']:46s} {r['filas']:>6d} {r['ids']:>15s} {r['total'] / 100:>18,.2f} "
              f"{r['total_oficial'] / 100:>18,.2f} {r['diferencia'] / 100:>5,.2f}")
        print(f"{'':46s} fechas {r['fechas']}; montos {r['montos']}; "
              f"{r['repetidas']} filas repetidas exactas, como en la fuente; "
              f"{r['comparadas']} filas iguales a la lectura independiente del XLSX")

    if a.informe:
        carpeta = Path(a.informe)
        carpeta.mkdir(parents=True, exist_ok=True)
        _tsv(carpeta / "conciliacion.tsv",
             [["archivo_origen", "tipo_de_medio", "filas", "ids", "total_cargado", "total_oficial",
               "diferencia", "total_oficial_fuente", "fechas", "montos", "filas_repetidas",
               "fuente", "sha256_fuente"]]
             + [[r["archivo_origen"], r["tipo_de_medio"], r["filas"], r["ids"],
                 f"{r['total'] / 100:.2f}", f"{r['total_oficial'] / 100:.2f}",
                 f"{r['diferencia'] / 100:.2f}", r["total_oficial_fuente"], r["fechas"], r["montos"],
                 r["repetidas"], r["man"]["url"], r["man"]["sha256"]] for r in informe])
        _tsv(carpeta / "manifest_crudos.tsv",
             [["archivo_origen", "crudo", "url", "bytes", "sha256", "last_modified",
               "descargado_utc", "manifest"]]
             + [[r["archivo_origen"], r["crudo"], r["man"]["url"], r["man"]["bytes"],
                 r["man"]["sha256"], r["man"]["last_modified"], r["man"]["descargado_utc"],
                 r["manifest"]] for r in informe])
        with open(carpeta / "verificacion.txt", "w", encoding="utf-8", newline="\n") as f:
            f.write(f"entrada: {len(viejas)} filas, SHA-256 {ENTRADA_SHA256}\n")
            f.write(f"salida: {len(nuevas)} filas, SHA-256 {h_salida}\n")
            f.write(f"las {len(viejas)} filas de la entrada siguen idénticas byte a byte y en el mismo "
                    f"orden; SHA-256 {h_resto}\n")
            f.write(f"orden de la carpeta 2023 (extract_caba.extraer): {', '.join(orden)}\n")
            f.write(f"{nombre_rep} (manifest n={n_rep}) es idéntico a "
                    f"{manifest[n_igual]['archivo']}: SHA-256 {manifest[n_rep]['sha256']}\n")
    if a.salida:
        Path(a.salida).write_bytes(salida_txt.encode("utf-8"))
        print(f"\nEscrito {a.salida}")


if __name__ == "__main__":
    main()
