/**
 * queries.ts — las 3 funciones de query de Datos Pauta Oficial.
 *
 * Cada función mapea a una de las 3 vistas de la home:
 *   1. getOrdenes()   → Tabla con filtros
 *   2. getCuantoRecibio() → Generador "Cuánto recibió"
 *   3. getRanking()   → Rankings (contextual y global)
 *
 * Más getMeta() para el hero de datos.
 *
 * Todas usan los índices compuestos definidos en build_db.py:
 *   idx_orders_juris_anio_prov / idx_orders_juris_anio_medio
 *   idx_orders_prov_anio / idx_orders_medio_anio
 */

import { query } from "./db";

// ---------------------------------------------------------------------------
// Tipos compartidos
// ---------------------------------------------------------------------------

export type Orden = {
  id: number;
  fecha: string | null;
  medio: string | null;
  proveedor: string | null;
  monto_deflactado: number | null;
  monto: number | null;
  resolucion: string | null;
  jurisdiccion: string;
  anio: number;
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

export type ResultadoCuantoRecibio = {
  nombre: string;
  norm: string;
  tipo: "proveedor" | "medio";
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
  deflactado?: boolean;
  ordenPor?: "fecha" | "monto" | "id";
  desc?: boolean;
  pagina?: number;
  porPagina?: number;
}

/**
 * Devuelve una página de órdenes aplicando los filtros activos.
 * Si no hay filtros específicos, ordena por monto_deflactado DESC para
 * mostrar las órdenes más significativas primero.
 */
export async function getOrdenes(filtros: FiltrosTabla = {}): Promise<{
  filas: Orden[];
  totalFilas: number;
}> {
  const {
    jurisdiccion,
    anio,
    entidadNorm,
    entidadTipo,
    deflactado = true,
    ordenPor = "monto",
    desc = true,
    pagina = 0,
    porPagina = 100,
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
    wheres.push("proveedor_norm = ?");
    params.push(entidadNorm);
  }
  if (entidadNorm && entidadTipo === "medio") {
    wheres.push("medio_norm = ?");
    params.push(entidadNorm);
  }

  const where = wheres.length ? `WHERE ${wheres.join(" AND ")}` : "";
  const montoCol = deflactado ? "monto_deflactado" : "monto";
  const orden = ordenPor === "fecha"
    ? `fecha ${desc ? "DESC" : "ASC"} NULLS LAST`
    : ordenPor === "id"
    ? `id ${desc ? "DESC" : "ASC"}`
    : `${montoCol} ${desc ? "DESC" : "ASC"} NULLS LAST`;

  // Count total para paginación (usa el mismo WHERE para ser consistente)
  const [{ total }] = await query<{ total: number }>(
    `SELECT COUNT(*) as total FROM orders ${where}`,
    [...params],
  );

  // Filas de la página
  const filas = await query<Orden>(
    `SELECT id, fecha, medio, proveedor, monto, monto_deflactado,
            resolucion, jurisdiccion, anio
     FROM orders ${where}
     ORDER BY ${orden}
     LIMIT ? OFFSET ?`,
    [...params, porPagina, pagina * porPagina],
  );

  return { filas, totalFilas: Number(total) };
}

// ---------------------------------------------------------------------------
// 2. Cuánto recibió
// ---------------------------------------------------------------------------

/**
 * Total recibido por un proveedor o medio, desglosado por año+jurisdicción.
 * Usa idx_orders_prov_anio o idx_orders_medio_anio.
 */
export async function getCuantoRecibio(
  norm: string,
  tipo: "proveedor" | "medio",
  nombreDisplay: string,
): Promise<ResultadoCuantoRecibio> {
  const col = tipo === "proveedor" ? "proveedor_norm" : "medio_norm";

  const porAnio = await query<TotalPorAnioJuris>(
    `SELECT anio, jurisdiccion,
            SUM(monto_deflactado) as total,
            COUNT(*) as n_ordenes
     FROM orders
     WHERE ${col} = ?
     GROUP BY anio, jurisdiccion
     ORDER BY anio DESC`,
    [norm],
  );

  const totalHistorico = porAnio.reduce((acc, r) => acc + (r.total ?? 0), 0);
  const nOrdenesHistorico = porAnio.reduce((acc, r) => acc + (r.n_ordenes ?? 0), 0);

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
  tipo?: "proveedor" | "medio";
  limite?: number;
}

/**
 * Top N proveedores o medios por monto deflactado.
 * Sin filtros → ranking global (toda la base, cacheado en tabla meta).
 * Con jurisdiccion/anio → ranking contextual.
 *
 * Usa idx_orders_juris_anio_prov o idx_orders_juris_anio_medio.
 */
export async function getRanking(filtros: FiltrosRanking = {}): Promise<RankingItem[]> {
  const { jurisdiccion, anio, tipo = "proveedor", limite = 10 } = filtros;

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
 * Se llama una vez al montar el hero; los valores se usan en el count-up.
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
): Promise<{ nOrdenes: number; montoTotal: number }> {
  const { jurisdiccion, anio, entidadNorm, entidadTipo } = filtros;

  const wheres: string[] = [];
  const params: (string | number | null)[] = [];

  if (jurisdiccion) { wheres.push("jurisdiccion = ?"); params.push(jurisdiccion); }
  if (anio)         { wheres.push("anio = ?");          params.push(anio); }
  if (entidadNorm && entidadTipo === "proveedor") {
    wheres.push("proveedor_norm = ?"); params.push(entidadNorm);
  }
  if (entidadNorm && entidadTipo === "medio") {
    wheres.push("medio_norm = ?"); params.push(entidadNorm);
  }

  const where = wheres.length ? `WHERE ${wheres.join(" AND ")}` : "";
  const [row] = await query<{ n: number; total: number }>(
    `SELECT COUNT(*) as n, SUM(monto_deflactado) as total FROM orders ${where}`,
    params,
  );
  return { nOrdenes: Number(row?.n ?? 0), montoTotal: Number(row?.total ?? 0) };
}
