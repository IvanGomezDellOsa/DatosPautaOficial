# -*- coding: utf-8 -*-
"""
regenerar.py  —  Actualización de datos del 2026-10-15: reemplazo por archivo de origen.

Regenera con el ETL del repo (etl/extractores, el mismo código que usa unificar.py) solo las
filas de los `archivo_origen` afectados por errores confirmados, y agrega los archivos nuevos en
la posición en la que los pondría unificar.py. Todo lo demás del CSV unificado queda idéntico
byte a byte, y el script lo verifica antes de escribir.

Correcciones (se eligen con --aplicar, separadas por coma; por defecto, todas):
  caba_x1000          CABA 2016 y 2017: montos con punto decimal y 3 decimales leídos x1000.
  nacion_pivots_rubro Nación 2010-S1, 2010-S2 y 2012-S1: el "Total general" de cada fila del
                      pivot cargado como una orden más, y rubros corridos; se leen del PDF oficial.
  nacion_2009         Nación may-oct y nov-dic 2009: montos en el mes equivocado, celdas
                      perdidas y 12 filas de encabezado ($9); se leen del PDF oficial.
  nacion_2012s2       Nación 2do semestre 2012: publicado solo en PDF, faltaba.
  caba_2025           CABA 2025: los 4 CSV publicados en BA Data el 20/07/2026.

Cada crudo se busca por su número de fila en un manifest_descargas.tsv (con URL y SHA-256) y
se rechaza si su SHA-256 no coincide. Los PDF, además, deben ser los revisados en
extract_nacion.PDF_DE_PIVOT / PDF_SIN_CSV y conciliar (si no, no se carga nada).

Uso (desde la raíz del repo; `-I` para no importar nada de las carpetas de crudos):
  python -I etl/actualizacion_2026-10-15/regenerar.py ENTRADA.csv CRUDOS_AUDITORIA CRUDOS_CABA_2025
      [--aplicar caba_x1000,...] [--salida etl/data/pauta_oficial_unificado_v2.csv]
      [--informe DIR]

ENTRADA.csv es el CSV unificado publicado antes de esta actualización (SHA-256 ENTRADA_SHA256;
`git show 8241b17:etl/data/pauta_oficial_unificado_v2.csv`). Sin --salida solo verifica e
informa. --informe escribe:
  conciliacion.tsv        por archivo: filas y total antes/después, total oficial y diferencia
  manifest_crudos.tsv     el crudo oficial de cada archivo, con URL, tamaño y SHA-256
  cambios_por_fila.csv    archivos reemplazados: filas que salen (id de antes) y entran (id de
                          después); id = número de fila = orders.id
  textos_conservados.tsv  textos que el PDF escribe distinto y quedan como en la base
  verificacion.txt        filas fuera de los archivos corregidos: idénticas, con su SHA-256
"""

import argparse
import csv
import hashlib
import io
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "etl" / "extractores"))
sys.path.insert(0, str(REPO / "etl"))
import comun  # noqa: E402
import extract_caba  # noqa: E402
import extract_nacion  # noqa: E402
import unificar  # noqa: E402

ENTRADA_SHA256 = "651814756238fa2151f00257a8752e89fb662ac8a50308870092286c7a9a62aa"

# (correccion, accion, jurisdiccion, archivo_origen, (manifest, n), lector, anio, ancla)
#   manifest "auditoria": crudos_2026-10-14 de la auditoría de fuentes; "caba2025": descarga nueva.
#   ancla de los archivos nuevos: dónde los pone unificar.py (ver extraer() de cada extractor).
_2012S1 = ("Nación", "inversion_1er_Semestre_2012_proveedor_rubro.csv")
ARCHIVOS = [
    ("caba_x1000", "reemplazar", "CABA", "pauta-publicitaria-2016.csv",
     ("auditoria", 33), "caba_combinado", 2016, None),
    ("caba_x1000", "reemplazar", "CABA", "pauta-publicitaria-2017-total.csv",
     ("auditoria", 34), "caba_combinado", 2017, None),
    ("nacion_2009", "reemplazar", "Nación", "(nuevo v2) Pauta_por_Proveedor_conIVA-_-2009-mayo-oct.csv",
     ("auditoria", 71), "pivot_pdf", 2009, None),
    ("nacion_2009", "reemplazar", "Nación", "(nuevo v2) Pauta_por_proveedor_conIVA_nov_dic_2009.csv",
     ("auditoria", 72), "pivot_pdf", 2009, None),
    ("nacion_pivots_rubro", "reemplazar", "Nación", "(nuevo v2)segundo_semestre_prov_rubro-2010.csv",
     ("auditoria", 74), "pivot_pdf", 2010, None),
    ("nacion_pivots_rubro", "reemplazar", "Nación", "(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv",
     ("auditoria", 73), "pivot_pdf", 2010, None),
    # extract_nacion.extraer() carga los PDF_SIN_CSV de la carpeta 2012 antes que sus CSV
    ("nacion_2012s2", "agregar", "Nación", "2dosemestre2012_01_prov_rubro.pdf",
     ("auditoria", 79), "pivot_pdf", 2012, ("antes_de", _2012S1)),
    ("nacion_pivots_rubro", "reemplazar", "Nación", "inversion_1er_Semestre_2012_proveedor_rubro.csv",
     ("auditoria", 77), "pivot_pdf", 2012, None),
] + [
    # extract_caba.extraer() recorre las carpetas por año: 2025 va después de 2024, al final de CABA
    ("caba_2025", "agregar", "CABA", nombre, ("caba2025", n), "caba_pertype", 2025,
     ("fin_de", "CABA"))
    for n, nombre in enumerate(["2025_Pauta_Publicitaria_Cine.csv",
                                "2025_Pauta_Publicitaria_Grafica.csv",
                                "2025_Pauta_Publicitaria_Medios_Vecinales.csv",
                                "2025_Pauta_Publicitaria_Radio.csv"], 1)
]
CORRECCIONES = list(dict.fromkeys(a[0] for a in ARCHIVOS))

# Total "Total general" del PDF según la auditoría de fuentes, con otro lector geométrico
# (auditoria_fuentes/salida/auditoria_pivots_nacion_resumen.tsv; 2012-S2: huecos_nacion_2026-10-15).
# Se usa como tercer control, independiente del lector del ETL y de la lectura de texto de abajo.
TOTAL_AUDITORIA = {
    "(nuevo v2) Pauta_por_Proveedor_conIVA-_-2009-mayo-oct.csv": 24557255464,
    "(nuevo v2) Pauta_por_proveedor_conIVA_nov_dic_2009.csv": 7783116527,
    "(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv": 24412814544,
    "(nuevo v2)segundo_semestre_prov_rubro-2010.csv": 41023235585,
    "inversion_1er_Semestre_2012_proveedor_rubro.csv": 42029446928,
    "2dosemestre2012_01_prov_rubro.pdf": 51871929015,
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def leer_manifest(carpeta):
    with open(Path(carpeta) / "manifest_descargas.tsv", encoding="utf-8", newline="") as f:
        return {int(r["n"]): r for r in csv.DictReader(f, delimiter="\t")}


def crudo(carpetas, manifests, ref):
    """Ruta del crudo (manifest, n), verificando su SHA-256 contra el manifest."""
    cual, n = ref
    fila = manifests[cual][n]
    path = Path(carpetas[cual]) / fila["ruta"].replace("\\", "/")
    real = sha256(path)
    if real != fila["sha256"]:
        raise SystemExit(f"ERROR {path}: SHA-256 {real} distinto del manifest ({fila['sha256']})")
    return path, fila


# ---------------------------------------------------------------------------
# Registros con el ETL y su forma en el CSV (igual que unificar.py)
# ---------------------------------------------------------------------------

def leer_registros(lector, path, anio, archivo, cont):
    if lector == "caba_combinado":
        return extract_caba._parse_combinado(path, anio, cont)
    if lector == "caba_pertype":
        return extract_caba._parse_pertype(path, anio, cont)
    if lector == "pivot_pdf":
        sha = (extract_nacion.PDF_DE_PIVOT.get(archivo, (None, None))[1]
               or extract_nacion.PDF_SIN_CSV.get(archivo))
        if sha256(path) != sha:
            raise SystemExit(f"ERROR {path.name}: no es el PDF revisado de {archivo}")
        regs = extract_nacion._parse_pivot_pdf(path, anio, archivo, cont)
        if regs is None:
            raise SystemExit(f"ERROR {path.name}: el PDF no concilia; no se carga")
        return regs
    raise ValueError(lector)


_VP = {"via publica", "vía pública", "via pública", "vía publica"}


def posprocesar(registros):
    """Lo que unificar.unificar() hace después de extraer: medio desde tipo_de_medio, Via
    Publica en un solo valor y el control de calidad final (unificar._valida_fila)."""
    for r in registros:
        if not r.get("medio") and not r.get("proveedor") and r.get("tipo_de_medio"):
            r["medio"] = r["tipo_de_medio"]
        for campo in ("medio", "tipo_de_medio"):
            v = r.get(campo)
            if v and v.strip().lower() in _VP:
                r[campo] = "Via Publica"
    descartes = Counter()
    return [r for r in registros if unificar._valida_fila(r, descartes)], descartes


def _clave_texto(v):
    return re.sub(r"\s+", "", v).replace('""', '"')


def conservar_textos(registros, antes):
    """Regla del proyecto: no cambiar ningún valor que no sea parte de la corrección.

    Al releer un archivo desde el PDF, algunos textos salen distintos de la base solo en espacios
    o en comillas: el PDF escribe "X 4", "P Y M" y "C & N" donde la base dice "X4", "PYM" y "C&N",
    y la base tiene 'LUCRO""NOSOTROS""' (comillas sin desescapar) donde el PDF dice
    'LUCRO"NOSOTROS"'. No es parte de la corrección: se conserva el texto de la base. Devuelve
    [(campo, texto del PDF, texto que queda, filas)]."""
    viejos = [fila_dict(l) for l in antes]
    cambios = Counter()
    for campo in ("proveedor", "medio"):
        presentes = {f[campo] for f in viejos if f[campo]}
        por_clave = {}
        for v in presentes:
            por_clave.setdefault(_clave_texto(v), set()).add(v)
        for r in registros:
            v = r.get(campo)
            if not v or v in presentes:
                continue
            cands = por_clave.get(_clave_texto(v), set())
            if len(cands) == 1:
                r[campo] = next(iter(cands))
                cambios[(campo, v, r[campo])] += 1
    return [(c, v, b, n) for (c, v, b), n in sorted(cambios.items())]


def a_lineas(registros):
    """Líneas del CSV como las escribe unificar.py (con fin de línea LF, el del repo)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=comun.COLUMNS, extrasaction="ignore", lineterminator="\n")
    for r in registros:
        fila = dict(r)
        mv = fila["monto"]
        fila["monto"] = ("%.2f" % mv).rstrip("0").rstrip(".") if isinstance(mv, float) else mv
        w.writerow(fila)
    lineas = buf.getvalue().split("\n")[:-1]
    if len(lineas) != len(registros):
        raise SystemExit("ERROR: un campo trae un salto de línea")
    return [l + "\n" for l in lineas]


def clave(linea):
    fila = next(csv.reader([linea]))
    if len(fila) != len(comun.COLUMNS):
        raise SystemExit(f"ERROR: fila con {len(fila)} campos: {linea!r}")
    return fila[0], fila[8]


def centavos(texto):
    return int((Decimal(texto) * 100).to_integral_value())


def fila_dict(linea):
    return dict(zip(comun.COLUMNS, next(csv.reader([linea]))))


# ---------------------------------------------------------------------------
# Total oficial, leído sin el ETL
# ---------------------------------------------------------------------------

def total_csv_oficial(path):
    """Suma exacta de la columna de importe del CSV oficial (Decimal; los montos de estos
    archivos son números planos con punto decimal: se verifica). Devuelve (centavos, filas,
    detalle): la suma redondeada al centavo una sola vez."""
    texto, _ = comun.leer_texto(path)
    primera = texto.split("\n", 1)[0]
    sep = ";" if primera.count(";") > primera.count(",") else ","
    filas = list(csv.reader(io.StringIO(texto), delimiter=sep))
    i = next(k for k, h in enumerate(filas[0]) if "importe" in h.lower())
    suma, n, raros = Decimal(0), 0, []
    for f in filas[1:]:
        if not any(c.strip() for c in f):
            continue
        v = f[i].strip()
        if not re.fullmatch(r"\d+(\.\d+)?", v):
            raros.append(v)
            continue
        suma += Decimal(v)
        n += 1
    if raros:
        raise SystemExit(f"ERROR {path.name}: importes con otro formato: {raros[:5]}")
    return int((suma * 100).quantize(Decimal(1))), n, f"suma exacta {suma}"


def total_pdf_oficial(path):
    """Total publicado en el PDF, leído del texto de la página (no por coordenadas).

    Pivot por rubro: la última cifra de la fila "Total general". Pivot por mes (2009): no hay
    "Total general"; la fila de totales es la última línea formada solo por montos, y el total
    es la suma de sus columnas."""
    import pdfplumber
    num = r"\d{1,3}(?:\.\d{3})*,\d{2}"
    with pdfplumber.open(path) as pdf:
        lineas = [l.strip() for p in pdf.pages for l in (p.extract_text() or "").split("\n")]
    tg = [l for l in lineas if l.lower().startswith("total general") and re.search(num, l)]
    if tg:
        ultimo = re.findall(num, tg[-1])[-1]
        if "$" in tg[-1]:
            # 2010-S2 escribe "$ 4 10.232.355,85": cada monto va después de su "$"
            ultimo = tg[-1].rsplit("$", 1)[1].replace(" ", "")
            if not re.fullmatch(num, ultimo):
                raise SystemExit(f"ERROR {path.name}: Total general ilegible: {tg[-1]!r}")
        return extract_nacion._centavos_pdf(ultimo), "Total general del PDF"
    solo_montos = [l for l in lineas if l and re.fullmatch(rf"(?:\$\s*)?{num}(?:\s+(?:\$\s*)?{num})+", l)]
    cols = re.findall(num, solo_montos[-1])
    return (sum(extract_nacion._centavos_pdf(c) for c in cols),
            "suma de la fila de totales del PDF (" + " + ".join(cols) + ")")


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("crudos_auditoria")
    ap.add_argument("crudos_caba2025")
    ap.add_argument("--aplicar", default=",".join(CORRECCIONES))
    ap.add_argument("--salida")
    ap.add_argument("--informe")
    a = ap.parse_args()

    aplicar = [c.strip() for c in a.aplicar.split(",") if c.strip()]
    if set(aplicar) - set(CORRECCIONES):
        raise SystemExit(f"ERROR: correcciones desconocidas {set(aplicar) - set(CORRECCIONES)}")
    if sha256(a.entrada) != ENTRADA_SHA256:
        raise SystemExit(f"ERROR: {a.entrada} no es el CSV revisado (SHA-256 {sha256(a.entrada)})")

    carpetas = {"auditoria": a.crudos_auditoria, "caba2025": a.crudos_caba2025}
    manifests = {k: leer_manifest(v) for k, v in carpetas.items()}

    texto = Path(a.entrada).read_bytes().decode("utf-8")
    encabezado, *viejas = texto.split("\n")
    if viejas[-1] != "":
        raise SystemExit("ERROR: el CSV no termina en salto de línea")
    viejas = [l + "\n" for l in viejas[:-1]]
    claves_viejas = [clave(l) for l in viejas]

    # bloques de cada archivo_origen. Los que se tocan o sirven de ancla deben ser contiguos (en
    # PBA hay nombres que se repiten en varios años, como tabula-1.csv: esos no se tocan)
    usados = [x for x in ARCHIVOS if x[0] in aplicar]
    vigilados = {(x[2], x[3]) for x in usados} | {x[7][1] for x in usados if x[7] and x[7][0] == "antes_de"}
    bloques = {}
    for i, k in enumerate(claves_viejas):
        ini, fin = bloques.get(k, (i, i))
        if k in vigilados and fin not in (i - 1, i):
            raise SystemExit(f"ERROR: {k} no es un bloque contiguo")
        bloques[k] = (ini, i)

    nuevas_por_clave, informe = {}, []
    cont = comun.Contador("[regenerar]")
    for corr, accion, jur, archivo, ref, lector, anio, ancla in usados:
        k = (jur, archivo)
        if (accion == "reemplazar") != (k in bloques):
            raise SystemExit(f"ERROR: {k} {'no ' if accion == 'reemplazar' else 'ya '}está en el CSV")
        path, man = crudo(carpetas, manifests, ref)
        regs, descartes = posprocesar(leer_registros(lector, path, anio, archivo, cont))
        if descartes:
            comun.log(f"  {archivo}: descartes del control final {dict(descartes)}")
        if any(r["jurisdiccion"] != jur or r["archivo_origen"] != archivo for r in regs):
            raise SystemExit(f"ERROR: {archivo}: registros con otra jurisdicción o archivo_origen")
        antes = viejas[bloques[k][0]:bloques[k][1] + 1] if k in bloques else []
        conservados = conservar_textos(regs, antes)
        for campo, v, b, n in conservados:
            comun.log(f"  {archivo}: {campo} {v!r} queda como en la base, {b!r} ({n} filas)")
        lineas = a_lineas(regs)
        nuevas_por_clave[k] = lineas

        if lector.startswith("caba"):
            oficial, n_oficial, det = total_csv_oficial(path)
            fuente_total = f"suma de la columna de importe del CSV oficial ({n_oficial} filas; {det})"
        else:
            oficial, fuente_total = total_pdf_oficial(path)
        c_antes = sum(centavos(fila_dict(l)["monto"]) for l in antes)
        c_despues = sum(centavos(fila_dict(l)["monto"]) for l in lineas)
        informe.append({
            "correccion": corr, "accion": accion, "jurisdiccion": jur, "archivo_origen": archivo,
            "fuente": man["url"], "sha256_fuente": man["sha256"],
            "filas_antes": len(antes), "filas_despues": len(lineas),
            "total_antes": c_antes, "total_despues": c_despues, "total_oficial": oficial,
            "diferencia": c_despues - oficial, "total_oficial_fuente": fuente_total,
            "total_auditoria": TOTAL_AUDITORIA.get(archivo),
            "antes": antes, "despues": lineas, "conservados": conservados,
            "inicio_antes": bloques[k][0] if k in bloques else None,
            "crudo": path.name, "man": man, "manifest": f"{ref[0]} n={ref[1]}", "clave": k,
        })

    # --- armado: bloques reemplazados en su lugar, archivos nuevos en su ancla ----------------
    reemplazos = {k: v for k, v in nuevas_por_clave.items() if k in bloques}
    antes_de, fin_de = {}, {}
    for corr, accion, jur, archivo, ref, lector, anio, ancla in usados:
        if accion == "agregar":
            destino = antes_de if ancla[0] == "antes_de" else fin_de
            destino.setdefault(ancla[1], []).extend(nuevas_por_clave[(jur, archivo)])
    for k in antes_de:
        if k not in bloques:
            raise SystemExit(f"ERROR: ancla {k} no está en el CSV")
    ultimo_de = {}
    for i, (jur, _) in enumerate(claves_viejas):
        ultimo_de[jur] = i
    for jur in fin_de:
        if any(j == jur for j, _ in claves_viejas[ultimo_de[jur] + 1:]):
            raise SystemExit(f"ERROR: {jur} no es un bloque contiguo")

    nuevas, hecho = [], set()
    for i, (linea, k) in enumerate(zip(viejas, claves_viejas)):
        if k in antes_de and k not in hecho:
            nuevas += antes_de[k]
        if k in reemplazos:
            if k not in hecho:
                nuevas += reemplazos[k]
        else:
            nuevas.append(linea)
        hecho.add(k)
        if k[0] in fin_de and ultimo_de[k[0]] == i:
            nuevas += fin_de[k[0]]

    # --- verificación: lo que no es parte de la corrección queda idéntico ---------------------
    tocadas = set(nuevas_por_clave)
    resto_viejo = [l for l, k in zip(viejas, claves_viejas) if k not in tocadas]
    resto_nuevo = [l for l in nuevas if clave(l) not in tocadas]
    if resto_viejo != resto_nuevo:
        raise SystemExit("ERROR: cambió alguna fila fuera de los archivos corregidos")
    h_resto = hashlib.sha256("".join(resto_viejo).encode("utf-8")).hexdigest()
    primera = {}
    for i, l in enumerate(nuevas):
        k = clave(l)
        if k in tocadas and k not in primera:
            primera[k] = i
    for r in informe:
        r["inicio_despues"] = primera[r["clave"]]
    salida_txt = encabezado + "\n" + "".join(nuevas)

    print(f"Entrada: {len(viejas)} filas, SHA-256 {ENTRADA_SHA256}")
    print(f"Correcciones: {', '.join(aplicar)}")
    print(f"Filas fuera de los archivos corregidos: {len(resto_viejo)}, idénticas byte a byte en el "
          f"mismo orden (SHA-256 {h_resto})")
    print(f"Salida: {len(nuevas)} filas, SHA-256 "
          f"{hashlib.sha256(salida_txt.encode('utf-8')).hexdigest()}")
    print()
    print(f"{'archivo_origen':58s} {'filas':>13s} {'total antes':>18s} {'total después':>18s} "
          f"{'total oficial':>18s} {'dif':>6s}")
    for r in informe:
        print(f"{r['archivo_origen'][:58]:58s} {r['filas_antes']:>6d}>{r['filas_despues']:<6d} "
              f"{r['total_antes'] / 100:>18,.2f} {r['total_despues'] / 100:>18,.2f} "
              f"{r['total_oficial'] / 100:>18,.2f} {r['diferencia'] / 100:>6,.2f}")

    if a.informe:
        escribir_informe(Path(a.informe), informe, aplicar, len(viejas), len(nuevas), h_resto,
                         len(resto_viejo))
    if a.salida:
        Path(a.salida).write_bytes(salida_txt.encode("utf-8"))
        print(f"\nEscrito {a.salida}")


def _tsv(path, filas):
    """TSV sin comillas (ningún campo trae tabulaciones ni saltos de línea)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for fila in filas:
            celdas = ["" if v is None else str(v) for v in fila]
            if any("\t" in c or "\n" in c for c in celdas):
                raise SystemExit(f"ERROR: campo con tabulación o salto de línea: {celdas}")
            f.write("\t".join(celdas) + "\n")


def escribir_informe(carpeta, informe, aplicar, n_viejas, n_nuevas, h_resto, n_resto):
    carpeta.mkdir(parents=True, exist_ok=True)

    def pesos(c):
        return "" if c is None else f"{c / 100:.2f}"

    _tsv(carpeta / "conciliacion.tsv",
         [["correccion", "accion", "jurisdiccion", "archivo_origen", "filas_antes", "filas_despues",
           "total_antes", "total_despues", "total_oficial", "diferencia", "total_auditoria",
           "total_oficial_fuente", "fuente", "sha256_fuente"]]
         + [[r["correccion"], r["accion"], r["jurisdiccion"], r["archivo_origen"], r["filas_antes"],
             r["filas_despues"], pesos(r["total_antes"]), pesos(r["total_despues"]),
             pesos(r["total_oficial"]), pesos(r["diferencia"]), pesos(r["total_auditoria"]),
             r["total_oficial_fuente"], r["fuente"], r["sha256_fuente"]] for r in informe])
    _tsv(carpeta / "manifest_crudos.tsv",
         [["correccion", "archivo_origen", "crudo", "url", "bytes", "sha256", "last_modified",
           "descargado_utc", "manifest"]]
         + [[r["correccion"], r["archivo_origen"], r["crudo"], r["man"]["url"], r["man"]["bytes"],
             r["man"]["sha256"], r["man"]["last_modified"], r["man"]["descargado_utc"],
             r["manifest"]] for r in informe])
    _tsv(carpeta / "textos_conservados.tsv",
         [["archivo_origen", "campo", "texto_en_el_pdf", "texto_que_queda_el_de_la_base", "filas"]]
         + [[r["archivo_origen"], c, v, b, n] for r in informe for c, v, b, n in r["conservados"]])
    # detalle de los archivos reemplazados: filas que salen (id de antes) y que entran (id de
    # después); las filas iguales no se listan. id = número de fila de datos = orders.id
    with open(carpeta / "cambios_por_fila.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cambio", "id"] + comun.COLUMNS)
        for r in informe:
            if r["accion"] != "reemplazar":
                continue
            for cambio, lineas, otras, inicio in (("sale", r["antes"], r["despues"], r["inicio_antes"]),
                                                  ("entra", r["despues"], r["antes"], r["inicio_despues"])):
                quedan = Counter(lineas) - Counter(otras)
                for j, linea in enumerate(lineas):
                    if quedan[linea]:
                        quedan[linea] -= 1
                        w.writerow([cambio, inicio + j + 1] + next(csv.reader([linea])))
    with open(carpeta / "verificacion.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"correcciones: {', '.join(aplicar)}\n")
        f.write(f"filas: {n_viejas} -> {n_nuevas}\n")
        f.write(f"filas fuera de los archivos corregidos: {n_resto}, idénticas byte a byte y en el "
                f"mismo orden; SHA-256 {h_resto}\n")


if __name__ == "__main__":
    main()

