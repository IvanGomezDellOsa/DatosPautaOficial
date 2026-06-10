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

Tabla orders: id, jurisdiccion, anio, proveedor (norm), medio (norm), monto (deflactado), resolucion.
Si falta aliases.csv, proveedor/medio usan solo la normalizacion algoritmica.
monto siempre se deflacta con ipc_indec.csv.

Solo usa la biblioteca estandar de Python: no requiere pip install.
Uso:  python3 etl/build_db.py
"""

import csv
import json
import math
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# --- rutas (relativas a la ubicacion del script) -------------------------
ETL_DIR = Path(__file__).resolve().parent
DATA_DIR = ETL_DIR / "data"
OUT_DIR = ETL_DIR.parent / "public" / "data"
# La DB monolitica va fuera de public/ para no superar el limite de 25 MiB
# de Cloudflare Pages. Los chunks (.0-.5) y config.json siguen en OUT_DIR.
BUILD_DIR = ETL_DIR / "build"
OUT_DB = BUILD_DIR / "pauta.sqlite"

_CSV_V2 = DATA_DIR / "pauta_oficial_unificado_v2.csv"
_CSV_V1 = DATA_DIR / "pauta_oficial_unificado.csv"
# Preferir la versión v2 (generada por los nuevos extractores en unificar.py)
# si existe; si no, caer al CSV original para no romper builds previos.
CSV_ORDERS = _CSV_V2 if _CSV_V2.exists() else _CSV_V1
CSV_IPC = DATA_DIR / "ipc_indec.csv"
CSV_GOV = DATA_DIR / "governments.csv"
CSV_ALIASES = DATA_DIR / "aliases.csv"
# Mapeo de grupos mediaticos (holdings) -> medios/proveedores. Archivo curado,
# separado de aliases.csv: aliases NUNCA consolida por propiedad. Cada fila es
# (grupo_slug, grupo_nombre, eje, valor); 'valor' es texto crudo que el ETL pasa
# por normalizar() para matchear contra orders.medio / orders.proveedor.
CSV_GRUPOS = DATA_DIR / "grupos_mom.csv"

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

# --- URL stripping --------------------------------------------------------
# Muchos "medios" se cargan como dominios (WWW.FUTUROCK.FM, futurock.fm,
# www.futurock.fm - Web), lo que fragmenta una misma entidad en varias claves.
# Antes de la normalizacion general extraemos la parte semantica del dominio.
#
# Distinguimos dos clases de TLD:
#   - _TLD_CRUFT: extensiones que NO son parte del nombre (com, com.ar, ar,
#     org, net, info, gob.ar...). Se eliminan por completo. Mas largas primero
#     para que "com.ar" gane sobre "ar".
#   - _TLD_NOMBRE: fm / am / tv. Para radios y canales la sigla ES parte del
#     nombre hablado ("Futurock FM"), asi que el punto se vuelve espacio y el
#     token se conserva. Esto ademas fusiona la forma-dominio (futurock.fm) con
#     la forma-nombre (FUTUROCK FM), que es exactamente lo que queremos.
# Conservar fm/am/tv es la opcion conservadora: ante la duda no fusionamos
# (futurock.fm no colapsa con un hipotetico futurock.com).
_TLD_CRUFT = [
    "com.ar", "org.ar", "net.ar", "gob.ar", "gov.ar", "edu.ar",
    "com", "net", "org", "info", "ar",
]
_TLD_NOMBRE = ["fm", "am", "tv"]
_TLD_TODOS = _TLD_NOMBRE + _TLD_CRUFT

_DOMINIO_CHARS_RE = re.compile(r"^[a-z0-9.\-]+$")
_PROTO_RE = re.compile(r"^https?://")
_WWW_RE = re.compile(r"^www\d*\.")


def _parece_dominio(tok):
    """True si el token aislado parece efectivamente una URL/dominio: empieza
    con protocolo o www., o tiene forma de dominio y termina en un TLD conocido."""
    if _PROTO_RE.match(tok) or _WWW_RE.match(tok):
        return True
    core = re.split(r"[/?#]", tok, maxsplit=1)[0]
    if not _DOMINIO_CHARS_RE.match(core) or "." not in core:
        return False
    return any(core.endswith("." + tld) for tld in _TLD_TODOS)


def _strip_dominio(tok):
    """Extrae la parte semantica de un token que parece dominio."""
    tok = _PROTO_RE.sub("", tok)       # protocolo
    tok = _WWW_RE.sub("", tok)         # www. / www2. / ...
    tok = re.split(r"[/?#]", tok, maxsplit=1)[0]  # path / query / fragmento
    if not tok or "." not in tok:
        return tok
    # fm / am / tv: el TLD es parte del nombre -> el punto se vuelve espacio
    for tld in _TLD_NOMBRE:
        if tok.endswith("." + tld):
            tok = tok[: -(len(tld) + 1)] + " " + tld
            return tok.replace(".", " ")
    # cruft: se elimina el TLD por completo (mas largo primero)
    for tld in _TLD_CRUFT:
        if tok.endswith("." + tld):
            tok = tok[: -(len(tld) + 1)]
            break
    return tok.replace(".", " ")  # subdominios restantes -> espacios


def _strip_urls(s):
    """Aplica el stripping de dominios token a token. Solo toca los tokens que
    parecen dominios; el resto (incluidos descriptivos como 'web'/'caba' que
    siguen al dominio) se conserva intacto."""
    if "." not in s and not s.startswith("www"):
        return s  # ningun token podria ser dominio: salida rapida
    return " ".join(
        _strip_dominio(t) if _parece_dominio(t) else t
        for t in s.split()
    )


def _algo_norm(s):
    """Normalizacion algoritmica: minusculas, sin tildes, sin URLs, sin
    puntuacion, sin sufijos societarios, espacios colapsados. Devuelve "" si
    queda vacio."""
    if not s:
        return ""
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    s = _strip_urls(s)  # extrae la parte semantica de dominios antes de limpiar
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


def cargar_grupos(aliases):
    """Lee grupos_mom.csv si existe. Devuelve [{slug, nombre, miembros}], donde
    cada miembro es {eje, valor, norm} con norm = normalizar(valor).

    El mapeo de grupos mediaticos (holdings) vive en su propio CSV, separado de
    aliases.csv: aliases solo colapsa grafias de la MISMA razon social, nunca
    consolida por propiedad. Un grupo puede sumar sobre dos ejes (medio y/o
    proveedor); cada fila de orders tiene un solo medio y un solo proveedor, asi
    que el OR a nivel orden (medio IN (...) OR proveedor IN (...)) no duplica.
    """
    if not CSV_GRUPOS.exists():
        return []
    grupos = {}  # slug -> {slug, nombre, miembros: [...]}
    with CSV_GRUPOS.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            slug = (fila.get("grupo_slug") or "").strip()
            nombre = (fila.get("grupo_nombre") or "").strip()
            eje = (fila.get("eje") or "").strip().lower()
            valor = (fila.get("valor") or "").strip()
            if not slug or not nombre or eje not in ("medio", "proveedor") or not valor:
                continue
            norm = normalizar(valor, aliases)
            if not norm:
                continue
            g = grupos.setdefault(slug, {"slug": slug, "nombre": nombre, "miembros": []})
            g["miembros"].append({"eje": eje, "valor": valor, "norm": norm})
    return list(grupos.values())


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


def crear_esquema(con):
    con.executescript(
        """
        CREATE TABLE orders (
            id            INTEGER PRIMARY KEY,
            jurisdiccion  TEXT NOT NULL,
            anio          INTEGER NOT NULL,
            proveedor     TEXT,
            medio         TEXT,
            monto         REAL,
            resolucion    TEXT
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



def crear_rankings(con, prov_disp, medio_disp, grupos, top_n=5):
    """Pre-computa todos los rankings posibles y los guarda en rankings_cache.

    La data historica es inmutable: pre-calculamos el top N para cada
    combinacion (tipo x jurisdiccion x anio) en el ETL. El front hace una
    lookup puntual de <=20 filas — cero full-scan, cero prefetch exponencial.

    Combinaciones: global (1) + por juris (4) + por anio (~22)
                   + juris x anio (~88) = ~115 por tipo => ~4600 filas total.
    Clave: jurisdiccion='*' = todas las jurisdicciones, anio=0 = todos los anios.

    Tipos: 'proveedor', 'medio' (una dimension de orders) y 'grupo' (holding que
    suma varios medios/proveedores con OR a nivel orden, identico criterio que
    totals_cache). Para grupo, norm = grupo_slug y nombre = grupo_nombre. La
    agregacion global/por-juris/por-anio reusa SUM(total)/SUM(n) sobre el
    desglose por (juris, anio), igual que para proveedor/medio.
    """
    def get_best_names(disp):
        res = []
        for norm, grafias in disp.items():
            nombre = max(grafias.items(), key=lambda kv: (kv[1], kv[0]))[0]
            res.append((norm, nombre))
        return res

    con.executescript("""
        CREATE TEMP TABLE _best_prov(norm TEXT PRIMARY KEY, nombre TEXT);
        CREATE TEMP TABLE _best_medio(norm TEXT PRIMARY KEY, nombre TEXT);
    """)
    con.executemany("INSERT INTO _best_prov VALUES (?,?)", get_best_names(prov_disp))
    con.executemany("INSERT INTO _best_medio VALUES (?,?)", get_best_names(medio_disp))

    # Tabla intermedia auxiliar (se descarta al final)
    con.executescript("""
        CREATE TEMP TABLE _rprov AS
            SELECT o.jurisdiccion, o.anio, o.proveedor AS norm,
                   b.nombre,
                   SUM(o.monto) AS total,
                   COUNT(*) AS n
            FROM orders o
            JOIN _best_prov b ON o.proveedor = b.norm
            WHERE o.proveedor IS NOT NULL
            GROUP BY o.jurisdiccion, o.anio, o.proveedor;

        CREATE TEMP TABLE _rmedio AS
            SELECT o.jurisdiccion, o.anio, o.medio AS norm,
                   b.nombre,
                   SUM(o.monto) AS total,
                   COUNT(*) AS n
            FROM orders o
            JOIN _best_medio b ON o.medio = b.norm
            WHERE o.medio IS NOT NULL
            GROUP BY o.jurisdiccion, o.anio, o.medio;
    """)

    # --- desglose por grupo (holding) -> _rgrupo --------------------------
    # Mismo esquema que _rprov/_rmedio: (jurisdiccion, anio, norm, nombre,
    # total, n). norm = grupo_slug, nombre = grupo_nombre. Por cada grupo se
    # suma sobre ambos ejes con OR a nivel orden (medio IN (...) OR proveedor
    # IN (...)); como cada orden tiene un solo medio y un solo proveedor, el OR
    # no duplica. Mismo criterio que crear_totals.
    con.executescript("""
        CREATE TEMP TABLE _rgrupo(
            jurisdiccion TEXT, anio INTEGER, norm TEXT, nombre TEXT,
            total REAL, n INTEGER);
    """)
    for g in grupos:
        medios = sorted({m["norm"] for m in g["miembros"] if m["eje"] == "medio"})
        provs = sorted({m["norm"] for m in g["miembros"] if m["eje"] == "proveedor"})
        conds, params = [], []
        if medios:
            conds.append(f"medio IN ({','.join('?' * len(medios))})")
            params += medios
        if provs:
            conds.append(f"proveedor IN ({','.join('?' * len(provs))})")
            params += provs
        if not conds:
            continue
        where = " OR ".join(conds)
        con.execute(f"""
            INSERT INTO _rgrupo
            SELECT jurisdiccion, anio, ?, ?, SUM(monto), COUNT(*)
            FROM orders WHERE {where}
            GROUP BY jurisdiccion, anio
        """, [g["slug"], g["nombre"], *params])

    con.executescript("""
        CREATE TABLE rankings_cache (
            tipo         TEXT    NOT NULL,
            jurisdiccion TEXT    NOT NULL,  -- '*' = todas
            anio         INTEGER NOT NULL,  -- 0   = todos
            rank         INTEGER NOT NULL,
            norm         TEXT    NOT NULL,
            nombre       TEXT    NOT NULL,
            total        REAL,
            n            INTEGER NOT NULL
        );
        CREATE INDEX idx_rcache
            ON rankings_cache(tipo, jurisdiccion, anio, rank);
    """)

    def insert_top(tipo, src, juris_key, anio_key, rows):
        con.executemany(
            "INSERT INTO rankings_cache VALUES (?,?,?,?,?,?,?,?)",
            [(tipo, juris_key, anio_key, i + 1, r[0], r[1], r[2], r[3])
             for i, r in enumerate(rows[:top_n])]
        )

    for tipo, tbl in [("proveedor", "_rprov"), ("medio", "_rmedio"), ("grupo", "_rgrupo")]:
        # --- global (todas las jurisdicciones, todos los anios) ---------------
        rows = con.execute(f"""
            SELECT norm, MAX(nombre), SUM(total), SUM(n)
            FROM {tbl} GROUP BY norm ORDER BY 3 DESC LIMIT {top_n}
        """).fetchall()
        insert_top(tipo, tbl, "*", 0, rows)

        # --- por jurisdiccion (todos los anios) --------------------------------
        for (juris,) in con.execute(f"SELECT DISTINCT jurisdiccion FROM {tbl}").fetchall():
            rows = con.execute(f"""
                SELECT norm, MAX(nombre), SUM(total), SUM(n)
                FROM {tbl} WHERE jurisdiccion=? GROUP BY norm ORDER BY 3 DESC LIMIT {top_n}
            """, [juris]).fetchall()
            insert_top(tipo, tbl, juris, 0, rows)

        # --- por anio (todas las jurisdicciones) ------------------------------
        for (anio,) in con.execute(f"SELECT DISTINCT anio FROM {tbl}").fetchall():
            rows = con.execute(f"""
                SELECT norm, MAX(nombre), SUM(total), SUM(n)
                FROM {tbl} WHERE anio=? GROUP BY norm ORDER BY 3 DESC LIMIT {top_n}
            """, [anio]).fetchall()
            insert_top(tipo, tbl, "*", anio, rows)

        # --- por jurisdiccion + anio ------------------------------------------
        for (juris, anio) in con.execute(
            f"SELECT DISTINCT jurisdiccion, anio FROM {tbl}"
        ).fetchall():
            rows = con.execute(f"""
                SELECT norm, nombre, total, n
                FROM {tbl} WHERE jurisdiccion=? AND anio=?
                ORDER BY total DESC LIMIT {top_n}
            """, [juris, anio]).fetchall()
            insert_top(tipo, tbl, juris, anio, rows)

    n = con.execute("SELECT COUNT(*) FROM rankings_cache").fetchone()[0]
    n_grupo = con.execute(
        "SELECT COUNT(*) FROM rankings_cache WHERE tipo='grupo'").fetchone()[0]
    print(f"  rankings_cache: {n} filas (incluye {n_grupo} de tipo='grupo')")


def crear_totals(con, grupos):
    """Pre-computa totals_cache: para CADA entidad (no solo el top-5) los
    totales por (anio, jurisdiccion), mas una fila global (anio=0,
    jurisdiccion='*') con el total historico ya sumado.

    Es el analogo a rankings_cache para la vista "Cuanto recibio": convierte
    un GROUP BY sobre ~500k filas (un round-trip HTTP por page sobre
    sql.js-httpvfs) en una lookup puntual indexada de pocas filas.

    Misma fuente que rankings_cache (SUM(monto_deflactado), COUNT(*)) para que
    los montos sean identicos a los que ya muestra el ranking. Las ordenes con
    monto=0 no estan en orders (se descartan al cargar), asi que no cuentan.

    Ademas de 'proveedor' y 'medio', emite tipo='grupo' (mismo esquema): por
    cada grupo mediatico (holding) los totales sumando sus medios/proveedores.
    norm = grupo_slug. El front hace el mismo lookup que para una entidad suelta.
    """
    con.executescript("""
        CREATE TABLE totals_cache (
            tipo         TEXT    NOT NULL,  -- 'proveedor' | 'medio' | 'grupo'
            norm         TEXT    NOT NULL,
            anio         INTEGER NOT NULL,  -- 0 = todos (fila global)
            jurisdiccion TEXT    NOT NULL,  -- '*' = todas (fila global)
            total        REAL,
            n_ordenes    INTEGER NOT NULL
        );
        CREATE INDEX idx_totals ON totals_cache(tipo, norm);
    """)

    for tipo, col in (("proveedor", "proveedor"), ("medio", "medio")):
        # desglose por anio x jurisdiccion
        con.execute(f"""
            INSERT INTO totals_cache(tipo, norm, anio, jurisdiccion, total, n_ordenes)
            SELECT '{tipo}', {col}, anio, jurisdiccion,
                   SUM(monto), COUNT(*)
            FROM orders
            WHERE {col} IS NOT NULL
            GROUP BY {col}, anio, jurisdiccion
        """)
        # fila global por entidad (total historico, sin sumar en el cliente)
        con.execute(f"""
            INSERT INTO totals_cache(tipo, norm, anio, jurisdiccion, total, n_ordenes)
            SELECT '{tipo}', {col}, 0, '*',
                   SUM(monto), COUNT(*)
            FROM orders
            WHERE {col} IS NOT NULL
            GROUP BY {col}
        """)

    # --- tipo='grupo': holdings que suman varios medios/proveedores ----------
    # El sumatorio usa IN sobre el conjunto de norms (deduplicado), asi que dos
    # grafias que normalizan al mismo norm (p.ej. "Clarin" y "Clarin.com" ->
    # 'clarin') NO se cuentan dos veces. El OR entre ejes tampoco duplica: cada
    # orden tiene un solo medio y un solo proveedor.
    n_grupos_cubiertos = 0
    for g in grupos:
        medios = sorted({m["norm"] for m in g["miembros"] if m["eje"] == "medio"})
        provs = sorted({m["norm"] for m in g["miembros"] if m["eje"] == "proveedor"})
        conds, params = [], []
        if medios:
            conds.append(f"medio IN ({','.join('?' * len(medios))})")
            params += medios
        if provs:
            conds.append(f"proveedor IN ({','.join('?' * len(provs))})")
            params += provs
        if not conds:
            continue
        where = " OR ".join(conds)
        # Si el grupo no matchea ninguna orden, no se inserta (mantiene el cache
        # limpio: getCuantoRecibio devolveria vacio y el front muestra "sin datos").
        n_match = con.execute(
            f"SELECT COUNT(*) FROM orders WHERE {where}", params).fetchone()[0]
        if n_match == 0:
            continue
        n_grupos_cubiertos += 1
        con.execute(f"""
            INSERT INTO totals_cache(tipo, norm, anio, jurisdiccion, total, n_ordenes)
            SELECT 'grupo', ?, anio, jurisdiccion, SUM(monto), COUNT(*)
            FROM orders WHERE {where}
            GROUP BY anio, jurisdiccion
        """, [g["slug"], *params])
        con.execute(f"""
            INSERT INTO totals_cache(tipo, norm, anio, jurisdiccion, total, n_ordenes)
            SELECT 'grupo', ?, 0, '*', SUM(monto), COUNT(*)
            FROM orders WHERE {where}
        """, [g["slug"], *params])

    n = con.execute("SELECT COUNT(*) FROM totals_cache").fetchone()[0]
    print(f"  totals_cache: {n} filas "
          f"({n_grupos_cubiertos}/{len(grupos)} grupos con datos)")


def crear_filtros(con):
    """Pre-computa filtros_cache: para CADA combinacion (jurisdiccion, anio) los
    totales que muestra la filter-bar y los conteos por columna (para ocultar
    columnas vacias). Convierte getTotalesFiltro() de un scan sobre el set
    filtrado (lee fecha/medio/proveedor/resolucion de cada fila) en un lookup
    puntual. Es el cuello del cambio de filtro: sin esto, cambiar a "PBA 2023"
    escanea todas las ordenes de PBA 2023.

    Claves: jurisdiccion='*' = todas, anio=0 = todos. Solo cubre el caso SIN
    filtro de entidad; con proveedor/medio el set es chico y se consulta en vivo.
    Mismas agregaciones que getTotalesFiltro (COUNT(*), SUM(monto_deflactado) y
    COUNT por columna) para que los numeros sean identicos.
    """
    con.executescript("""
        CREATE TABLE filtros_cache (
            jurisdiccion TEXT    NOT NULL,  -- '*' = todas
            anio         INTEGER NOT NULL,  -- 0   = todos
            n_ordenes    INTEGER NOT NULL,
            monto_total  REAL,
            c_medio INTEGER, c_proveedor INTEGER,
            c_monto      INTEGER, c_resolucion INTEGER
        );
        CREATE INDEX idx_filtros ON filtros_cache(jurisdiccion, anio);
    """)
    cols = ("COUNT(*), SUM(monto), COUNT(medio), "
            "COUNT(proveedor), COUNT(monto), COUNT(resolucion)")
    # por (jurisdiccion, anio)
    con.execute(f"INSERT INTO filtros_cache "
                f"SELECT jurisdiccion, anio, {cols} FROM orders GROUP BY jurisdiccion, anio")
    # por jurisdiccion (todos los anios)
    con.execute(f"INSERT INTO filtros_cache "
                f"SELECT jurisdiccion, 0, {cols} FROM orders GROUP BY jurisdiccion")
    # por anio (todas las jurisdicciones)
    con.execute(f"INSERT INTO filtros_cache "
                f"SELECT '*', anio, {cols} FROM orders GROUP BY anio")
    # global (todo)
    con.execute(f"INSERT INTO filtros_cache SELECT '*', 0, {cols} FROM orders")
    n = con.execute("SELECT COUNT(*) FROM filtros_cache").fetchone()[0]
    print(f"  filtros_cache: {n} filas")


def crear_groups(con, top_n=None):
    """Pre-computa groups_cache: TODOS los pares (medio_norm, proveedor_norm),
    rankeados por monto_deflactado, para cada combinacion (jurisdiccion, anio).

    Analogo a rankings_cache pero agrupando por el par en lugar de por una
    sola dimension. El DataTable hace un lookup puntual + paginado aqui (ORDER
    BY rank, LIMIT/OFFSET) en vez de correr un GROUP BY sobre orders (que
    requiere escanear todo el set filtrado y dispara el prefetch exponencial de
    sql.js-httpvfs).

    Se guardan TODAS las combinaciones (no un top-N) para que el usuario pueda
    paginar la base entera en modo agrupado; el front nunca trae mas de una
    pagina por vez. `rank` da el orden (por monto desc) para esa paginacion.
    top_n=None => sin tope; pasar un entero solo para debug.

    Claves: jurisdiccion='*' = todas, anio=0 = todos. Solo cubre el caso SIN
    filtro de entidad; con proveedor/medio el set es chico y se agrupa en vivo.
    """
    limit_clause = f"LIMIT {top_n}" if top_n else ""
    con.executescript("""
        CREATE TABLE groups_cache (
            jurisdiccion   TEXT    NOT NULL,
            anio           INTEGER NOT NULL,
            rank           INTEGER NOT NULL,
            medio_norm     TEXT,
            proveedor_norm TEXT,
            medio          TEXT,
            proveedor      TEXT,
            total          REAL,
            n              INTEGER NOT NULL
        );
        CREATE INDEX idx_gcache ON groups_cache(jurisdiccion, anio, rank);
    """)

    # Tabla temporal: todos los agregados por (juris, anio, medio_norm, prov_norm).
    # Excluye el grupo (null, null): ordenes sin proveedor ni medio identificable,
    # que no aportan informacion util al usuario y distorsionan el ranking.
    con.executescript("""
        CREATE TEMP TABLE _groups AS
            SELECT o.jurisdiccion, o.anio,
                   o.medio    AS medio_norm,
                   o.proveedor AS proveedor_norm,
                   COALESCE(bm.nombre, o.medio)     AS medio,
                   COALESCE(bp.nombre, o.proveedor) AS proveedor,
                   SUM(o.monto) AS total,
                   COUNT(*)     AS n
            FROM orders o
            LEFT JOIN _best_medio bm ON o.medio     = bm.norm
            LEFT JOIN _best_prov  bp ON o.proveedor = bp.norm
            WHERE NOT (o.medio IS NULL AND o.proveedor IS NULL)
            GROUP BY o.jurisdiccion, o.anio, o.medio, o.proveedor;
    """)

    def insert_top(juris_key, anio_key, rows):
        filas = rows[:top_n] if top_n else rows
        con.executemany(
            "INSERT INTO groups_cache VALUES (?,?,?,?,?,?,?,?,?)",
            [(juris_key, anio_key, i + 1,
              r[0], r[1], r[2], r[3], r[4], r[5])
             for i, r in enumerate(filas)]
        )

    # Global
    rows = con.execute(f"""
        SELECT medio_norm, proveedor_norm,
               MAX(medio), MAX(proveedor),
               SUM(total), SUM(n)
        FROM _groups
        GROUP BY medio_norm, proveedor_norm
        ORDER BY 5 DESC {limit_clause}
    """).fetchall()
    insert_top("*", 0, rows)

    # Por jurisdiccion (todos los anios)
    for (juris,) in con.execute(
            "SELECT DISTINCT jurisdiccion FROM _groups").fetchall():
        rows = con.execute(f"""
            SELECT medio_norm, proveedor_norm,
                   MAX(medio), MAX(proveedor),
                   SUM(total), SUM(n)
            FROM _groups WHERE jurisdiccion=?
            GROUP BY medio_norm, proveedor_norm
            ORDER BY 5 DESC {limit_clause}
        """, [juris]).fetchall()
        insert_top(juris, 0, rows)

    # Por anio (todas las jurisdicciones)
    for (anio,) in con.execute(
            "SELECT DISTINCT anio FROM _groups").fetchall():
        rows = con.execute(f"""
            SELECT medio_norm, proveedor_norm,
                   MAX(medio), MAX(proveedor),
                   SUM(total), SUM(n)
            FROM _groups WHERE anio=?
            GROUP BY medio_norm, proveedor_norm
            ORDER BY 5 DESC {limit_clause}
        """, [anio]).fetchall()
        insert_top("*", anio, rows)

    # Por jurisdiccion + anio
    for (juris, anio) in con.execute(
            "SELECT DISTINCT jurisdiccion, anio FROM _groups").fetchall():
        rows = con.execute(f"""
            SELECT medio_norm, proveedor_norm, medio, proveedor, total, n
            FROM _groups WHERE jurisdiccion=? AND anio=?
            ORDER BY total DESC {limit_clause}
        """, [juris, anio]).fetchall()
        insert_top(juris, anio, rows)

    n = con.execute("SELECT COUNT(*) FROM groups_cache").fetchone()[0]
    print(f"  groups_cache: {n} filas")


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
        CREATE INDEX idx_orders_juris_anio_prov  ON orders(jurisdiccion, anio, proveedor);
        CREATE INDEX idx_orders_juris_anio_medio ON orders(jurisdiccion, anio, medio);
        -- Covering index para getOrdenes(agrupado=true): incluye monto
        -- para que SUM() se resuelva sin saltar a la tabla principal.
        -- Sin monto cada fila del GROUP BY scan requiere un acceso
        -- aleatorio a la tabla -> prefetch exponencial de sql.js-httpvfs.
        CREATE INDEX idx_orders_juris_anio_medio_prov ON orders(jurisdiccion, anio, medio, proveedor, monto);
        CREATE INDEX idx_orders_prov_anio        ON orders(proveedor, anio);
        CREATE INDEX idx_orders_medio_anio       ON orders(medio, anio);

        -- Indices de ORDENAMIENTO de la tabla (getOrdenes). Sin estos, ORDER BY
        -- monto hace "USE TEMP B-TREE FOR ORDER BY": SQLite materializa y
        -- ordena en memoria el set filtrado. Sobre sql.js-httpvfs eso dispara
        -- el prefetch exponencial -> "database disk image is malformed".
        -- 'id' no necesita indice: es la PK (orden secuencial nativo).
        CREATE INDEX idx_orders_juris_anio_monto ON orders(jurisdiccion, anio, monto);
        CREATE INDEX idx_orders_anio_monto       ON orders(anio, monto);
        CREATE INDEX idx_orders_monto            ON orders(monto);
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

    # urlPrefix: de donde el front baja los chunks de la SQLite.
    # Cloudflare Pages NO soporta HTTP range requests (devuelve 200 con el archivo
    # completo en vez de 206), lo que rompe sql.js-httpvfs con "database disk image
    # is malformed". Por eso los chunks se sirven desde Cloudflare R2 (que SI
    # devuelve 206). Si R2_PUBLIC_URL esta seteada (build de Cloudflare), apunta
    # ahi; si no (build local), cae a /data/ para poder testear con http-server.
    r2_base = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")
    url_prefix = f"{r2_base}/pauta.sqlite." if r2_base else "/data/pauta.sqlite."

    # Escribir config.json (lo lee el front con from: 'jsonconfig')
    config = {
        "requestChunkSize": 65536,      # = page_size del SQLite (ver PRAGMA arriba)
        "serverMode": "chunked",
        "urlPrefix": url_prefix,
        "serverChunkSize": CHUNK_SIZE,
        "databaseLengthBytes": db_size,
        "suffixLength": suffix_len,
    }
    config_path = OUT_DIR / "config.json"
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return n_chunks, suffix_len, db_size, config_path


def escribir_home(con, prov_disp):
    """Emite public/data/home.json: el estado inicial de la portada precomputado.

    La vista inicial (PBA + anio_mas_reciente, ordenada por id ascendente) es FIJA,
    igual en cada carga. En vez de levantarla en vivo con sql.js-httpvfs --cientos de
    range-requests HTTP encadenados, ~8 s de spinners-- la calculamos aca y la
    servimos como JSON estatico que Astro inlinea como prop. Asi el primer paint
    muestra datos reales sin WASM, sin worker y sin un solo round-trip a la DB;
    sql.js solo arranca cuando el usuario toca un filtro, busca u ordena distinto.

    Replica EXACTAMENTE las queries del front (getOrdenes / getTotalesFiltro /
    useGobierno / getRanking / getCuantoRecibio) para que el seed coincida con lo
    que devolveria la DB. Si cambias esas queries o el default, regenera esto.
    """
    JURIS = "PBA"
    cur = con.cursor()
    # Usar el anio mas reciente con datos reales para la jurisdiccion elegida,
    # para que el seed nunca quede vacio si los datos no llegaron al anio actual.
    row = cur.execute(
        "SELECT MAX(anio) FROM orders WHERE jurisdiccion=?", (JURIS,)
    ).fetchone()
    ANIO = row[0] if (row and row[0]) else 2024

    def rows(sql, prm=()):
        cur.execute(sql, prm)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # 1. Tabla -- getOrdenes(PBA, ANIO, agrupado) pagina 0. El modo por defecto
    #    del DataTable es AGRUPADO, asi que sembramos la primera pagina de
    #    combinaciones (medio,proveedor) desde groups_cache, identico a la query
    #    del front, para que el primer paint no toque sql.js.
    total_filas = cur.execute(
        "SELECT COUNT(*) FROM groups_cache WHERE jurisdiccion=? AND anio=?",
        (JURIS, ANIO)).fetchone()[0]
    filas = rows(
        """SELECT medio_norm, proveedor_norm, medio, proveedor, total, n
           FROM groups_cache WHERE jurisdiccion=? AND anio=?
           ORDER BY rank LIMIT 100""", (JURIS, ANIO))

    # 2. Totales -- getTotalesFiltro
    t = cur.execute(
        """SELECT COUNT(*) n, SUM(monto) total,
                  COUNT(medio) c_medio, COUNT(proveedor) c_proveedor,
                  COUNT(monto) c_monto, COUNT(resolucion) c_resolucion
           FROM orders WHERE jurisdiccion=? AND anio=?""", (JURIS, ANIO)).fetchone()
    totales = {"nOrdenes": t[0], "montoTotal": t[1] or 0,
               "c_medio": t[2], "c_proveedor": t[3], "c_monto": t[4], "c_resolucion": t[5]}

    # 3. Gobierno -- useGobierno
    g = cur.execute(
        """SELECT name, role FROM governments
           WHERE jurisdiccion=? AND CAST(substr(date_from,1,4) AS INTEGER) <= ?
             AND (date_to IS NULL OR CAST(substr(date_to,1,4) AS INTEGER) >= ?)
           ORDER BY date_from DESC LIMIT 1""", (JURIS, ANIO, ANIO)).fetchone()
    gobierno = {"name": g[0], "role": g[1]} if g else None

    # 4/5. Rankings -- getRanking (contextual PBA/2025 y global */0), prov + medio
    def ranking(juris_key, anio_key, tipo):
        return rows(
            """SELECT norm, nombre, total, n FROM rankings_cache
               WHERE tipo=? AND jurisdiccion=? AND anio=? ORDER BY rank LIMIT 5""",
            (tipo, juris_key, anio_key))
    rankingContextual = {"proveedor": ranking(JURIS, ANIO, "proveedor"),
                         "medio": ranking(JURIS, ANIO, "medio"),
                         "grupo": ranking(JURIS, ANIO, "grupo")}
    rankingGlobal = {"proveedor": ranking("*", 0, "proveedor"),
                     "medio": ranking("*", 0, "medio"),
                     "grupo": ranking("*", 0, "grupo")}

    # 6. Demo del Generador (Grupo Clarín) -- getCuantoRecibio tipo='grupo'.
    #    Muestra el top 1 de grupos para que la sección arranque con datos
    #    representativos sin forzar la descarga de search.json (1,5 MB) al inicio.
    grupo_row = cur.execute(
        """SELECT norm, nombre, total, n FROM rankings_cache
           WHERE tipo='grupo' AND jurisdiccion='*' AND anio=0
           ORDER BY rank LIMIT 1""").fetchone()
    generadorDemo = None
    if grupo_row:
        gnorm, gnombre, gtotal_hist, gn_hist = grupo_row
        gpor = rows(
            """SELECT anio, jurisdiccion, total, n_ordenes FROM totals_cache
               WHERE tipo='grupo' AND norm=? ORDER BY anio DESC""", (gnorm,))
        gpor = [r for r in gpor if not (r["anio"] == 0 and r["jurisdiccion"] == "*")]
        generadorDemo = {
            "tipo": "grupo",
            "entidad": {"id": "g:" + gnorm, "norm": gnorm, "nombre": gnombre,
                        "n": gn_hist, "tipo": "grupo"},
            "resultado": {"nombre": gnombre, "norm": gnorm, "tipo": "grupo",
                          "totalHistorico": gtotal_hist or 0, "nOrdenesHistorico": gn_hist,
                          "porAnio": gpor},
        }

    home = {
        "filtroInicial": {"jurisdiccion": JURIS, "anio": ANIO, "ordenPor": "id",
                          "desc": False, "deflactado": True, "entidadTipo": "proveedor"},
        "tabla": {"filas": filas, "totalFilas": total_filas},
        "totales": totales,
        "gobierno": gobierno,
        "rankingContextual": rankingContextual,
        "rankingGlobal": rankingGlobal,
        "generadorDemo": generadorDemo,
    }
    out = OUT_DIR / "home.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(home, f, ensure_ascii=False, separators=(",", ":"))
    return out, len(filas), total_filas, JURIS, ANIO


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


def escribir_grupos(con, grupos):
    """Emite public/data/grupos.json: para cada grupo mediatico su total
    historico y la lista de miembros con su monto individual.

    En modo 'grupo' el buscador del Generador filtra este JSON en cliente (son
    ~25 grupos, busqueda lineal) en vez de usar MiniSearch. El panel de
    transparencia del Generador muestra `miembros` (que medios/razones sociales
    se suman y cuanto aporta cada uno). Los totales salen de totals_cache (misma
    fuente que el resto del sitio), asi que coinciden con "Cuanto recibio".

    Miembros deduplicados por (eje, norm): varias grafias que normalizan al
    mismo norm (Clarin / Clarin.com) colapsan en una sola fila, igual que en el
    sumatorio del grupo. Se conserva la primera grafia como nombre de display.
    """
    def total_global(tipo, norm):
        r = con.execute(
            "SELECT total, n_ordenes FROM totals_cache "
            "WHERE tipo=? AND norm=? AND anio=0 AND jurisdiccion='*'",
            (tipo, norm)).fetchone()
        return (r[0] or 0, r[1] or 0) if r else (0, 0)

    salida = []
    cubiertos = 0
    for g in grupos:
        # dedup miembros por (eje, norm), conservando la primera grafia
        vistos = {}
        for m in g["miembros"]:
            clave = (m["eje"], m["norm"])
            if clave not in vistos:
                t, n = total_global(m["eje"], m["norm"])
                vistos[clave] = {"eje": m["eje"], "nombre": m["valor"],
                                 "norm": m["norm"], "total": t, "n": n}
        miembros = sorted(vistos.values(), key=lambda x: -x["total"])
        gt, gn = total_global("grupo", g["slug"])
        cubierto = gt > 0
        if cubierto:
            cubiertos += 1
        salida.append({
            "slug": g["slug"], "nombre": g["nombre"], "norm": g["slug"],
            "total": gt, "n": gn, "cubierto": cubierto, "miembros": miembros,
        })
    salida.sort(key=lambda x: -x["total"])

    payload = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": ("Media Ownership Monitor Argentina (2018) - Global Media "
                   "Registry, CC BY-ND 4.0"),
        "totalGrupos": len(salida),
        "cubiertos": cubiertos,
        "grupos": salida,
    }
    out = OUT_DIR / "grupos.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return out, len(salida), cubiertos


def main():
    for ruta in (CSV_ORDERS, CSV_IPC, CSV_GOV):
        if not ruta.exists():
            sys.exit(f"ERROR: falta el archivo obligatorio {ruta}")

    aliases = cargar_aliases()
    grupos = cargar_grupos(aliases)
    indice_mes, indice_anio, mes_ref = cargar_deflactor()
    indice_ref = indice_mes[tuple(int(x) for x in mes_ref.split("-"))]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        try:
            OUT_DB.unlink()
        except PermissionError:
            # En Linux con mount CIFS/9p el archivo puede ser read-only;
            # se sobreescribe truncando en lugar de borrar.
            OUT_DB.write_bytes(b"")

    con = sqlite3.connect(OUT_DB)
    # page_size grande = arbol B mas chato + lecturas mas grandes por request.
    # Sobre R2 (que SI sirve range requests) esto reduce mucho la cantidad de
    # round-trips HTTP por query, que es el cuello sobre r2.dev (~234 ms/request).
    # 65536 es el maximo de SQLite. Debe coincidir con requestChunkSize.
    con.execute("PRAGMA page_size = 65536")
    con.execute("PRAGMA journal_mode = OFF")
    crear_esquema(con)

    # --- estadisticas para la tabla meta y la verificacion ----------------
    st = {
        "filas": 0, "monto_nulo": 0, "monto_cero": 0,
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
    # su orden. Columnas extra del CSV (p.ej. archivo_origen)
    # se ignoran sin romper. Evita el bug silencioso de descartar todas las
    # filas por un conteo de columnas que no coincide.
    REQUERIDAS = ("jurisdiccion", "anio", "medio",
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
                medio = d.get("medio") or ""
                prov = d.get("proveedor") or ""
                monto = d.get("monto") or ""
                reso = d.get("resolucion") or ""
                if not jur or not anio:
                    continue
                anio_i = int(anio)
                anios.add(anio_i)
                juris.add(jur)

                # monto nominal
                monto_v = None
                if monto.strip() != "":
                    try:
                        monto_v = float(monto)
                    except ValueError:
                        monto_v = None
                if monto_v is None:
                    st["monto_nulo"] += 1
                elif monto_v == 0.0:
                    st["monto_cero"] += 1
                    continue  # descarta ordenes con monto = $0 (anulaciones/reservas)
                else:
                    st["monto_total"] += monto_v

                st["filas"] += 1

                # deflactor: siempre por anio (ya no hay columna fecha)
                factor = indice_anio.get(anio_i)
                monto_def = monto_v * (indice_ref / factor) if (monto_v is not None and factor) else None
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
                    jur, anio_i,
                    p_norm, m_norm, monto_def,
                    (reso.strip() or None),
                )

    con.executemany(
        "INSERT INTO orders(jurisdiccion, anio, "
        "proveedor, medio, monto, resolucion) VALUES (?,?,?,?,?,?)",
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
        "filas_monto_cero": st["monto_cero"],
        "filas_deflactado_nulo": st["deflactado_nulo"],
        "aliases_csv": ("presente" if CSV_ALIASES.exists() else "ausente"),
        "aliases_aplicados": st["alias_aplicados"],
        "governments_filas": n_gov,
    }
    con.executemany("INSERT INTO meta(clave, valor) VALUES (?,?)",
                     [(k, str(v)) for k, v in meta.items()])

    # --- tablas de rankings pre-computadas (evitan full-scan en el front) ---
    crear_rankings(con, prov_disp, medio_disp, grupos)

    # --- totales pre-computados por entidad (vista "Cuanto recibio") --------
    #     incluye tipo='grupo' (holdings) computado desde grupos_mom.csv
    crear_totals(con, grupos)

    # --- totales/conteos por (jurisdiccion, anio) para la filter-bar ---------
    crear_filtros(con)

    # --- top-100 grupos (medio_norm x proveedor_norm) para el DataTable ------
    crear_groups(con)

    # --- grupos mediaticos (holdings) para el toggle "Grupo mediatico" -------
    out_grupos, n_grupos, n_grupos_cub = escribir_grupos(con, grupos)

    # --- estado inicial de la portada precomputado (evita el waterfall HTTP) -
    out_home, n_home, n_home_total, out_home_juris, out_home_anio = escribir_home(con, prov_disp)

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
    print(f"OK  {config_path}  ({n_chunks} chunks x 20 MiB, suffixLen={suffix_len}, " + f"{db_size:,}" + " bytes)")
    print(f"OK  {out_busq}  ({tam_busq_mb:.2f} MB; "
          f"{n_prov} proveedores, {n_medio} medios)")
    print(f"OK  {out_grupos}  ({n_grupos} grupos, {n_grupos_cub} con datos, "
          f"{out_grupos.stat().st_size/1024:.1f} KB)")
    print(f"OK  {out_home}  (estado inicial {out_home_juris} {out_home_anio}: {n_home}/{n_home_total} filas, "
          f"{out_home.stat().st_size/1024:.1f} KB)")
    for k, v in meta.items():
        print(f"  {k:32s} {v}")

    # --- verificacion post-build ------------------------------------------
    vcon = sqlite3.connect(OUT_DB)
    print("\nSchema final de orders (PRAGMA table_info):")
    for row in vcon.execute("PRAGMA table_info(orders)"):
        print(f"  {row}")
    total_v = vcon.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"COUNT(*) FROM orders: {total_v}")
    monto_null_v = vcon.execute("SELECT COUNT(*) FROM orders WHERE monto IS NULL").fetchone()[0]
    print(f"Filas con monto IS NULL: {monto_null_v}"
          + (" (deflactor ausente para esos anios)" if monto_null_v else " OK"))
    vcon.close()


if __name__ == "__main__":
    main()
