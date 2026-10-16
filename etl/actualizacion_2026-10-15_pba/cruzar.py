# -*- coding: utf-8 -*-
"""
cruzar.py  —  PBA: cruza las resoluciones y anexos oficiales contra las filas de PBA de la base.

No toca el CSV unificado. Lee:
  - el CSV unificado (filas de PBA);
  - ordenes_anexos.csv y anexos.tsv, que escribe leer_anexos.py;
  - la lista de resoluciones de normas.gba.gob.ar (NORMAS.tsv).
Escribe en DIR_SALIDA:
  - resoluciones.tsv: una fila por resolución publicada, con su estado en la base (cargada,
    parcial, faltante) o por qué no se puede cargar (sin anexo, no concilia, ilegible,
    rescisión, rectificación);
  - bloques_base.tsv: cada bloque de la base (archivo_origen + expediente) y la resolución a la
    que corresponde;
  - ordenes_faltantes.csv: las órdenes de los anexos que no están en la base.

La base no guarda el número de OP, así que una fila de la base se empareja con una orden del
anexo por monto exacto y, en este orden de preferencia: proveedor y medio iguales; proveedor
igual; medio igual; solo monto. Los textos se comparan sin tildes, mayúsculas ni signos.

Qué filas de la base pueden emparejarse con qué resolución:
  - PBA_2025.csv guarda la URL de la resolución;
  - los tabula-* de 2020-2023 que guardan el expediente se unen con el expediente impreso en el
    anexo;
  - los bloques sin expediente (casi todo 2021-2024) se asignan a la resolución del mismo año
    con la que comparten más pares (monto, proveedor): esa asignación queda en bloques_base.tsv.

Uso (desde la raíz del repo):
  python -I etl/actualizacion_2026-10-15_pba/cruzar.py CSV LECTURA_DIR NORMAS.tsv DIR_SALIDA
"""

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def clave_txt(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def clave_exp(s):
    m = re.search(r"(\d{4})\s*-\s*(\d+)", s or "")
    return f"{m.group(1)}-{int(m.group(2))}" if m else ""


MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
         "diciembre": 12}


def periodo_de_texto(t):
    """'... Junio/2020' o '... Septiembre 2023 ...' -> '2020-06'; '' si no hay un solo mes."""
    hallados = {(m.group(2), MESES[m.group(1).lower()])
                for m in re.finditer(r"(?i)(" + "|".join(MESES) + r")\W{0,3}(?:del?\s+)?(?:a[ñn]o\W{0,3})?(20\d\d)", t or "")}
    if len(hallados) != 1:
        return ""
    anio, mes = hallados.pop()
    return f"{anio}-{mes:02d}"


def leer_base(path):
    filas = []
    with open(path, encoding="utf-8", newline="") as f:
        for i, d in enumerate(csv.DictReader(f), start=1):
            if d["jurisdiccion"] == "PBA":
                d["id"] = i
                d["m"] = Decimal(d["monto"])
                filas.append(d)
    return filas


def emparejar(base, ordenes, max_nivel=4):
    """Empareja filas de la base con órdenes del anexo. Devuelve (pares, base_sola, ordenes_solas);
    cada par es (fila, orden, nivel) con nivel 1 (proveedor y medio), 2 (proveedor), 3 (medio)
    o 4 (solo monto)."""
    niveles = [
        lambda x, p, m: (x, p, m),
        lambda x, p, m: (x, p),
        lambda x, p, m: (x, m),
        lambda x, p, m: (x,),
    ]
    libres_b = list(base)
    libres_o = list(ordenes)
    pares = []
    for n, f in enumerate(niveles[:max_nivel], start=1):
        idx = defaultdict(list)
        for o in libres_o:
            idx[f(o["m"], clave_txt(o["proveedor"]), clave_txt(o["medio"]))].append(o)
        usados = set()
        quedan_b = []
        for b in libres_b:
            k = f(b["m"], clave_txt(b["proveedor"]), clave_txt(b["medio"]))
            cand = idx.get(k)
            if cand:
                o = cand.pop(0)
                usados.add(id(o))
                pares.append((b, o, n))
            else:
                quedan_b.append(b)
        libres_b = quedan_b
        libres_o = [o for o in libres_o if id(o) not in usados]
    return pares, libres_b, libres_o


def main():
    csv_path, lectura, normas_tsv, salida = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    salida.mkdir(parents=True, exist_ok=True)
    base = leer_base(csv_path)
    anexos = list(csv.DictReader(open(lectura / "anexos.tsv", encoding="utf-8"), delimiter="\t"))
    ordenes = list(csv.DictReader(open(lectura / "ordenes_anexos.csv", encoding="utf-8")))
    for o in ordenes:
        o["m"] = Decimal(o["monto"])
    normas = list(csv.DictReader(open(normas_tsv, encoding="utf-8"), delimiter="\t"))

    # --- resoluciones (una unidad por URL de resolución) ---
    res = {}
    for r in normas:
        u = r["resolucion_url"]
        if u not in res:
            m = re.search(r"/resolucion/(\d{4})/(\d+)/", u)
            res[u] = {"resolucion": f"{m.group(2)}/{m.group(1)}", "resolucion_url": u, "promulgacion": r["promulgacion"],
                      "resumen": r["resumen"], "anexos": [], "titulo": r["titulo"]}
    # período: el del resumen de la resolución; si no dice el mes, el de la referencia del
    # anexo en la hoja de firmas ("Órdenes de Publicidad - Junio/2020")
    resumenes = {r["resolucion_url"]: r["resumen"] for r in normas}
    for a in anexos:
        a["periodo_fuente"] = "resumen" if a["periodo"] else ""
        if not a["periodo"]:
            p = periodo_de_texto(a["referencia"])
            if p:
                a["periodo"], a["periodo_fuente"] = p, "referencia del anexo"
            elif periodo_de_texto(resumenes[a["resolucion_url"]]):
                a["periodo"], a["periodo_fuente"] = periodo_de_texto(resumenes[a["resolucion_url"]]), "resumen"
    per = {a["anexo"]: a["periodo"] for a in anexos}
    por_anexo = defaultdict(list)
    for o in ordenes:
        o["periodo"] = o["periodo"] or per[o["anexo"]]
        por_anexo[o["anexo"]].append(o)
    for a in anexos:
        a["ordenes_l"] = por_anexo.get(a["anexo"], [])
        res[a["resolucion_url"]]["anexos"].append(a)

    # Unidades que se cruzan: aprobaciones con al menos un anexo propio (no repetido) que tenga órdenes.
    def propios(u):
        return [a for a in u["anexos"] if not a["duplicado_de"]]

    unidades = {k: u for k, u in res.items()
                if any(a["tipo"] == "aprobacion" and a["ordenes_l"] for a in propios(u))}
    for u in unidades.values():
        u["ordenes"] = [o for a in propios(u) if a["tipo"] == "aprobacion" for o in a["ordenes_l"]]
        u["exps"] = {clave_exp(e) for a in propios(u) for e in a["expedientes"].split()} - {""}
        anios = Counter(o["periodo"][:4] for o in u["ordenes"] if o["periodo"])
        u["anio"] = anios.most_common(1)[0][0] if anios else u["resolucion"].split("/")[1]

    # --- bloques de la base: archivo_origen + expediente/URL ---
    bloques = defaultdict(list)
    for b in base:
        bloques[(b["archivo_origen"], b["anio"], b["resolucion"])].append(b)
    por_exp = defaultdict(list)
    for k, u in unidades.items():
        for e in u["exps"]:
            por_exp[e].append(k)
    # Paso 1: vínculo directo. PBA_2025.csv por la URL y los bloques con expediente por el
    # expediente impreso en el anexo. Solo con proveedor o medio iguales (niveles 1 a 3).
    directo = {}  # bloque -> unidades
    motivo = {}
    for bk in bloques:
        arch, anio, reso = bk
        if reso.startswith("http"):
            directo[bk] = [reso] if reso in unidades else []
            motivo[bk] = "URL de la resolución"
        elif clave_exp(reso):
            directo[bk] = por_exp.get(clave_exp(reso), [])
            motivo[bk] = "expediente"
        else:
            directo[bk] = []
            motivo[bk] = "sin expediente"
    usada = set()
    pares_u = defaultdict(list)   # unidad -> [(fila, orden, nivel, paso)]
    libres_u = {k: list(u["ordenes"]) for k, u in unidades.items()}
    vinculo = defaultdict(list)   # bloque -> [(unidad, pares, paso)]

    def aplicar(bk, k, filas, max_nivel, paso):
        pares, _, solas = emparejar(filas, libres_u[k], max_nivel)
        for b, o, n in pares:
            usada.add(b["id"])
            pares_u[k].append((b, o, n, paso))
        libres_u[k] = solas
        if pares:
            vinculo[bk].append((k, len(pares), paso))
        return len(pares)

    for bk, us in directo.items():
        for k in us:
            aplicar(bk, k, [b for b in bloques[bk] if b["id"] not in usada], 3, "directo")

    # Paso 2: las filas que quedan sin par (bloques sin expediente, o filas de otro anexo dentro
    # de un bloque con expediente) se asignan bloque contra resolución, empezando por el par que
    # comparte más órdenes (monto y proveedor iguales). Se acepta si comparten al menos 3 órdenes
    # y son la mitad de lo que le queda al bloque o a la resolución: así una orden mensual que se
    # repite igual en otro mes no arrastra una resolución entera.
    def k_ord(x):
        return (x["m"], clave_txt(x["proveedor"]))

    c_bloque = {bk: Counter(k_ord(b) for b in filas if b["id"] not in usada) for bk, filas in bloques.items()}
    c_unidad = {k: Counter(map(k_ord, libres_u[k])) for k in unidades}

    def solapa(bk, k):
        if abs(int(unidades[k]["anio"]) - int(bk[1])) > 1:
            return 0
        n = sum((c_bloque[bk] & c_unidad[k]).values())
        nb, nu = sum(c_bloque[bk].values()), len(libres_u[k])
        return n if n >= 3 and (n >= 0.5 * nb or n >= 0.5 * nu) else 0

    puntaje = {(bk, k): solapa(bk, k) for bk in bloques for k in unidades if c_bloque[bk] and libres_u[k]}
    while True:
        cands = [(n, bk, k) for (bk, k), n in puntaje.items() if n]
        if not cands:
            break
        n, bk, k = max(cands, key=lambda t: (t[0], t[1], t[2]))
        libres_b = [b for b in bloques[bk] if b["id"] not in usada]
        hechos = aplicar(bk, k, libres_b, 3, "por pares")
        c_bloque[bk] = Counter(k_ord(b) for b in bloques[bk] if b["id"] not in usada)
        c_unidad[k] = Counter(map(k_ord, libres_u[k]))
        if not hechos:
            puntaje[(bk, k)] = 0
        for (b2, k2) in list(puntaje):
            if b2 == bk or k2 == k:
                puntaje[(b2, k2)] = solapa(b2, k2) if (hechos or (b2, k2) != (bk, k)) else 0

    # Paso 3: dentro de cada vínculo ya hallado, lo que queda se empareja solo por monto.
    for bk, vs in list(vinculo.items()):
        for k, _, _ in vs:
            libres_b = [b for b in bloques[bk] if b["id"] not in usada]
            if libres_b and libres_u[k]:
                aplicar(bk, k, libres_b, 4, "solo monto")

    resultado = {k: ([(b, o, n) for b, o, n, _ in pares_u[k]], libres_u[k]) for k in unidades}
    asign = {bk: list(dict.fromkeys(k for k, _, _ in vinculo.get(bk, []))) for bk in bloques}
    for bk in bloques:
        if vinculo.get(bk):
            motivo[bk] += "; " + ", ".join(f"{unidades[k]['resolucion']}={n} ({paso})" for k, n, paso in vinculo[bk])

    base_sin_par = [b for b in base if b["id"] not in usada]

    # --- tabla por resolución ---
    tabla = []
    faltantes = []
    for k, u in sorted(res.items(), key=lambda kv: (int(kv[1]["resolucion"].split("/")[1]),
                                                    int(kv[1]["resolucion"].split("/")[0]))):
        prop = propios(u)
        tipos = sorted({a["tipo"] for a in prop}) or ["(sin anexo)"]
        fila = {
            "resolucion": u["resolucion"], "promulgacion": u["promulgacion"], "resolucion_url": k,
            "tipo": "/".join(tipos), "periodo": " ".join(sorted({a["periodo"] for a in prop if a["periodo"]})),
            "anexos": " ".join(a["anexo"] for a in u["anexos"]),
            "expedientes": " ".join(sorted({e for a in prop for e in a["expedientes"].split()})),
            "ordenes_anexo": sum(int(a["ordenes"]) for a in prop),
            "total_anexo": f"{sum(Decimal(a['suma_ordenes']) for a in prop):.2f}",
            "total_impreso": " ".join(a["totales_impresos"] for a in prop if a["totales_impresos"]),
            "concilia": "/".join(sorted({a["concilia"] for a in prop})) or "",
            "en_base_ordenes": 0, "en_base_monto": "0.00", "faltan_ordenes": 0, "faltan_monto": "0.00",
            "emparejadas_nivel_1_2_3_4": "", "estado": "", "nota": "",
        }
        if not u["anexos"]:
            fila["estado"] = "sin anexo publicado"
            fila["nota"] = u["resumen"][:160]
        elif not prop:
            fila["estado"] = "anexo repetido de otra resolución"
        elif "aprobacion" not in tipos:
            fila["estado"] = tipos[0]
            fila["nota"] = u["resumen"][:160]
        elif k in resultado:
            pares, solas = resultado[k]
            fila["en_base_ordenes"] = len(pares)
            fila["en_base_monto"] = f"{sum(o['m'] for _, o, _ in pares):.2f}"
            fila["faltan_ordenes"] = len(solas)
            fila["faltan_monto"] = f"{sum(o['m'] for o in solas):.2f}"
            niv = Counter(n for _, _, n in pares)
            fila["emparejadas_nivel_1_2_3_4"] = "/".join(str(niv[i]) for i in (1, 2, 3, 4))
            fila["estado"] = ("cargada" if not solas else "faltante" if not pares else "parcial")
            for o in solas:
                faltantes.append({"resolucion": u["resolucion"], "resolucion_url": k, "estado": fila["estado"], **{
                    c: o[c] for c in ("anexo", "periodo", "expediente", "op", "proveedor", "medio", "monto",
                                      "proveedor_renglones", "medio_renglones", "continuacion", "pagina")}})
        else:
            fila["estado"] = "anexo sin órdenes legibles"
        if fila["concilia"] and "no" in fila["concilia"]:
            fila["nota"] = ("; ".join(f"{a['anexo']}: {a['motivo']}" for a in prop if a["concilia"] == "no") + " " + fila["nota"]).strip()
        tabla.append(fila)

    def tsv(nombre, filas):
        with open(salida / nombre, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]), delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(filas)

    tsv("resoluciones.tsv", tabla)
    tsv("bloques_base.tsv", [{
        "archivo_origen": bk[0], "anio": bk[1], "resolucion_en_base": bk[2], "filas": len(f),
        "monto": f"{sum(b['m'] for b in f):.2f}",
        "filas_sin_par": sum(1 for b in f if b["id"] not in usada),
        "monto_sin_par": f"{sum(b['m'] for b in f if b['id'] not in usada):.2f}",
        "resoluciones": " ".join(unidades[k]["resolucion"] for k in asign[bk]),
        "vinculo": motivo[bk], "primer_id": f[0]["id"], "ultimo_id": f[-1]["id"],
    } for bk, f in bloques.items()])
    with open(salida / "ordenes_faltantes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(faltantes[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(faltantes)
    with open(salida / "base_sin_par.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "anio", "fecha", "proveedor", "medio", "monto", "resolucion", "archivo_origen"])
        for b in base_sin_par:
            w.writerow([b["id"], b["anio"], b["fecha"], b["proveedor"], b["medio"], b["monto"], b["resolucion"], b["archivo_origen"]])

    # resumen por año
    print("anio estado resoluciones ordenes_anexo faltan_ordenes faltan_monto")
    agg = defaultdict(lambda: [0, 0, 0, Decimal(0)])
    for t in tabla:
        anio = t["periodo"][:4] if t["periodo"] else t["resolucion"].split("/")[1]
        a = agg[(anio, t["estado"])]
        a[0] += 1
        a[1] += int(t["ordenes_anexo"])
        a[2] += int(t["faltan_ordenes"])
        a[3] += Decimal(t["faltan_monto"])
    for k in sorted(agg):
        print(*k, *agg[k])
    print("filas de la base sin par:", len(base_sin_par), Counter(b["anio"] for b in base_sin_par))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
