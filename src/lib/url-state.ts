/**
 * url-state.ts — sincroniza el estado de filtros con la URL.
 *
 * Cada estado de la app tiene su representación en query params, lo que
 * permite compartir y guardar vistas específicas (permalinks).
 *
 * Parámetros soportados:
 *   Tabla:      juris, anio, norm, tipo, def, orden, desc
 *   Generador:  p (norm), modo (proveedor|medio), y (anio|historico)
 */

import type { FiltrosTabla } from "./queries";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface EstadoTabla {
  jurisdiccion: string | null;
  anio: number | null;
  entidadNorm: string | null;
  entidadTipo: "proveedor" | "medio";
  deflactado: boolean;
  ordenPor: "fecha" | "monto";
  desc: boolean;
}

export interface EstadoGenerador {
  norm: string | null;
  tipo: "proveedor" | "medio";
  /** número de año, o "historico" */
  anio: number | "historico";
}

// ---------------------------------------------------------------------------
// Lectura
// ---------------------------------------------------------------------------

/** Lee el estado de la tabla desde la URL actual (window.location.search). */
export function leerEstadoTabla(): EstadoTabla {
  const p = new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : "",
  );
  return {
    jurisdiccion: p.get("juris"),
    anio: p.has("anio") ? Number(p.get("anio")) : null,
    entidadNorm: p.get("norm"),
    entidadTipo: p.get("tipo") === "medio" ? "medio" : "proveedor",
    deflactado: p.get("def") !== "0",
    ordenPor: p.get("orden") === "fecha" ? "fecha" : "monto",
    desc: p.get("desc") !== "0",
  };
}

/** Lee el estado del generador desde la URL actual. */
export function leerEstadoGenerador(): EstadoGenerador {
  const p = new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : "",
  );
  const yRaw = p.get("y");
  const anio = yRaw && yRaw !== "historico" && !isNaN(Number(yRaw))
    ? Number(yRaw)
    : "historico";
  return {
    norm: p.get("p"),
    tipo: p.get("modo") === "medio" ? "medio" : "proveedor",
    anio,
  };
}

// ---------------------------------------------------------------------------
// Escritura
// ---------------------------------------------------------------------------

/**
 * Actualiza la URL con el nuevo estado de tabla SIN recargar la página.
 * Solo escribe los parámetros que difieren del default para mantener las
 * URLs limpias (ej: sin `def=1` cuando el default ya es deflactado=true).
 */
export function escribirEstadoTabla(estado: Partial<EstadoTabla>): void {
  if (typeof window === "undefined") return;
  const p = new URLSearchParams(window.location.search);

  setOrDel(p, "juris", estado.jurisdiccion ?? null);
  setOrDel(p, "anio", estado.anio != null ? String(estado.anio) : null);
  setOrDel(p, "norm", estado.entidadNorm ?? null);
  setOrDel(p, "tipo", estado.entidadTipo === "medio" ? "medio" : null); // proveedor es default
  setOrDel(p, "def", estado.deflactado === false ? "0" : null);         // deflactado es default
  setOrDel(p, "orden", estado.ordenPor === "fecha" ? "fecha" : null);   // monto es default
  setOrDel(p, "desc", estado.desc === false ? "0" : null);              // desc es default

  const search = p.toString();
  const url = search ? `?${search}` : window.location.pathname;
  window.history.replaceState(null, "", url);
}

/** Actualiza la URL del generador. */
export function escribirEstadoGenerador(estado: Partial<EstadoGenerador>): void {
  if (typeof window === "undefined") return;
  const p = new URLSearchParams(window.location.search);

  setOrDel(p, "p", estado.norm ?? null);
  setOrDel(p, "modo", estado.tipo === "medio" ? "medio" : null); // proveedor es default
  setOrDel(p, "y",
    estado.anio != null && estado.anio !== "historico"
      ? String(estado.anio)
      : null,
  );

  const search = p.toString();
  const url = search ? `?${search}` : window.location.pathname;
  window.history.replaceState(null, "", url);
}

// ---------------------------------------------------------------------------
// Conversión a FiltrosTabla (para pasarle a queries.ts)
// ---------------------------------------------------------------------------

export function estadoAFiltros(estado: EstadoTabla): FiltrosTabla {
  return {
    jurisdiccion: estado.jurisdiccion ?? undefined,
    anio: estado.anio ?? undefined,
    entidadNorm: estado.entidadNorm ?? undefined,
    entidadTipo: estado.entidadTipo,
    deflactado: estado.deflactado,
    ordenPor: estado.ordenPor,
    desc: estado.desc,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Construye la URL del generador para compartir (deeplink). */
export function urlGenerador(estado: EstadoGenerador): string {
  const p = new URLSearchParams();
  if (estado.norm) p.set("p", estado.norm);
  if (estado.tipo === "medio") p.set("modo", "medio");
  if (estado.anio !== "historico") p.set("y", String(estado.anio));
  const base =
    typeof window !== "undefined"
      ? `${window.location.origin}/`
      : "https://datospautaoficial.com.ar/";
  return `${base}?${p.toString()}`;
}

function setOrDel(p: URLSearchParams, key: string, val: string | null): void {
  if (val !== null) {
    p.set(key, val);
  } else {
    p.delete(key);
  }
}
