#!/usr/bin/env python3
"""build_db.py - construye la base SQLite del sitio Datos Pauta Oficial.

Fase 3 del proyecto. Toma el CSV unificado de Fase 2 y produce la base que el
navegador consulta con sql.js-httpvfs.

Entradas (en etl/data/):
  - pauta_oficial_unificado.csv  OBLIGATORIO  esquema canonico de 8 columnas
  - ipc_indec.csv                OBLIGATORIO  serie mensual de inflacion
  - governments.csv              OBLIGATORIO  vigencias de gestion (hardcoded)
  - aliases.csv                  OPCIONAL     normalizacion curada de nombres

Salida:
  - public/data/pauta.sqlite     base read-only (archivo unico, para uso local)
  - public/data/pauta.sqlite.N   chunks de 20 MiB para Cloudflare Pages
  - public/data/config.json      config de sql.js-httpvfs (serverMode: chunked)
  - public/data/search.json      entidades distintas (proveedor/medio) para
                                 la busqueda client-side con MiniSearch

El script es ADITIVO: las columnas derivadas existen siempre y mejoran cuando
aparecen sus insumos. Si falta aliases.csv, proveedor_norm/medio_norm usan solo
la normalizacion algoritmica. monto_deflactado siempre se calcula con ipc_indec.csv.

Solo usa la biblioteca estandar de Python: no requiere pip install.
Uso:  python3 etl/build_db.py
"""

import csv
import json
import math
import re
import sqlite3
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

# --- rutas (relativas a la ubicacion del script) -------------------------
ETL_DIR = Path(__file__).resolve().parent
DATA_DIR = ETL_DIR / "data"
OUT_DIR = ETL_DIR.parent / "public" / "data"
# La DB monolitica va fuera de public/ para no superar el limite de 25 MiB
# de Cloudflare Pages. Los chunks (.0-.5) y config.json siguen en OUT_DIR.
BUILD_DIR = ETL_DIR / "build"
OUT_DB = BUILD_DIR / "pauta.sqlite"

CSV_ORDERS = DATA_DIR / "pauta_oficial_unificado.csv"
CSV_IPC = DATA_DIR / "ipc_indec.csv"
CSV_GOV = DATA_DIR / "governments.csv"
CSV_ALIASES = DATA_DIR / "aliases.csv"

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Secuencias de tokens de sufijos societarios a descartar al final de un
# nombre. Tras sacar acentos y reemplazar puntuacion por espacios, "S.A."
# queda como ["s", "a"]. Solo se aplica a proveedor_norm/medio_norm (claves
# de agrupacion); la columna cruda nunca se toca. Orden: mas largas primero.
_SUFIJOS = [
    ["s", "a", "i", "c", "y", "f"],
    ["s", "a", "i", "c"],
    ["s", "a", "c", "i"],
    ["s", "r", "l"],
    ["s", "a", "s"],
    ["s", "c", "a"],
    ["s", "a"],
    ["saicyf"], ["sacif"], ["saicf"], ["saic"], ["saci"],
    ["srl"], ["sas"], ["sca"], ["sa"], ["ltda"],
]


def _algo_norm(s):
    """Normalizacion algoritmica: minusculas, sin tildes, sin puntuacion,
    sin sufijos societarios, espacios colapsados. Devuelve "" si queda vacio."""
    if not s:
        return ""
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    if not s:
        return ""
    toks = s.split()
    # descarta sufijos societarios al final, de forma repetida; nunca vacia
    # el nombre por completo (requiere que quede al menos un token).
    cambio = True
    while cambio and toks:
        cambio = False
        for seq in _SUFIJOS:
            n = len(seq)
            if len(toks) > n and toks[-n:] == seq:
                toks = toks[:-n]
                cambio = True
                break
    return " ".join(toks)


def normalizar(valor, aliases):
    """Clave normalizada para agrupar. Si el nombre figura en aliases.csv,
    se usa el nombre canonico; si no, la normalizacion algoritmica."""
    clave = _algo_norm(valor)
    if not clave:
        return None
    if clave in aliases:
        return _algo_norm(aliases[clave]) or clave
    return clave


def cargar_aliases():
    """Lee aliases.csv si existe. Devuelve dict {clave_norm_cruda: canonico}."""
    if not CSV_ALIASES.exists():
        return {}
    aliases = {}
    with CSV_ALIASES.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            crudo = (fila.get("nombre_crudo") or "").strip()
            canon = (fila.get("nombre_canonico") or "").strip()
            if crudo and canon:
                aliases[_algo_norm(crudo)] = canon
    return aliases


def cargar_deflactor():
    """Lee ipc_indec.csv (variacion % mensual) y arma el deflactor.

    Devuelve (indice_mes, indice_anio, mes_ref) donde:
      - indice_mes[(anio, mes)]  nivel de indice encadenado de ese mes
      - indice_anio[anio]        promedio anual del indice (para filas sin mes)
      - mes_ref                  'AAAA-MM' del ultimo mes (base de la deflactacion)

    monto_deflactado = monto * (indice_mes[ref] / indice_mes[mes_de_la_fila]).
    """
    filas = []
    with CSV_IPC.open(newline="", encoding="utf-8") as f:
        for d in csv.DictReader(f):
            filas.append((int(d["anio"]), int(d["mes"]), float(d["variacion_pct"])))
    filas.sort()
    indice_mes = {}
    nivel = 100.0
    for anio, mes, var in filas:
        nivel *= (1 + var / 100.0)
        indice_mes[(anio, mes)] = nivel
    # promedio anual del nivel de indice
    por_anio = {}
    for (anio, _mes), val in indice_mes.items():
        por_anio.setdefault(anio, []).append(val)
    indice_anio = {a: sum(v) / len(v) for a, v in por_anio.items()}
    anio_ref, mes_ref = filas[-1][0], filas[-1][1]
    return indice_mes, indice_anio, f"{anio_ref:04d}-{mes_ref:02d}"


def parse_fecha_iso(valor):
    """Devuelve (fecha_iso, mes) si el valor es una fecha ISO valida;
    si no, (None, None). El esquema fija fecha = ISO 8601 o NULL."""
    if not valor or not ISO_RE.match(valor):
        return None, None
    try:
        d = date.fromisoformat(valor)
    except ValueError:
        return None, None
    return valor, d.month


def crear_esquema(con):
    con.executescript(
        """
        CREATE TABLE orders (
            id                INTEGER PRIMARY KEY,
            jurisdiccion      TEXT NOT NULL,
            anio              INTEGER NOT NULL,
            fecha             TEXT,
            medio             TEXT,
            proveedor         TEXT,
            monto             REAL,
            monto_deflactado  REAL,
            resolucion        TEXT,
            proveedor_norm    TEXT,
            medio_norm        TEXT
        );

        CREATE TABLE governments (
            id            INTEGER PRIMARY KEY,
            jurisdiccion  TEXT NOT NULL,
            name          TEXT NOT NULL,
            role          TEXT NOT NULL,
            date_from     TEXT NOT NULL,
            date_to       TEXT
        );

        CREATE TABLE meta (
            clave  TEXT PRIMARY KEY,
            valor  TEXT
        );
        """
    )


def crear_indices(con):
    # Indices compuestos que mapean a las 3 funciones de la web. El prefijo
    # izquierdo de cada compuesto cubre tambien las consultas mas simples:
    #   - (jurisdiccion, anio, *) sirve para filtrar por jurisdiccion sola
    #     y por jurisdiccion+anio (tabla con filtros, ranking).
    #   - (proveedor_norm, anio) / (medio_norm, anio) sirven el caso
    #     "Cuanto recibio" (proveedor/medio-first), y su prefijo cubre la
    #     busqueda por proveedor/medio sin jurisdiccion.
    # Se omite a proposito un indice por (anio) solo: agregarlo unicamente si
    # el front termina permitiendo filtrar por anio sin jurisdiccion.
    con.executescript(
        """
        CREATE INDEX idx_orders_juris_anio_prov  ON orders(jurisdiccion, anio, proveedor_norm);
        CREATE INDEX idx_orders_juris_anio_medio ON orders(jurisdiccion, anio, medio_norm);
        CREATE INDEX idx_orders_prov_anio        ON orders(proveedor_norm, anio);
        CREATE INDEX idx_orders_medio_anio       ON orders(medio_norm, anio);
        """
    )
    # FAST-FOLLOW (no implementar hasta tener el query layer escrito):
    # sobre sql.js-httpvfs lo que duele son los round-trips HTTP, no el
    # tamano. Cuando las queries reales de agregacion existan, medir con
    # EXPLAIN QUERY PLAN y, si hacen saltos a la tabla, volver covering los
    # indices de "Cuanto recibio" / ranking agregando monto y monto_deflactado
    # para que la suma se resuelva leyendo solo el indice:
    #   CREATE INDEX ix_prov_cover  ON orders(proveedor_norm, anio, jurisdiccion, monto, monto_deflactado);
    #   CREATE INDEX ix_medio_cover ON orders(medio_norm, anio, jurisdiccion, monto, monto_deflactado);
    #   CREATE INDEX ix_juris_anio_prov_cov  ON orders(jurisdiccion, anio, proveedor_norm, monto_deflactado);
    #   CREATE INDEX ix_juris_anio_medio_cov ON orders(jurisdiccion, anio, medio_norm, monto_deflactado);
    # (reemplazarian a los compuestos de arriba; pagan tamano por menos round-trips).


def cargar_governments(con):
    filas = []
    with CSV_GOV.open(newline="", encoding="utf-8") as f:
        for d in csv.DictReader(f):
            filas.append((
                d["jurisdiccion"].strip(),
                d["name"].strip(),
                d["role"].strip(),
                d["date_from"].strip(),
                (d["date_to"].strip() or None),
            ))
    con.executemany(
        "INSERT INTO governments(jurisdiccion, name, role, date_from, date_to) "
        "VALUES (?,?,?,?,?)", filas)
    return len(filas)


def split_db():
    """Parte la SQLite en chunks de CHUNK_SIZE bytes para Cloudflare Pages.

    Cloudflare Pages rechaza archivos > 25 MiB. La DB de ~106 MB se parte en
    pauta.sqlite.0, pauta.sqlite.1, ... + config.json.

    El front carga los chunks con serverMode='chunked' de sql.js-httpvfs:
      createDbWorker([{ from: 'jsonconfig', configUrl: '/data/config.json' }], ...)

    Llama despues de que OUT_DB ya existe (al final de main()).
    """
    CHUNK_SIZE = 20 * 1024 * 1024  # 20 MiB — margen comodo bajo el limite de 25 MiB

    data = OUT_DB.read_bytes()
    db_size = len(data)
    n_chunks = math.ceil(db_size / CHUNK_SIZE)
    suffix_len = len(str(n_chunks - 1))  # digitos necesarios para el sufijo

    # Limpiar chunks anteriores para evitar chunks huerfanos de una build previa
    for old in OUT_DIR.glob("pauta.sqlite.*"):
        old.unlink()

    # Escribir chunks
    for i in range(n_chunks):
        chunk = data[i * CHUNK_SIZE: (i + 1) * CHUNK_SIZE]
        (OUT_DIR / f"pauta.sqlite.{i}").write_bytes(chunk)

    # Escribir config.json (lo lee el front con from: 'jsonconfig')
    config = {
        "requestChunkSize": 1024,       # page_size del SQLite (ver PRAGMA arriba)
        "serverMode": "chunked",
        "urlPrefix": "/data/pauta.sqlite.",
        "serverChunkSize": CHUNK_SIZE,
        "databaseLengthBytes": db_size,
        "suffixLength": suffix_len,
    }
    config_path = OUT_DIR / "config.json"
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return n_chunks, suffix_len, db_size, config_path


def escribir_busqueda(prov_disp, medio_disp):
    """Emite public/data/search.json para la busqueda client-side (MiniSearch).

    El buscador resuelve texto -> clave normalizada sobre el universo chico de
    entidades distintas (no sobre las 504k ordenes): el front filtra orders por
    proveedor_norm/medio_norm, que estan indexadas. Por eso esto vive como JSON
    estatico y no como FTS5 dentro de la SQLite.

    Cada item: {norm, nombre, n}. 'nombre' es la grafia cruda mas frecuente de
    esa clave; 'n' es la cantidad de ordenes (util para ordenar sugerencias).
    """
    def entidades(disp):
        items = []
        for norm, grafias in disp.items():
            nombre = max(grafias.items(), key=lambda kv: (kv[1], kv[0]))[0]
            items.append({"norm": norm, "nombre": nombre,
                          "n": sum(grafias.values())})
        items.sort(key=lambda it: (-it["n"], it["norm"]))
        return items

    payload = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proveedores": entidades(prov_disp),
        "medios": entidades(medio_disp),
    }
    out = OUT_DIR / "search.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return out, len(payload["proveedores"]), len(payload["medios"])


def main():
    for ruta in (CSV_ORDERS, CSV_IPC, CSV_GOV):
        if not ruta.exists():
            sys.exit(f"ERROR: falta el archivo obligatorio {ruta}")

    aliases = cargar_aliases()
    indice_mes, indice_anio, mes_ref = cargar_deflactor()
    indice_ref = indice_mes[tuple(int(x) for x in mes_ref.split("-"))]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()

    con = sqlite3.connect(OUT_DB)
    con.execute("PRAGMA page_size = 1024")   # optimo para sql.js-httpvfs
    con.execute("PRAGMA journal_mode = OFF")
    crear_esquema(con)

    # --- estadisticas para la tabla meta y la verificacion ----------------
    st = {
        "filas": 0, "monto_nulo": 0, "fecha_no_iso": 0, "fecha_nula": 0,
        "deflactado_nulo": 0, "monto_total": 0.0, "monto_def_total": 0.0,
        "alias_aplicados": 0,
    }
    prov_raw, prov_norm, medio_raw, medio_norm_set = set(), set(), set(), set()
    anios = set()
    juris = set()
    # Para search.json (MiniSearch client-side): por cada clave normalizada,
    # cuenta de cada grafia cruda para elegir luego un nombre representativo.
    prov_disp = {}   # proveedor_norm -> {nombre_crudo: count}
    medio_disp = {}  # medio_norm -> {nombre_crudo: count}

    # Columnas que necesita la base. Se leen por NOMBRE (DictReader), no por
    # posicion: asi el script no depende de cuantas columnas trae el CSV ni de
    # su orden. Columnas extra del CSV (p.ej. tipo_de_medio, archivo_origen)
    # se ignoran sin romper. Evita el bug silencioso de descartar todas las
    # filas por un conteo de columnas que no coincide.
    REQUERIDAS = ("jurisdiccion", "anio", "fecha", "medio",
                  "proveedor", "monto", "resolucion")

    def filas_orders():
        with CSV_ORDERS.open(newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            faltan = [c for c in REQUERIDAS if c not in (lector.fieldnames or [])]
            if faltan:
                sys.exit(f"ERROR: al CSV unificado le faltan columnas: {faltan}")
            for d in lector:
                jur = (d.get("jurisdiccion") or "").strip()
                anio = (d.get("anio") or "").strip()
                fecha = d.get("fecha") or ""
                medio = d.get("medio") or ""
                prov = d.get("proveedor") or ""
                monto = d.get("monto") or ""
                reso = d.get("resolucion") or ""
                if not jur or not anio:
                    continue
                st["filas"] += 1
                anio_i = int(anio)
                anios.add(anio_i)
                juris.add(jur)

                fecha_iso, mes = parse_fecha_iso(fecha)
                if fecha == "":
                    st["fecha_nula"] += 1
                elif fecha_iso is None:
                    st["fecha_no_iso"] += 1

                # monto nominal
                monto_v = None
                if monto.strip() != "":
                    try:
                        monto_v = float(monto)
                    except ValueError:
                        monto_v = None
                if monto_v is None:
                    st["monto_nulo"] += 1
                else:
                    st["monto_total"] += monto_v

                # deflactor: por mes si hay fecha ISO, si no por anio
                factor = None
                if mes is not None and (anio_i, mes) in indice_mes:
                    factor = indice_ref / indice_mes[(anio_i, mes)]
                elif anio_i in indice_anio:
                    factor = indice_ref / indice_anio[anio_i]
                monto_def = monto_v * factor if (monto_v is not None and factor) else None
                if monto_def is None:
                    st["deflactado_nulo"] += 1
                else:
                    st["monto_def_total"] += monto_def

                # normalizacion
                prov_v = prov.strip() or None
                medio_v = medio.strip() or None
                p_norm = normalizar(prov_v, aliases)
                m_norm = normalizar(medio_v, aliases)
                if prov_v:
                    prov_raw.add(prov_v)
                    if _algo_norm(prov_v) in aliases:
                        st["alias_aplicados"] += 1
                if p_norm:
                    prov_norm.add(p_norm)
                    if prov_v:
                        d = prov_disp.setdefault(p_norm, {})
                        d[prov_v] = d.get(prov_v, 0) + 1
                if medio_v:
                    medio_raw.add(medio_v)
                if m_norm:
                    medio_norm_set.add(m_norm)
                    if medio_v:
                        d = medio_disp.setdefault(m_norm, {})
                        d[medio_v] = d.get(medio_v, 0) + 1

                yield (
                    jur, anio_i, fecha_iso,
                    medio_v, prov_v, monto_v, monto_def,
                    (reso.strip() or None), p_norm, m_norm,
                )

    con.executemany(
        "INSERT INTO orders(jurisdiccion, anio, fecha, medio, "
        "proveedor, monto, monto_deflactado, resolucion, "
        "proveedor_norm, medio_norm) VALUES (?,?,?,?,?,?,?,?,?,?)",
        filas_orders())

    if st["filas"] == 0:
        con.close()
        sys.exit("ERROR: 0 filas insertadas; revisar el CSV unificado "
                 "(columnas/encoding). No se genera una base vacia.")

    n_gov = cargar_governments(con)
    crear_indices(con)

    # --- tabla meta -------------------------------------------------------
    meta = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filas_orders": st["filas"],
        "jurisdicciones": ", ".join(sorted(juris)),
        "anio_min": min(anios),
        "anio_max": max(anios),
        "monto_total_nominal": f"{st['monto_total']:.2f}",
        "monto_total_deflactado": f"{st['monto_def_total']:.2f}",
        "deflactado_mes_referencia": mes_ref,
        "deflactado_fuentes": "INDEC; Eco Go (2007-2015)",
        "proveedores_distintos_crudo": len(prov_raw),
        "proveedores_distintos_norm": len(prov_norm),
        "medios_distintos_crudo": len(medio_raw),
        "medios_distintos_norm": len(medio_norm_set),
        "filas_monto_nulo": st["monto_nulo"],
        "filas_fecha_nula": st["fecha_nula"],
        "filas_fecha_no_iso": st["fecha_no_iso"],
        "filas_deflactado_nulo": st["deflactado_nulo"],
        "aliases_csv": ("presente" if CSV_ALIASES.exists() else "ausente"),
        "aliases_aplicados": st["alias_aplicados"],
        "governments_filas": n_gov,
    }
    con.executemany("INSERT INTO meta(clave, valor) VALUES (?,?)",
                     [(k, str(v)) for k, v in meta.items()])

    con.commit()
    con.execute("ANALYZE")
    con.commit()
    con.execute("VACUUM")
    con.close()

    # --- split chunked para Cloudflare Pages ------------------------------
    n_chunks, suffix_len, db_size, config_path = split_db()

    # --- indice de busqueda client-side -----------------------------------
    out_busq, n_prov, n_medio = escribir_busqueda(prov_disp, medio_disp)
    tam_busq_mb = out_busq.stat().st_size / (1024 * 1024)

    # --- reporte ----------------------------------------------------------
    tam_mb = OUT_DB.stat().st_size / (1024 * 1024)
    print(f"OK  {OUT_DB}  ({tam_mb:.1f} MB)")
    print(f"OK  {config_path}  "
          f"({n_chunks} chunks x 20 MiB, suffixLen={suffix_len}, "
          f"{db_size:,} bytes)")
    print(f"OK  {out_busq}  ({tam_busq_mb:.2f} MB; "
          f"{n_prov} proveedores, {n_medio} medios)")
    for k, v in meta.items():
        print(f"  {k:32s} {v}")


if __name__ == "__main__":
    main()
