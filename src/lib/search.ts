/**
 * search.ts — índice MiniSearch para el buscador de proveedores/medios.
 *
 * Carga search.json (1,54 MB, 21.434 entidades) una sola vez y construye un
 * índice fuzzy/prefix en cliente. Las búsquedas devuelven la clave normalizada
 * (norm) que luego se usa como filtro SQL en getOrdenes/getCuantoRecibio.
 */

import MiniSearch from "minisearch";

export interface EntidadBusqueda {
  id: string;
  norm: string;
  nombre: string;
  n: number;
  tipo: "proveedor" | "medio";
}

let _indexPromise: Promise<MiniSearch<EntidadBusqueda>> | null = null;

export function getSearchIndex(): Promise<MiniSearch<EntidadBusqueda>> {
  if (!_indexPromise) {
    _indexPromise = fetch("/data/search.json")
      .then((r) => r.json())
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
    .slice(0, limite);
}
