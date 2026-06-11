/**
 * search.ts — índice MiniSearch para el buscador de proveedores/medios.
 *
 * Carga search.json (1,54 MB, 21.434 entidades) una sola vez y construye un
 * índice fuzzy/prefix en cliente. Las búsquedas devuelven la clave normalizada
 * (norm) que luego se usa como filtro SQL en getOrdenes/getCuantoRecibio.
 */

import MiniSearch from "minisearch";
import type { TipoEntidad } from "./queries";

export interface EntidadBusqueda {
  id: string;
  norm: string;
  nombre: string;
  n: number;
  tipo: TipoEntidad;
}

/** Un miembro de un grupo mediático (medio o razón social que se suma). */
export interface GrupoMiembro {
  eje: "medio" | "proveedor";
  nombre: string;
  norm: string;
  total: number;
  n: number;
}

/** Un grupo mediático (holding) — proviene de grupos.json (ETL). */
export interface GrupoInfo {
  slug: string;
  nombre: string;
  norm: string;     // = slug; es la clave de lookup en totals_cache (tipo='grupo')
  total: number;
  n: number;
  cubierto: boolean;
  miembros: GrupoMiembro[];
}

let _indexPromise: Promise<MiniSearch<EntidadBusqueda>> | null = null;

export function getSearchIndex(): Promise<MiniSearch<EntidadBusqueda>> {
  if (!_indexPromise) {
    _indexPromise = fetch("/data/search.json")
      .then((r) => {
        if (!r.ok) throw new Error(`search.json: HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        const docs: EntidadBusqueda[] = [
          ...data.proveedores.map((p: EntidadBusqueda) => ({
            id: `p:${p.norm}`,
            norm: p.norm,
            nombre: p.nombre,
            n: p.n,
            tipo: "proveedor" as const,
          })),
          ...data.medios.map((m: EntidadBusqueda) => ({
            id: `m:${m.norm}`,
            norm: m.norm,
            nombre: m.nombre,
            n: m.n,
            tipo: "medio" as const,
          })),
        ];
        const ms = new MiniSearch<EntidadBusqueda>({
          fields: ["nombre"],
          storeFields: ["norm", "nombre", "n", "tipo"],
          searchOptions: { prefix: true, fuzzy: 0.2 },
        });
        ms.addAll(docs);
        return ms;
      })
      .catch((err) => {
        // No cachear el fallo: el próximo buscar() reintenta la descarga.
        _indexPromise = null;
        throw err;
      });
  }
  return _indexPromise!;
}

/** Busca en el índice y devuelve hasta `limite` sugerencias. */
export async function buscar(
  texto: string,
  tipo?: "proveedor" | "medio",
  limite = 8,
): Promise<EntidadBusqueda[]> {
  if (!texto.trim()) return [];
  const idx = await getSearchIndex();
  const resultados = idx.search(texto) as unknown as (EntidadBusqueda & { score: number })[];
  return resultados
    .filter((r) => !tipo || r.tipo === tipo)
    .sort((a, b) => b.score - a.score || b.n - a.n)  // empate de score → más órdenes primero
    .slice(0, limite);
}

// ---------------------------------------------------------------------------
// Grupos mediáticos
// ---------------------------------------------------------------------------
//
// Son ~25 entidades: no van por MiniSearch sino por un filtro lineal sobre
// grupos.json (cargado una sola vez, sólo al usar el modo "Grupo mediático").

let _gruposPromise: Promise<GrupoInfo[]> | null = null;

export function getGrupos(): Promise<GrupoInfo[]> {
  if (!_gruposPromise) {
    _gruposPromise = fetch("/data/grupos.json")
      .then((r) => {
        if (!r.ok) throw new Error(`grupos.json: HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => data.grupos as GrupoInfo[])
      .catch((err) => {
        _gruposPromise = null;
        throw err;
      });
  }
  return _gruposPromise;
}

/** Devuelve un GrupoInfo por su norm (=slug), o null. */
export async function getGrupoPorNorm(norm: string): Promise<GrupoInfo | null> {
  const grupos = await getGrupos();
  return grupos.find((g) => g.norm === norm) ?? null;
}

/** Convierte un GrupoInfo en una EntidadBusqueda (tipo='grupo'). */
function grupoAEntidad(g: GrupoInfo): EntidadBusqueda {
  return { id: `g:${g.norm}`, norm: g.norm, nombre: g.nombre, n: g.n, tipo: "grupo" };
}

/**
 * Busca grupos por nombre del holding O por nombre de cualquiera de sus
 * miembros (filtro lineal, sin acentos): así "telefe" encuentra "Viacom" y
 * "c5n" encuentra "Grupo Indalo". Sin texto devuelve los grupos con datos
 * ordenados por monto, para poblar la lista al abrir el modo.
 */
export async function buscarGrupos(
  texto: string,
  limite = 8,
): Promise<EntidadBusqueda[]> {
  const grupos = await getGrupos();
  const q = norm(texto);
  const filtrados = q
    ? grupos.filter(
        (g) =>
          norm(g.nombre).includes(q) ||
          g.miembros.some((m) => norm(m.nombre).includes(q)),
      )
    : grupos.filter((g) => g.cubierto);
  return filtrados.slice(0, limite).map(grupoAEntidad);
}

/** Normaliza para comparar: minúsculas, sin tildes. */
function norm(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}
