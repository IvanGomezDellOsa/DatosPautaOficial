# -*- coding: utf-8 -*-
"""
agregar.py  —  PBA: agrega a la base las órdenes de los anexos oficiales que faltan.

Toma la salida de leer_anexos.py (las órdenes leídas de cada anexo PDF) y de cruzar.py (qué
órdenes de cada resolución no están en la base) y agrega al CSV unificado solo las órdenes de los
anexos que cumplen todo esto:
  - el anexo es de aprobación de gasto (no rescisión ni rectificación) y no repite otro anexo;
  - la suma de sus órdenes concilia al centavo con el total impreso en el anexo;
  - la resolución está en la lista de CARGAR (abajo), revisada a mano: faltante (ninguna orden
    en la base) o parcial (la base tiene una parte, y con lo que se agrega la resolución queda
    exactamente igual al anexo).
Todo lo demás del CSV queda idéntico byte a byte y en el mismo orden: el script lo verifica.

Las filas nuevas van al final del bloque de PBA (después de PBA_2025.csv), en el orden de las
resoluciones (año y número) y, dentro de cada una, en el orden del anexo. Campos:
  - anio y fecha: el mes de las órdenes según el resumen de la resolución (AAAA-MM-01), como en
    PBA_2025.csv;
  - proveedor y medio: el texto de la celda del anexo; si la celda ocupa dos renglones se une
    con un espacio, igual que en los tabula-* de la base;
  - tipo_de_medio vacío, como el resto de PBA;
  - resolucion: la URL de la resolución en normas.gba.gob.ar, como en PBA_2025.csv;
  - archivo_origen: el nombre del PDF del anexo.

Etapa 2 (--etapa 2, 16/10/2026): las 3 resoluciones cuyo resumen y anexo no dicen el mes
(33/2023, 45/2023 y 274/2024). El mes sale del texto oficial de la resolución, que se bajó con
permiso del usuario: el script exige que el PDF tenga el SHA-256 de PERIODO_DEL_TEXTO, que diga
"emitida(s) durante el mes de <mes> del año <año>" y que el monto de su artículo 1 sea el total
del anexo. Se parte del CSV que dejó la etapa 1 y las filas van al final del bloque de PBA.

Uso (desde la raíz del repo):
  python -I etl/actualizacion_2026-10-15_pba/agregar.py ENTRADA.csv LECTURA_DIR CRUCE_DIR
      [--etapa 2 --textos DIR_TEXTOS] [--salida etl/data/pauta_oficial_unificado_v2.csv] [--informe DIR]
Sin --salida solo verifica e informa. CRUCE_DIR es la salida de cruzar.py sobre ENTRADA.csv.
"""

import argparse
import csv
import hashlib
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "actualizacion_2026-10-15"))
import regenerar  # noqa: E402  (agrega etl/ y etl/extractores al path)
from regenerar import a_lineas, comun, fila_dict, posprocesar, sha256  # noqa: E402

ENTRADA_SHA256 = {
    1: "dbe7b01fc41e9051972b237799ad8de24c475fe10ba0f3f1b02e5dfbb431c74a",  # antes de la etapa 1
    2: "e9ac121acab5e72500e454ee4a9a27f393359cbb068f51d2f03c6e2e2915cddf",  # después de la etapa 1
}

# Resoluciones que se cargan (resolución -> estado esperado en cruzar.py). Ver LEEME.md.
CARGAR = {
    "55/2020": "faltante", "80/2020": "parcial", "98/2020": "faltante", "118/2020": "parcial",
    "119/2020": "parcial", "123/2020": "faltante", "124/2020": "faltante", "129/2020": "parcial",
    "133/2020": "parcial", "134/2020": "faltante", "136/2020": "parcial", "137/2020": "parcial",
    "140/2020": "faltante", "193/2020": "faltante", "220/2020": "faltante", "221/2020": "faltante",
    "19/2021": "faltante", "20/2021": "faltante", "35/2021": "parcial", "39/2021": "faltante",
    "40/2021": "faltante", "51/2021": "faltante", "52/2021": "faltante", "65/2021": "faltante",
    "72/2021": "faltante", "80/2021": "faltante", "81/2021": "faltante", "85/2021": "faltante",
    "88/2021": "faltante", "91/2021": "faltante", "95/2021": "faltante", "99/2021": "faltante",
    "101/2021": "faltante", "123/2021": "faltante", "127/2021": "faltante", "144/2021": "faltante",
    "145/2021": "faltante", "147/2021": "faltante", "149/2021": "faltante", "161/2021": "faltante",
    "171/2021": "faltante", "178/2021": "faltante", "182/2021": "faltante", "183/2021": "faltante",
    "192/2021": "faltante", "205/2021": "faltante", "28/2022": "faltante", "46/2022": "faltante",
    "47/2022": "faltante", "50/2022": "faltante", "57/2022": "faltante", "122/2022": "faltante",
    "167/2022": "faltante", "243/2022": "faltante", "245/2022": "faltante", "246/2022": "faltante",
    "261/2022": "faltante", "262/2022": "faltante", "263/2022": "faltante", "44/2023": "faltante",
    "70/2023": "faltante", "71/2023": "faltante", "86/2023": "faltante", "90/2023": "faltante",
    "139/2023": "faltante", "236/2023": "faltante", "315/2023": "faltante", "111/2024": "faltante",
    "125/2024": "faltante", "223/2024": "faltante", "261/2024": "faltante", "263/2024": "faltante",
    "264/2024": "faltante", "301/2025": "parcial", "307/2025": "faltante", "308/2025": "faltante",
    "309/2025": "faltante", "311/2025": "faltante",
}

# Etapa 2: resolución -> (mes de las órdenes, PDF del texto oficial, su SHA-256, total del art. 1)
PERIODO_DEL_TEXTO = {
    "33/2023": ("2022-11", "xDwLdZSK.pdf",
                "01b1722a470b7af614dc113f7dbb950b0c3bf7157c940fc14f481413fecd3603", "1875500.00"),
    "45/2023": ("2022-12", "xb3Ra5cp.pdf",
                "dbbce15db463b0c2c4ec6462877fa7845e4fbaf49dfee481de2303084f08842c", "60191748.00"),
    "274/2024": ("2024-11", "0XnqrlHd.pdf",
                 "7a5199bb3d00b2fa1013914c7a447af08f560334b71c6f0d6516d0197588c9c3", "237373821.00"),
}
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def verificar_texto(carpeta, res):
    """Controla el texto oficial de la resolución y devuelve el mes de las órdenes."""
    import re
    import pdfplumber
    periodo, archivo, sha, total = PERIODO_DEL_TEXTO[res]
    path = Path(carpeta) / archivo
    if sha256(path) != sha:
        raise SystemExit(f"ERROR {res}: {path} no es el texto revisado")
    with pdfplumber.open(path) as pdf:
        t = " ".join((p.extract_text() or "").replace(chr(10), " ") for p in pdf.pages)
    art1 = t[t.index("ARTÍCULO 1"):t.index("ARTÍCULO 2")]
    m = re.search(r"emitidas? durante el mes de (\w+) del año (\d{4})", art1)
    if not m or f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}" != periodo:
        raise SystemExit(f"ERROR {res}: el artículo 1 no dice el mes {periodo}")
    mt = re.search(r"\(\s*\$\s*([\d.]+,\d{2})\s*\)", art1)
    if not mt or Decimal(mt.group(1).replace(".", "").replace(",", ".")) != Decimal(total):
        raise SystemExit(f"ERROR {res}: el artículo 1 no dice el total {total}")
    return periodo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("lectura")
    ap.add_argument("cruce")
    ap.add_argument("--salida")
    ap.add_argument("--informe")
    ap.add_argument("--etapa", type=int, choices=(1, 2), default=1)
    ap.add_argument("--textos")
    a = ap.parse_args()
    cargar = CARGAR if a.etapa == 1 else {r: "faltante" for r in PERIODO_DEL_TEXTO}
    if sha256(a.entrada) != ENTRADA_SHA256[a.etapa]:
        raise SystemExit(f"ERROR: {a.entrada} no es el CSV publicado (SHA-256 {sha256(a.entrada)})")
    lectura, cruce = Path(a.lectura), Path(a.cruce)

    anexos = {r["anexo"]: r for r in csv.DictReader(open(lectura / "anexos.tsv", encoding="utf-8"), delimiter="\t")}
    resol = {r["resolucion"]: r for r in csv.DictReader(open(cruce / "resoluciones.tsv", encoding="utf-8"), delimiter="\t")}
    faltan = defaultdict(list)
    for o in csv.DictReader(open(cruce / "ordenes_faltantes.csv", encoding="utf-8")):
        faltan[o["resolucion"]].append(o)

    registros, informe = [], []
    for res, estado in sorted(cargar.items(), key=lambda kv: (int(kv[0].split("/")[1]), int(kv[0].split("/")[0]))):
        t = resol[res]
        if t["estado"] != estado:
            raise SystemExit(f"ERROR {res}: estado {t['estado']}, se esperaba {estado}")
        ords = faltan[res]
        for an in {o["anexo"] for o in ords}:
            x = anexos[an]
            if x["tipo"] != "aprobacion" or x["duplicado_de"] or x["concilia"] != "si":
                raise SystemExit(f"ERROR {res} {an}: no es un anexo de aprobación propio que concilie")
        # con lo que se agrega, la resolución queda igual a su anexo (al centavo y en órdenes)
        suma = sum(Decimal(o["monto"]) for o in ords)
        if suma != Decimal(t["faltan_monto"]) or len(ords) != int(t["faltan_ordenes"]):
            raise SystemExit(f"ERROR {res}: faltantes inconsistentes")
        if Decimal(t["en_base_monto"]) + suma != Decimal(t["total_anexo"]):
            raise SystemExit(f"ERROR {res}: base + agregado no da el total del anexo")
        n0 = len(registros)
        if a.etapa == 2:
            if Decimal(t["total_anexo"]) != Decimal(PERIODO_DEL_TEXTO[res][3]):
                raise SystemExit(f"ERROR {res}: el total del anexo no es el del artículo 1")
            periodo_texto = verificar_texto(a.textos, res)
        for o in ords:
            periodo = o["periodo"] if a.etapa == 1 else periodo_texto
            if len(periodo) != 7 or periodo.endswith("-00"):
                raise SystemExit(f"ERROR {res}: sin mes ({periodo!r})")
            m = Decimal(o["monto"])
            if "%.2f" % float(m) != f"{m:.2f}":
                raise SystemExit(f"ERROR {res}: el monto {m} no se puede escribir exacto")
            registros.append(comun.registro(
                "PBA", int(periodo[:4]), float(m), o["anexo"], fecha=f"{periodo}-01",
                proveedor=o["proveedor"], medio=o["medio"], resolucion=t["resolucion_url"]))
        informe.append({"resolucion": res, "estado": estado, "anexos": t["anexos"],
                        "ordenes_agregadas": len(registros) - n0, "monto_agregado": f"{suma:.2f}",
                        "en_base_antes": t["en_base_monto"], "total_anexo": t["total_anexo"],
                        "total_impreso": t["total_impreso"]})

    limpios, descartes = posprocesar(registros)
    if descartes or len(limpios) != len(registros):
        raise SystemExit(f"ERROR: el control de calidad de unificar.py descartaría filas: {descartes}")
    nuevas = a_lineas(limpios)

    with open(a.entrada, encoding="utf-8", newline="") as f:
        lineas = f.readlines()
    encabezado, datos = lineas[0], lineas[1:]
    ult_pba = max(i for i, l in enumerate(datos) if l.startswith("PBA,"))
    salida = [encabezado] + datos[:ult_pba + 1] + nuevas + datos[ult_pba + 1:]

    # control: las filas que no se tocan quedan idénticas y en el mismo orden
    resto = salida[:ult_pba + 2] + salida[ult_pba + 2 + len(nuevas):]
    if resto != lineas:
        raise SystemExit("ERROR: cambió una fila que no debía cambiar")
    suma_nuevas = sum(Decimal(fila_dict(l)["monto"]) for l in nuevas)
    print(f"filas: {len(datos)} -> {len(salida) - 1} (+{len(nuevas)}); monto agregado {suma_nuevas:.2f}")
    print(f"primer id nuevo: {ult_pba + 2}; las filas de Santa Fe corren su id en {len(nuevas)}")
    print("SHA-256 del resto (filas viejas, en orden):", hashlib.sha256("".join(lineas).encode()).hexdigest())
    for r in informe:
        print(r)

    if a.salida:
        txt = "".join(salida)
        with open(a.salida, "w", encoding="utf-8", newline="") as f:
            f.write(txt)
        print("escrito", a.salida, hashlib.sha256(txt.encode("utf-8")).hexdigest())
    if a.informe:
        Path(a.informe).mkdir(parents=True, exist_ok=True)
        with open(Path(a.informe) / "conciliacion.tsv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(informe[0]), delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(informe)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
