/**
 * url-state.ts — sincroniza el estado de filtros con la URL.
 *
 * Cada estado de la app tiene su representación en query params, lo que
 * permite compartir y guardar vistas específicas (permalinks).
 *
 * Parámetros soportados:
 *   Tabla:      juris, anio, norm, tipo
 *   Generador:  p (norm), modo (proveedor|medio|grupo), y (anio|historico)
 */

import type { FiltrosTabla, TipoEntidad } from "./queries";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface EstadoTabla {
  jurisdiccion: string | null;
  anio: number | null;
  entidadNorm: string | null;
  entidadTipo: "proveedor" | "medio";
}

/**
 * Vista por defecto cuando la URL no trae params. Los islands deben pasar el
 * default real desde home.json (filtroInicial, calculado por el ETL como la
 * jurisdicción seed + su año más reciente con datos) para que la vista
 * inicial, el seed del primer paint y la URL "limpia" siempre coincidan.
 * Este fallback hardcodeado solo aplica si un island se monta sin seed.
 */
export interface DefaultsTabla {
  jurisdiccion: string;
  anio: number;
}

export const DEFAULTS_TABLA: DefaultsTabla = { jurisdiccion: "PBA", anio: 2025 };

export interface EstadoGenerador {
  norm: string | null;
  tipo: TipoEntidad;
  /** número de año, o "historico" */
  anio: number | "historico";
}

// ---------------------------------------------------------------------------
// Lectura
// ---------------------------------------------------------------------------

/** Lee el estado de la tabla desde la URL actual (window.location.search). */
export function leerEstadoTabla(defaults: DefaultsTabla = DEFAULTS_TABLA): EstadoTabla {
  const p = new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : "",
  );
  // Si la URL trae el param, prevalece; si no, se usa el default (que viene
  // de home.json). Para "sin filtro" (todas las jurisdicciones / todos los
  // años), la URL debe traer juris=todas o anio=todos.
  const jurisParam = p.get("juris");
  const anioParam  = p.get("anio");
  // anio no numérico en la URL (?anio=abc) → NaN rompería el seed y los
  // selects de disponibilidad; se cae al default.
  const anioNum = anioParam != null ? Number(anioParam) : NaN;
  return {
    jurisdiccion: jurisParam === "todas" ? null : (jurisParam ?? defaults.jurisdiccion),
    anio:         anioParam  === "todos" ? null : (Number.isInteger(anioNum) ? anioNum : defaults.anio),
    entidadNorm: p.get("norm"),
    entidadTipo: p.get("tipo") === "medio" ? "medio" : "proveedor",
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
  const modo = p.get("modo");
  return {
    norm: p.get("p"),
    tipo: modo === "medio" ? "medio" : modo === "grupo" ? "grupo" : "proveedor",
    anio,
  };
}

// ---------------------------------------------------------------------------
// Escritura
// ---------------------------------------------------------------------------

/**
 * Actualiza la URL con el nuevo estado de tabla SIN recargar la página.
 * Solo escribe los parámetros que difieren del default para mantener las
 * URLs limpias.
 */
export function escribirEstadoTabla(
  estado: Partial<EstadoTabla>,
  defaults: DefaultsTabla = DEFAULTS_TABLA,
): void {
  if (typeof window === "undefined") return;
  const p = new URLSearchParams(window.location.search);

  // juris: el default → no se escribe. null → "todas" (param explícito).
  const jurisVal = estado.jurisdiccion === undefined ? undefined
                 : estado.jurisdiccion === null                  ? "todas"
                 : estado.jurisdiccion === defaults.jurisdiccion ? null   // default, no escribir
                 : estado.jurisdiccion;
  setOrDel(p, "juris", jurisVal ?? null);
  // anio: el default → no se escribe. null → "todos" (param explícito).
  const anioVal = estado.anio === undefined ? undefined
                : estado.anio === null          ? "todos"
                : estado.anio === defaults.anio ? null   // default, no escribir
                : String(estado.anio);
  setOrDel(p, "anio", anioVal ?? null);
  setOrDel(p, "norm", estado.entidadNorm ?? null);
  setOrDel(p, "tipo", estado.entidadTipo === "medio" ? "medio" : null); // proveedor es default
  // Params legacy que ya no hacen nada (def/orden/desc): se limpian de la URL
  // para que los permalinks viejos no prometan un estado que no existe.
  p.delete("def");
  p.delete("orden");
  p.delete("desc");

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
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Construye la URL del generador para compartir (deeplink). */
export function urlGenerador(estado: EstadoGenerador): string {
  const p = new URLSearchParams();
  if (estado.norm) p.set("p", estado.norm);
  if (estado.tipo && estado.tipo !== "proveedor") p.set("modo", estado.tipo);
  if (estado.anio !== "historico") p.set("y", String(estado.anio));
  // El hash lleva al receptor directo a la sección "Cuánto recibió".
  return `https://datospautaoficial.com.ar/?${p.toString()}#cuanto-recibio`;
}

function setOrDel(p: URLSearchParams, key: string, val: string | null): void {
  if (val !== null) {
    p.set(key, val);
  } else {
    p.delete(key);
  }
}
