/**
 * home.ts — tipo del estado inicial precomputado (public/data/home.json).
 *
 * home.json lo genera el ETL (build_db.py → escribir_home). Contiene TODO lo que
 * la portada muestra con los filtros por defecto (PBA 2025, orden por fecha asc),
 * ya resuelto. Astro lo inlinea como prop de los islands para que el primer paint
 * no dispare sql.js-httpvfs: cero WASM, cero worker, cero round-trips a la DB.
 * sql.js recién se inicializa cuando el usuario cambia un filtro, busca u ordena.
 *
 * Si cambian las queries del front o el filtro por defecto, regenerar home.json.
 */

import type { OrdenAgrupada, RankingItem, ResultadoCuantoRecibio } from "./queries";
import type { EntidadBusqueda } from "./search";

export interface HomeFiltroInicial {
  jurisdiccion: string;
  anio: number;
  ordenPor: "monto" | "id";
  desc: boolean;
  deflactado: boolean;
  entidadTipo: "proveedor" | "medio";
}

export interface HomeTotales {
  nOrdenes: number;
  montoTotal: number;
  c_medio: number;
  c_proveedor: number;
  c_monto: number;
  c_resolucion: number;
}

export interface HomeSeed {
  filtroInicial: HomeFiltroInicial;
  // Primera página del modo AGRUPADO (default): combinaciones (medio, proveedor).
  tabla: { filas: OrdenAgrupada[]; totalFilas: number };
  totales: HomeTotales;
  gobierno: { name: string; role: string } | null;
  rankingContextual: { proveedor: RankingItem[]; medio: RankingItem[]; grupo: RankingItem[] };
  rankingGlobal: { proveedor: RankingItem[]; medio: RankingItem[]; grupo: RankingItem[] };
  generadorDemo: { entidad: EntidadBusqueda; resultado: ResultadoCuantoRecibio } | null;
}

/** Slice que recibe DataTable. */
export interface SeedTabla {
  filtroInicial: HomeFiltroInicial;
  tabla: HomeSeed["tabla"];
  totales: HomeTotales;
  gobierno: HomeSeed["gobierno"];
}

/** Slice que recibe Rankings. */
export interface SeedRankings {
  filtroInicial: HomeFiltroInicial;
  rankingContextual: HomeSeed["rankingContextual"];
  rankingGlobal: HomeSeed["rankingGlobal"];
}
