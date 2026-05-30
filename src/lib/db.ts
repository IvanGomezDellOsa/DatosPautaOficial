/**
 * db.ts — singleton de sql.js-httpvfs para Datos Pauta Oficial.
 *
 * Inicializa el worker UNA sola vez (lazy) y lo reutiliza en toda la app.
 * El worker carga la SQLite en modo chunked desde /data/config.json:
 *   6 chunks de 20 MiB, todos bajo el límite de 25 MiB de Cloudflare Pages.
 *
 * Solo usar desde componentes React con directiva client:* en Astro.
 */

import { createDbWorker } from "sql.js-httpvfs";
import type { WorkerHttpvfs } from "sql.js-httpvfs";

// Vite resuelve new URL() en build time y copia los assets al dist/.
// El worker y el WASM necesitan esta forma para quedar incluidos en el bundle.
const workerUrl = new URL(
  "sql.js-httpvfs/dist/sqlite.worker.js",
  import.meta.url,
);
const wasmUrl = new URL(
  "sql.js-httpvfs/dist/sql-wasm.wasm",
  import.meta.url,
);

let _workerPromise: Promise<WorkerHttpvfs> | null = null;

/**
 * Devuelve el worker de sql.js-httpvfs, inicializándolo la primera vez.
 * Las llamadas concurrentes reciben la misma Promise — no se crean workers dobles.
 */
export function getDb(): Promise<WorkerHttpvfs> {
  if (!_workerPromise) {
    _workerPromise = createDbWorker(
      [{ from: "jsonconfig", configUrl: "/data/config.json" }],
      workerUrl.toString(),
      wasmUrl.toString(),
    );
  }
  return _workerPromise;
}

/**
 * Ejecuta una query SQL con parámetros y devuelve las filas como objetos tipados.
 * Wrapper fino sobre worker.db.exec() que aplana el resultado a un array plano.
 *
 * @example
 *   const rows = await query<{ total: number }>(
 *     "SELECT SUM(monto_deflactado) as total FROM orders WHERE proveedor_norm = ?",
 *     ["clarin"]
 *   );
 */
// Comlink envuelve LazyHttpDatabase en un Proxy — exec existe en runtime
// pero TypeScript no lo ve a través de Remote<>. Cast explícito necesario.
type DbExec = {
  exec(
    sql: string,
    params?: (string | number | null)[],
  ): Promise<Array<{ columns: string[]; values: unknown[][] }>>;
};

export async function query<T extends Record<string, unknown>>(
  sql: string,
  params: (string | number | null)[] = [],
): Promise<T[]> {
  const worker = await getDb();
  const db = worker.db as unknown as DbExec;
  const results = await db.exec(sql, params);
  if (!results.length) return [];
  const { columns, values } = results[0];
  return values.map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, row[i]])),
  ) as T[];
}
