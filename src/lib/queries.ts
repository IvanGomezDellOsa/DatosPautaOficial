/**
 * queries.ts — las 3 funciones de query de Datos Pauta Oficial.
 *
 * Cada función mapea a una de las 3 vistas de la home:
 *   1. getOrdenes()       → Tabla con filtros (modo agrupado por defecto)
 *   1b. getDetalleGrupo() → Filas individuales de un grupo (lazy load)
 *   2. getCuantoRecibio() → Generador "Cuánto recibió"
 *   3. getRanking()       → Rankings (contextual y global)
 *
 * Más getMeta() para el hero de datos.
 *
 * Todas usan los índices compuestos definidos en build_db.py:
 *   idx_orders_juris_anio_prov / idx_orders_juris_anio_medio
 *   idx_orders_juris_anio_medio_prov
 *   idx_orders_prov_anio / idx_orders_medio_anio
 */

import { query } from "./db";

// ---------------------------------------------------------------------------
// Tipos compartidos
// ---------------------------------------------------------------------------

export type Orden = {
  id: number;
  medio: string | null;
  proveedor: string | null;
  monto: number | null;
  resolucion: string | null;
  jurisdiccion: string;
  anio: number;
};

/** Fila devuelta por getOrdenes en modo agrupado (GROUP BY medio, proveedor). */
export type OrdenAgrupada = {
  medio_norm: string | null;
  proveedor_norm: string | null;
  medio: string | null;
  proveedor: string | null;
  total: number | null;    // SUM(monto)
  n: number;               // COUNT(*)
};

export type RankingItem = {
  norm: string;
  nombre: string;  // grafía cruda más frecuente
  total: number;   // SUM(monto_deflactado)
  n: number;       // COUNT(*)
};

export type TotalPorAnioJuris = {
  anio: number;
  jurisdiccion: string;
  total: number;
  n_ordenes: number;
};

/** Proveedor/medio son entidades sueltas; 'grupo' es un holding pre-agregado
 *  en el ETL (totals_cache tipo='grupo'). El lookup es idéntico para los tres. */
export type TipoEntidad = "proveedor" | "medio" | "grupo";

export type ResultadoCuantoRecibio = {
  nombre: string;
  norm: string;
  tipo: TipoEntidad;
  totalHistorico: number;
  nOrdenesHistorico: number;
  porAnio: TotalPorAnioJuris[];
};

export type MetaStats = {
  filas_orders: number;
  jurisdicciones: string;
  anio_min: number;
  anio_max: number;
  monto_total_deflactado: number;
  deflactado_mes_referencia: string;
  proveedores_distintos_norm: number;
  medios_distintos_norm: number;
};

// ---------------------------------------------------------------------------
// 1. Tabla con filtros
// ---------------------------------------------------------------------------

export interface FiltrosTabla {
  jurisdiccion?: string;
  anio?: number;
  /** clave normalizada devuelta por MiniSearch */
  entidadNorm?: string;
  entidadTipo?: "proveedor" | "medio";
  /** Orden del modo individual (lo fija el componente, no la URL). */
  ordenPor?: "monto" | "id";
  desc?: boolean;
  pagina?: number;
  porPagina?: number;
  /** Modo agrupado: GROUP BY medio_norm, proveedor_norm. Ignora pagina/porPagina. */
  agrupado?: boolean;
}

/**
 * Devuelve una página de órdenes aplicando los filtros activos.
 *
 * Con agrupado=true (modo DataTable): devuelve hasta 2000 filas agrupadas
 * por (medio_norm, proveedor_norm) ordenadas por total DESC.
 *
 * Sin agrupado: devuelve filas individuales paginadas.
 */
export async function getOrdenes(filtros: FiltrosTabla = {}): Promise<{
  filas: Orden[] | OrdenAgrupada[];
  totalFilas: number;
}> {
  const {
    jurisdiccion,
    anio,
    entidadNorm,
    entidadTipo,
    ordenPor = "monto",
    desc = true,
    pagina = 0,
    porPagina = 100,
    agrupado = false,
  } = filtros;

  const wheres: string[] = [];
  const params: (string | number | null)[] = [];

  if (jurisdiccion) {
    wheres.push("jurisdiccion = ?");
    params.push(jurisdiccion);
  }
  if (anio) {
    wheres.push("anio = ?");
    params.push(anio);
  }
  if (entidadNorm && entidadTipo === "proveedor") {
    wheres.push("proveedor = ?");
    params.push(entidadNorm);
  }
  if (entidadNorm && entidadTipo === "medio") {
    wheres.push("medio = ?");
    params.push(entidadNorm);
  }

  const where = wheres.length ? `WHERE ${wheres.join(" AND ")}` : "";

  // ── Modo agrupado ────────────────────────────────────────────────────────
  if (agrupado) {
    // Sin entidad: lookup puntual + PAGINADO en groups_cache (pre-computado en
    // el ETL, que ahora guarda TODAS las combinaciones, no un top-N). Evita el
    // GROUP BY sobre orders y permite recorrer la base entera agrupada sin traer
    // miles de filas de golpe. ORDER BY rank usa idx_gcache; LIMIT/OFFSET pagina.
    if (!entidadNorm) {
      const [{ total }] = await query<{ total: number }>(
        `SELECT COUNT(*) as total FROM groups_cache WHERE jurisdiccion = ? AND anio = ?`,
        [jurisdiccion ?? "*", anio ?? 0],
      );
      const filas = await query<OrdenAgrupada>(
        `SELECT medio_norm, proveedor_norm, medio, proveedor, total, n
         FROM groups_cache
         WHERE jurisdiccion = ? AND anio = ?
         ORDER BY rank
         LIMIT ? OFFSET ?`,
        [jurisdiccion ?? "*", anio ?? 0, porPagina, pagina * porPagina],
      );
      return { filas, totalFilas: Number(total) };
    }
    // Con entidad: el set es chico (un solo proveedor/medio), GROUP BY en vivo es
    // rapido. Igual se pagina por consistencia con la UI. HAVING excluye el grupo
    // (null,null): ordenes sin proveedor ni medio.
    const [{ total }] = await query<{ total: number }>(
      `SELECT COUNT(*) as total FROM (
         SELECT 1 FROM orders ${where}
         GROUP BY medio, proveedor
         HAVING medio IS NOT NULL OR proveedor IS NOT NULL)`,
      params,
    );
    const filas = await query<OrdenAgrupada>(
      `SELECT medio AS medio_norm, proveedor AS proveedor_norm,
              medio, proveedor,
              SUM(monto) as total, COUNT(*) as n
       FROM orders ${where}
       GROUP BY medio, proveedor
       HAVING medio IS NOT NULL OR proveedor IS NOT NULL
       ORDER BY total DESC
       LIMIT ? OFFSET ?`,
      [...params, porPagina, pagina * porPagina],
    );
    return { filas, totalFilas: Number(total) };
  }

  // ── Modo individual (original) ───────────────────────────────────────────
  const orden = ordenPor === "id"
    ? `id ${desc ? "DESC" : "ASC"}`
    : `monto ${desc ? "DESC" : "ASC"} NULLS LAST`;

  // Count total para paginación (usa el mismo WHERE para ser consistente)
  const [{ total }] = await query<{ total: number }>(
    `SELECT COUNT(*) as total FROM orders ${where}`,
    [...params],
  );

  // Filas de la página
  const filas = await query<Orden>(
    `SELECT id, medio, proveedor, monto,
            resolucion, jurisdiccion, anio
     FROM orders ${where}
     ORDER BY ${orden}
     LIMIT ? OFFSET ?`,
    [...params, porPagina, pagina * porPagina],
  );

  return { filas, totalFilas: Number(total) };
}

// ---------------------------------------------------------------------------
// 1b. Detalle de un grupo (lazy load al expandir en DataTable)
// ---------------------------------------------------------------------------

/**
 * Devuelve una página de órdenes individuales de un par (medio_norm,
 * proveedor_norm) con los filtros de jurisdicción/año activos. Solo se llama al
 * expandir una fila agrupada; el resultado se cachea/acumula en el componente.
 *
 * Paginado (limite/offset) para no bajar de golpe todas las órdenes de un grupo
 * grande (p.ej. 1366 casi idénticas): el front carga de a `limite` y ofrece
 * "ver más". El índice idx_orders_juris_anio_medio_prov incluye `monto`, así que
 * con jurisdicción+año filtrados el ORDER BY monto + LIMIT/OFFSET se resuelve por
 * índice, sin temp B-tree ni prefetch exponencial sobre sql.js-httpvfs.
 */
export async function getDetalleGrupo(
  medio_norm: string | null,
  proveedor_norm: string | null,
  filtros: Pick<FiltrosTabla, "jurisdiccion" | "anio"> = {},
  limite = 500,
  offset = 0,
): Promise<Orden[]> {
  const { jurisdiccion, anio } = filtros;
  const wheres: string[] = [];
  const params: (string | number | null)[] = [];

  if (jurisdiccion)   { wheres.push("jurisdiccion = ?");   params.push(jurisdiccion); }
  if (anio)           { wheres.push("anio = ?");            params.push(anio); }
  if (medio_norm)     { wheres.push("medio = ?");      params.push(medio_norm); }
  if (proveedor_norm) { wheres.push("proveedor = ?");  params.push(proveedor_norm); }

  const where = wheres.length ? `WHERE ${wheres.join(" AND ")}` : "";
  return query<Orden>(
    `SELECT id, medio, proveedor, monto,
            resolucion, jurisdiccion, anio
     FROM orders ${where}
     ORDER BY monto DESC NULLS LAST, id DESC
     LIMIT ? OFFSET ?`,
    [...params, limite, offset],
  );
}

// ---------------------------------------------------------------------------
// 2. Cuánto recibió
// ---------------------------------------------------------------------------

/**
 * Total recibido por un proveedor, medio o grupo mediático, desglosado por
 * año+jurisdicción.
 *
 * Para tipo='grupo' el lookup es idéntico: el ETL pre-agrega el holding en
 * totals_cache (tipo='grupo', norm=grupo_slug) sumando sus medios/proveedores,
 * así que el front nunca hace scan/GROUP BY sobre orders.
 *
 * Lee totals_cache (pre-computado en el ETL) en lugar de hacer un GROUP BY
 * sobre las ~500k filas de orders. Igual que rankings_cache: la data histórica
 * es inmutable, así que el cache es siempre válido y la query es una lookup
 * puntual indable (idx_totals) de pocas filas — sin full-scan ni round-trips
 * HTTP por page. El total histórico viene en la fila global (anio=0,
 * jurisdiccion='*'), así que no hay que sumar en el cliente.
 */
export async function getCuantoRecibio(
  norm: string,
  tipo: TipoEntidad,
  nombreDisplay: string,
): Promise<ResultadoCuantoRecibio> {
  const filas = await query<TotalPorAnioJuris>(
    `SELECT anio, jurisdiccion, total, n_ordenes
     FROM totals_cache
     WHERE tipo = ? AND norm = ?
     ORDER BY anio DESC`,
    [tipo, norm],
  );

  // La fila global (anio=0, jurisdiccion='*') trae el total histórico ya sumado;
  // el resto es el desglose por año+jurisdicción.
  const esGlobal = (r: TotalPorAnioJuris) => r.anio === 0 && r.jurisdiccion === "*";
  const global = filas.find(esGlobal);
  const porAnio = filas.filter((r) => !esGlobal(r));

  const totalHistorico = global
    ? Number(global.total ?? 0)
    : porAnio.reduce((acc, r) => acc + (r.total ?? 0), 0);
  const nOrdenesHistorico = global
    ? Number(global.n_ordenes ?? 0)
    : porAnio.reduce((acc, r) => acc + (r.n_ordenes ?? 0), 0);

  return {
    nombre: nombreDisplay,
    norm,
    tipo,
    totalHistorico,
    nOrdenesHistorico,
    porAnio,
  };
}

// ---------------------------------------------------------------------------
// 3. Rankings
// ---------------------------------------------------------------------------

export interface FiltrosRanking {
  jurisdiccion?: string;
  anio?: number;
  tipo?: "proveedor" | "medio" | "grupo";
  limite?: number;
}

/**
 * Top N proveedores o medios por monto deflactado.
 * Sin filtros → ranking global (toda la base, cacheado en tabla meta).
 * Con jurisdiccion/anio → ranking contextual.
 */
export async function getRanking(filtros: FiltrosRanking = {}): Promise<RankingItem[]> {
  const { jurisdiccion, anio, tipo = "proveedor", limite = 5 } = filtros;

  // Todos los rankings estan pre-computados en rankings_cache por el ETL.
  // La data historica es inmutable, asi que el cache es siempre valido.
  // La query es una lookup puntual de <=20 filas — sin scan, sin prefetch.
  // Clave: jurisdiccion='*' = todas; anio=0 = todos.
  const jurisKey = jurisdiccion ?? "*";
  const anioKey  = anio ?? 0;

  return query<RankingItem>(
    `SELECT norm, nombre, total, n
     FROM rankings_cache
     WHERE tipo = ? AND jurisdiccion = ? AND anio = ?
     ORDER BY rank
     LIMIT ?`,
    [tipo, jurisKey, anioKey, limite],
  );
}

// ---------------------------------------------------------------------------
// Meta — hero de datos
// ---------------------------------------------------------------------------

/**
 * Lee las estadísticas de la tabla meta (generadas por build_db.py).
 */
export async function getMeta(): Promise<MetaStats> {
  const rows = await query<{ clave: string; valor: string }>(
    "SELECT clave, valor FROM meta",
  );
  const map = Object.fromEntries(rows.map((r) => [r.clave, r.valor]));
  return {
    filas_orders: Number(map.filas_orders ?? 0),
    jurisdicciones: map.jurisdicciones ?? "",
    anio_min: Number(map.anio_min ?? 0),
    anio_max: Number(map.anio_max ?? 0),
    monto_total_deflactado: Number(map.monto_total_deflactado ?? 0),
    deflactado_mes_referencia: map.deflactado_mes_referencia ?? "",
    proveedores_distintos_norm: Number(map.proveedores_distintos_norm ?? 0),
    medios_distintos_norm: Number(map.medios_distintos_norm ?? 0),
  };
}

// ---------------------------------------------------------------------------
// Totales del filtro activo (para el subtitle de la filter bar)
// ---------------------------------------------------------------------------

/**
 * Devuelve el conteo de órdenes y la suma de monto deflactado para los
 * filtros activos — se muestra en "18.420 órdenes · AR$ 9.840.300.000".
 */
export async function getTotalesFiltro(
  filtros: Omit<FiltrosTabla, "pagina" | "porPagina" | "ordenPor" | "desc">,
): Promise<{
  nOrdenes: number;
  montoTotal: number;
  c_medio: number;
  c_proveedor: number;
  c_monto: number;
  c_resolucion: number;
}> {
  const { jurisdiccion, anio, entidadNorm, entidadTipo } = filtros;

  // Caso comun (sin filtro de entidad): lookup puntual en filtros_cache, sin
  // escanear orders. Es lo que hace rapido el cambio de filtro. filtros_cache
  // tiene una fila por (jurisdiccion, anio) con '*'=todas y 0=todos.
  if (!entidadNorm) {
    const [c] = await query<{ n_ordenes: number; monto_total: number; c_medio: number; c_proveedor: number; c_monto: number; c_resolucion: number }>(
      `SELECT n_ordenes, monto_total, c_medio, c_proveedor, c_monto, c_resolucion
       FROM filtros_cache WHERE jurisdiccion = ? AND anio = ?`,
      [jurisdiccion ?? "*", anio ?? 0],
    );
    if (c) {
      return {
        nOrdenes: Number(c.n_ordenes ?? 0),
        montoTotal: Number(c.monto_total ?? 0),
        c_medio: Number(c.c_medio ?? 0),
        c_proveedor: Number(c.c_proveedor ?? 0),
        c_monto: Number(c.c_monto ?? 0),
        c_resolucion: Number(c.c_resolucion ?? 0),
      };
    }
    // Si no estuviera en cache (no deberia), cae al scan de abajo.
  }

  // Con filtro de entidad (proveedor/medio): el set es chico, se consulta en vivo.
  const wheres: string[] = [];
  const params: (string | number | null)[] = [];

  if (jurisdiccion) { wheres.push("jurisdiccion = ?"); params.push(jurisdiccion); }
  if (anio)         { wheres.push("anio = ?");          params.push(anio); }
  if (entidadNorm && entidadTipo === "proveedor") {
    wheres.push("proveedor = ?"); params.push(entidadNorm);
  }
  if (entidadNorm && entidadTipo === "medio") {
    wheres.push("medio = ?"); params.push(entidadNorm);
  }

  const where = wheres.length ? `WHERE ${wheres.join(" AND ")}` : "";
  const [row] = await query<{ n: number; total: number; c_medio: number; c_proveedor: number; c_monto: number; c_resolucion: number }>(
    `SELECT COUNT(*) as n, SUM(monto) as total, COUNT(medio) as c_medio, COUNT(proveedor) as c_proveedor, COUNT(monto) as c_monto, COUNT(resolucion) as c_resolucion FROM orders ${where}`,
    params,
  );
  return {
    nOrdenes: Number(row?.n ?? 0),
    montoTotal: Number(row?.total ?? 0),
    c_medio: Number(row?.c_medio ?? 0),
    c_proveedor: Number(row?.c_proveedor ?? 0),
    c_monto: Number(row?.c_monto ?? 0),
    c_resolucion: Number(row?.c_resolucion ?? 0),
  };
}
