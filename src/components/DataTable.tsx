/**
 * DataTable.tsx — tabla principal de órdenes con filtros y búsqueda.
 *
 * Reemplaza el bloque estático filter-bar + toolbar + table-wrap del index.
 * Se monta con client:only="react" (ver index.astro).
 *
 * Arquitectura:
 *  - Filtros activos se leen/escriben en la URL (url-state.ts).
 *  - getOrdenes() + getTotalesFiltro() traen los datos via sql.js-httpvfs.
 *  - MiniSearch (search.ts) resuelve texto → norm para el filtro SQL.
 *
 * Modos de vista:
 *  - Agrupado (default): muestra pares únicos (proveedor+medio) por monto,
 *    expandibles para ver órdenes individuales. Lee de groups_cache.
 *  - Individual: órdenes una a una, paginadas (POR_PAGINA), mostrando TODOS los datos.
 */

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import {
  getOrdenes,
  getDetalleGrupo,
  getTotalesFiltro,
  type Orden,
  type OrdenAgrupada,
  type FiltrosTabla,
} from "../lib/queries";
import {
  leerEstadoTabla,
  escribirEstadoTabla,
  estadoAFiltros,
  type EstadoTabla,
} from "../lib/url-state";
import { buscar, type EntidadBusqueda } from "../lib/search";
import { query } from "../lib/db";
import { useSugerenciasNav } from "../lib/useSugerenciasNav";
import type { SeedTabla } from "../lib/home";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const JURISDICCIONES = ["CABA", "Nación", "PBA", "Santa Fe"];
const ANIOS = Array.from({ length: 23 }, (_, i) => 2025 - i); // 2025..2003
const DISPONIBILIDAD: Record<string, [number, number]> = {
  "Nación": [2009, 2022],
  "CABA": [2003, 2024],
  "PBA": [2020, 2025],
  "Santa Fe": [2008, 2023],
};
const POR_PAGINA = 50;
// Órdenes que se cargan por tanda al expandir un grupo. Pequeño a propósito:
// un grupo grande (cientos de órdenes casi idénticas) cargaría lentísimo de una.
const POR_TANDA_DETALLE = 15;

const fmtARS = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtNum = new Intl.NumberFormat("es-AR");

function formatMonto(v: number | null): string {
  if (v == null) return "–";
  return `$ ${fmtARS.format(Math.round(v))}`;
}

// ---------------------------------------------------------------------------
// Hook: datos agrupados
// ---------------------------------------------------------------------------

/** Seed de la primera página agrupada (de home.json) para el primer paint. */
type SeedAgrupado = { filas: OrdenAgrupada[]; totalFilas: number; totalMonto: number } | null;

function useTabla(filtros: FiltrosTabla, pagina: number, seed: SeedAgrupado) {
  const [rows, setRows] = useState<OrdenAgrupada[]>(() => (seed ? seed.filas : []));
  const [totalFilas, setTotalFilas] = useState(() => (seed ? seed.totalFilas : 0));
  const [totalMonto, setTotalMonto] = useState(() => (seed ? seed.totalMonto : 0));
  const [loading, setLoading] = useState(() => !seed);
  const first = useRef(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [{ filas, totalFilas: total }, tots] = await Promise.all([
        getOrdenes({ ...filtros, agrupado: true, pagina, porPagina: POR_PAGINA }),
        getTotalesFiltro(filtros),
      ]);
      setRows(filas as OrdenAgrupada[]);
      setTotalFilas(Number(total));
      setTotalMonto(tots.montoTotal);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filtros), pagina]);

  // Si la vista inicial coincide con el seed (home.json), no se toca sql.js en
  // el primer render: el primer paint sale del estado sembrado. sql.js recién
  // arranca cuando el usuario cambia filtro/página.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      if (seed) return;
    }
    cargar();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargar]);

  return { rows, totalFilas, totalMonto, loading };
}

// ---------------------------------------------------------------------------
// Hook: datos individuales con paginación
// ---------------------------------------------------------------------------

/**
 * `activo` gatea la carga: este modo está oculto por default y consultarlo en
 * el mount inicializaba sql.js (worker + WASM + chunks) en el primer paint,
 * anulando el seed de home.json. Solo consulta cuando el modo está visible.
 */
function useTablaIndividual(filtros: FiltrosTabla, pagina: number, activo: boolean) {
  const [rows, setRows] = useState<Orden[]>([]);
  const [totalFilas, setTotalFilas] = useState(0);
  const [totalMonto, setTotalMonto] = useState(0);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [{ filas, totalFilas: total }, tots] = await Promise.all([
        getOrdenes({ ...filtros, agrupado: false, pagina, porPagina: POR_PAGINA, ordenPor: "monto", desc: true }),
        getTotalesFiltro(filtros),
      ]);
      setRows(filas as Orden[]);
      setTotalFilas(Number(total));
      setTotalMonto(tots.montoTotal);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filtros), pagina]);

  useEffect(() => {
    if (!activo) return;
    cargar();
  }, [cargar, activo]);

  return { rows, totalFilas, totalMonto, loading };
}

// ---------------------------------------------------------------------------
// Hook: gobierno activo
// ---------------------------------------------------------------------------

type SeedGob =
  | { juris: string | null; anio: number | null; value: { name: string; role: string } | null }
  | null;

function useGobierno(juris: string | null, anio: number | null, seedGob: SeedGob) {
  const seedMatch = !!seedGob && seedGob.juris === juris && seedGob.anio === anio;
  const [gov, setGov] = useState<{ name: string; role: string } | null>(
    () => (seedMatch ? seedGob!.value : null),
  );
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      if (seedMatch) return;
    }
    if (!juris || !anio) { setGov(null); return; }
    query<{ name: string; role: string }>(
      `SELECT name, role FROM governments
       WHERE jurisdiccion = ?
         AND CAST(substr(date_from,1,4) AS INTEGER) <= ?
         AND (date_to IS NULL OR CAST(substr(date_to,1,4) AS INTEGER) >= ?)
       ORDER BY date_from DESC LIMIT 1`,
      [juris, anio, anio],
    ).then((rows) => setGov(rows[0] ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [juris, anio]);
  return gov;
}

// ---------------------------------------------------------------------------
// Helpers para renderizado agrupado
// ---------------------------------------------------------------------------

function groupKey(row: OrdenAgrupada): string {
  return `${row.medio_norm ?? row.medio ?? ""}|${row.proveedor_norm ?? row.proveedor ?? ""}`;
}

/** Estado de un grupo expandido: órdenes cargadas + si hay una tanda en vuelo. */
type DetalleGrupoState = { filas: Orden[]; cargando: boolean };

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function DataTable({ initial }: { initial?: SeedTabla }) {
  // Estado de filtros (sincronizado con URL)
  const [estado, setEstado] = useState<EstadoTabla>(() => leerEstadoTabla());

  // Modo de vista
  const [modoIndividual, setModoIndividual] = useState(false);
  const [paginaIndividual, setPaginaIndividual] = useState(0);
  const [paginaAgrupado, setPaginaAgrupado] = useState(0);

  const jurisFiltradas = estado.anio
    ? JURISDICCIONES.filter((j) => estado.anio! >= DISPONIBILIDAD[j][0] && estado.anio! <= DISPONIBILIDAD[j][1])
    : JURISDICCIONES;

  const aniosFiltrados = estado.jurisdiccion
    ? ANIOS.filter((a) => a >= DISPONIBILIDAD[estado.jurisdiccion!][0] && a <= DISPONIBILIDAD[estado.jurisdiccion!][1])
    : ANIOS;

  // Búsqueda con MiniSearch
  const [textoBusq, setTextoBusq] = useState("");
  const [sugerencias, setSugerencias] = useState<EntidadBusqueda[]>([]);
  const [mostrarSugs, setMostrarSugs] = useState(false);
  const busqRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Atajo "/" → foco en el buscador (el badge del input lo promete)
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, []);

  const filtros = estadoAFiltros(estado);

  // Gobierno activo
  const seedGob: SeedGob = initial
    ? { juris: initial.filtroInicial.jurisdiccion, anio: initial.filtroInicial.anio, value: initial.gobierno }
    : null;
  const gobierno = useGobierno(estado.jurisdiccion, estado.anio, seedGob);

  // Seed del primer paint: solo aplica si la vista inicial es EXACTAMENTE la
  // que precomputó home.json (PBA + año por defecto, agrupado, página 0, sin
  // entidad, deflactado). Si la URL trae otro filtro, se consulta en vivo.
  const seedTabla: SeedAgrupado =
    initial &&
    !modoIndividual &&
    paginaAgrupado === 0 &&
    !estado.entidadNorm &&
    estado.jurisdiccion === initial.filtroInicial.jurisdiccion &&
    estado.anio === initial.filtroInicial.anio &&
    estado.deflactado === initial.filtroInicial.deflactado
      ? {
          // home.json precomputa 100 filas; si POR_PAGINA es menor, recortar
          filas: initial.tabla.filas.slice(0, POR_PAGINA),
          totalFilas: initial.tabla.totalFilas,
          totalMonto: initial.totales.montoTotal,
        }
      : null;

  // Datos agrupados (modo default) — paginado, igual que el individual
  const { rows: rowsAgrupados, totalFilas: totalCombinaciones, totalMonto: totalMontoAgrupado, loading: loadingAgrupado } = useTabla(filtros, paginaAgrupado, seedTabla);

  // Datos individuales (modo individual)
  const { rows: rowsIndividual, totalFilas, totalMonto: totalMontoIndividual, loading: loadingIndividual } = useTablaIndividual(filtros, paginaIndividual, modoIndividual);

  // Detalle expandido: key → { filas cargadas hasta ahora, si está cargando una tanda }
  const [expandedMap, setExpandedMap] = useState<Map<string, DetalleGrupoState>>(new Map());

  // Actualiza estado + URL
  const setFiltro = useCallback((patch: Partial<EstadoTabla>) => {
    setEstado((prev) => {
      const next = { ...prev, ...patch };
      escribirEstadoTabla(next);
      return next;
    });
    setExpandedMap(new Map());
    setPaginaIndividual(0);
    setPaginaAgrupado(0);
  }, []);

  // Al cambiar de página agrupada, colapsar los detalles (las claves expandidas
  // pertenecen a la página anterior).
  useEffect(() => { setExpandedMap(new Map()); }, [paginaAgrupado]);

  // Al cambiar modo, resetear página individual
  const toggleModo = useCallback(() => {
    setModoIndividual((prev) => !prev);
    setPaginaIndividual(0);
    setPaginaAgrupado(0);
    setExpandedMap(new Map());
  }, []);

  // MiniSearch: buscar mientras tipea
  useEffect(() => {
    if (!textoBusq.trim()) { setSugerencias([]); return; }
    buscar(textoBusq).then(setSugerencias);
  }, [textoBusq]);

  // Cerrar sugerencias al hacer click fuera
  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (busqRef.current && !busqRef.current.contains(e.target as Node)) {
        setMostrarSugs(false);
      }
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const elegirEntidad = (e: EntidadBusqueda) => {
    // La tabla sólo busca proveedores/medios (MiniSearch); nunca grupos.
    const entidadTipo = e.tipo === "medio" ? "medio" : "proveedor";
    setFiltro({ entidadNorm: e.norm, entidadTipo });
    setTextoBusq(e.nombre);
    setMostrarSugs(false);
  };

  // Navegación por teclado del dropdown de sugerencias
  const { idx: idxSug, onKeyDown: onKeyDownSugs } = useSugerenciasNav(
    sugerencias.length,
    mostrarSugs,
    (i) => elegirEntidad(sugerencias[i]),
    () => setMostrarSugs(false),
  );

  const quitarEntidad = () => {
    setFiltro({ entidadNorm: null });
    setTextoBusq("");
  };

  // Carga una tanda de órdenes del grupo (la primera al expandir, o las
  // siguientes al tocar "ver más"). Acumula sobre lo ya cargado.
  const cargarTandaDetalle = useCallback((row: OrdenAgrupada, key: string, offset: number) => {
    getDetalleGrupo(
      row.medio_norm, row.proveedor_norm,
      { jurisdiccion: filtros.jurisdiccion, anio: filtros.anio },
      POR_TANDA_DETALLE, offset,
    ).then((nuevas) => {
      setExpandedMap((p) => {
        const cur = p.get(key);
        if (!cur) return p; // se colapsó mientras cargaba
        const n = new Map(p);
        // offset 0 = primera tanda (reemplaza); resto = append
        n.set(key, { filas: offset === 0 ? nuevas : [...cur.filas, ...nuevas], cargando: false });
        return n;
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros.jurisdiccion, filtros.anio]);

  // Toggle expandir/colapsar grupo (modo agrupado). Lee expandedMap del closure
  // (está en deps) para decidir SINCRÓNICAMENTE si abrir y disparar el fetch —
  // no se puede usar una flag seteada dentro del updater de setState porque ese
  // updater corre diferido (la flag seguiría en false al lanzar la tanda).
  const toggleGrupo = useCallback((row: OrdenAgrupada) => {
    const key = groupKey(row);
    if (expandedMap.has(key)) {
      setExpandedMap((prev) => { const n = new Map(prev); n.delete(key); return n; });
    } else {
      setExpandedMap((prev) => { const n = new Map(prev); n.set(key, { filas: [], cargando: true }); return n; });
      cargarTandaDetalle(row, key, 0);
    }
  }, [expandedMap, cargarTandaDetalle]);

  // "Ver más": carga la siguiente tanda a partir de lo ya mostrado.
  const verMasDetalle = useCallback((row: OrdenAgrupada) => {
    const key = groupKey(row);
    const cur = expandedMap.get(key);
    if (!cur || cur.cargando) return; // ya cargando o colapsado
    const offset = cur.filas.length;
    setExpandedMap((prev) => {
      const c = prev.get(key);
      if (!c) return prev;
      const n = new Map(prev);
      n.set(key, { ...c, cargando: true });
      return n;
    });
    cargarTandaDetalle(row, key, offset);
  }, [expandedMap, cargarTandaDetalle]);

  // Paginación — unificada para ambos modos (individual y agrupado).
  const loading = modoIndividual ? loadingIndividual : loadingAgrupado;
  const totalMonto = modoIndividual ? totalMontoIndividual : totalMontoAgrupado;
  // Registros totales del modo activo: órdenes (individual) o combinaciones (agrupado).
  const totalRegistros = modoIndividual ? totalFilas : totalCombinaciones;
  const totalPaginas = Math.max(1, Math.ceil(totalRegistros / POR_PAGINA));
  const paginaActual = modoIndividual ? paginaIndividual : paginaAgrupado;
  const setPaginaActual = modoIndividual ? setPaginaIndividual : setPaginaAgrupado;

  // Solo se permite expandir un grupo cuando hay jurisdicción Y año: ese es el
  // caso que resuelve el covering index idx_orders_juris_anio_medio_prov (lookup
  // rápido, sin temp B-tree). Sin ambos filtros, el detalle de un grupo cruzaría
  // todas las jurisdicciones/años -> escaneo lento + datos redundantes; se guía
  // al usuario a filtrar primero en vez de bajar miles de filas dispersas.
  const puedeExpandir = estado.jurisdiccion != null && estado.anio != null;

  // Columnas visibles de cada modo (jurisdicción/año se ocultan según filtros)
  const colsIndividual = 5 + (estado.jurisdiccion ? 0 : 1) + (estado.anio ? 0 : 1);
  const colsAgrupado = 4 + (estado.jurisdiccion ? 0 : 1);

  return (
    <>
      {/* ── FILTER BAR ── */}
      <div className="filter-bar">
        <div className="row1">
          <span className="lead">Estás viendo</span>

          {estado.jurisdiccion ? (
            <button className="chip-active" aria-label="Quitar Jurisdicción" onClick={() => setFiltro({ jurisdiccion: null })}>
              <span className="label">Jurisdicción:</span>
              <strong>{estado.jurisdiccion}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          ) : (
            <select className="chip-add" value="" onChange={(e) => e.target.value && setFiltro({ jurisdiccion: e.target.value })} aria-label="Filtrar por jurisdicción">
              <option value="">+ Jurisdicción</option>
              {jurisFiltradas.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          )}

          {estado.anio ? (
            <button className="chip-active" aria-label="Quitar Año" onClick={() => setFiltro({ anio: null })}>
              <span className="label">Año:</span>
              <strong>{estado.anio}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          ) : (
            <select className="chip-add" value="" onChange={(e) => e.target.value && setFiltro({ anio: Number(e.target.value) })} aria-label="Filtrar por año">
              <option value="">+ Año</option>
              {aniosFiltrados.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          )}

          {estado.entidadNorm && (
            <button className="chip-active" aria-label="Quitar Entidad" onClick={quitarEntidad}>
              <span className="label">{estado.entidadTipo === "medio" ? "Medio:" : "Proveedor:"}</span>
              <strong>{textoBusq || estado.entidadNorm}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          )}
        </div>

        {gobierno && (
          <div className="row3">
            <span className="governance-tag">
              <span className="label">Gestión</span>
              <strong>{gobierno.name}</strong> — {gobierno.role}
            </span>
          </div>
        )}

        <div className="row2">
          <span className="totals">
            {modoIndividual ? (
              <>
                <strong>{fmtNum.format(totalFilas)}</strong> órdenes
              </>
            ) : (
              <>
                <strong>{fmtNum.format(totalCombinaciones)}</strong> combinaciones
              </>
            )}
            {totalMonto > 0 && (
              <> · <strong>$ {fmtARS.format(Math.round(totalMonto))}</strong></>
            )}
          </span>
          <div className="row2-right">
            <a href="#receptores" className="btn-secondary btn-ranking-inline">
              <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
              Ver Ranking
            </a>
            <span className="deflation-note">· Montos deflactados con IPC INDEC mensual</span>
            <span className="approx">· Los totales son aproximaciones inferiores: al haber huecos de cobertura, el monto real puede ser mayor.</span>
          </div>
        </div>
      </div>

      {/* ── TOOLBAR (búsqueda + toggle de modo) ── */}
      <div className="toolbar">
        <div className="search-input-wrap" ref={busqRef} style={{ position: "relative" }}>
          <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            ref={inputRef}
            className="search-input"
            type="search"
            placeholder="Buscar proveedor o medio…"
            aria-label="Buscar"
            aria-autocomplete="list"
            aria-controls="sugs-tabla"
            aria-activedescendant={idxSug >= 0 ? `sug-tabla-${idxSug}` : undefined}
            value={textoBusq}
            onChange={(e) => { setTextoBusq(e.target.value); setMostrarSugs(true); }}
            onFocus={() => setMostrarSugs(true)}
            onKeyDown={onKeyDownSugs}
          />
          <span className="search-kbd" aria-hidden="true">/</span>

          {mostrarSugs && sugerencias.length > 0 && (
            <ul role="listbox" id="sugs-tabla" className="suggest-list">
              {sugerencias.map((s, i) => (
                <li key={s.id} id={`sug-tabla-${i}`} role="option" aria-selected={estado.entidadNorm === s.norm}
                  className={i === idxSug ? "suggest-item activo" : "suggest-item"}
                  onClick={() => elegirEntidad(s)}
                >
                  <span>{s.nombre}</span>
                  <span className="meta" style={{ textTransform: "capitalize" }}>{s.tipo}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Toggle agrupado / individual */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={toggleModo}
            title={modoIndividual ? "Ver combinaciones agrupadas por proveedor+medio" : "Ver todas las órdenes individuales con paginación"}
          >
            {modoIndividual ? (
              <>
                <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                Ver agrupado
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                Ver todas las órdenes
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── TABLA ── */}
      <div className="table-wrap">
        <div className="table-scroll">
          {modoIndividual ? (
            /* ── MODO INDIVIDUAL ── */
            <table className="data">
              <thead>
                <tr>
                  <th className="col-id" style={{ color: "var(--color-fg-subtle)", fontWeight: 400 }}>#</th>
                  {!estado.jurisdiccion && <th className="col-juris">Jurisdicción</th>}
                  {!estado.anio && <th className="col-anio">Año</th>}
                  <th className="col-proveedor">Proveedor</th>
                  <th className="col-medio">Medio</th>
                  <th className="col-resol">Resolución</th>
                  <th className="col-monto right">Monto (deflactado)</th>
                </tr>
              </thead>
              <tbody>
                {loadingIndividual ? (
                  <tr className="row-msg"><td colSpan={colsIndividual} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>Cargando datos…</td></tr>
                ) : rowsIndividual.length === 0 ? (
                  <tr className="row-msg"><td colSpan={colsIndividual} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>No hay resultados para los filtros seleccionados.</td></tr>
                ) : (
                  rowsIndividual.map((orden) => (
                    <tr key={orden.id} className="row-orden">
                      <td className="col-id" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)" }}>#{orden.id}</td>
                      {!estado.jurisdiccion && <td className="col-juris" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>{orden.jurisdiccion}</td>}
                      {!estado.anio && <td className="col-anio" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>{orden.anio}</td>}
                      <td className="col-proveedor">{orden.proveedor ?? "–"}</td>
                      <td className="col-medio">{orden.medio ?? "–"}</td>
                      <td className="col-resol" style={{ fontSize: "var(--text-small)" }}>
                        {orden.resolucion ? (
                          orden.resolucion.startsWith("http")
                            ? <a href={orden.resolucion} target="_blank" rel="noopener" aria-label="Ver resolución oficial">↗ Resolución</a>
                            : orden.resolucion
                        ) : "–"}
                      </td>
                      <td className="col-monto monto">{formatMonto(orden.monto)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          ) : (
            /* ── MODO AGRUPADO ── */
            <>
            {!puedeExpandir && rowsAgrupados.length > 0 && (
              <p style={{ margin: 0, padding: "0.75rem 1rem", color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)" }}>
                Filtrá por jurisdicción y año para poder ver las órdenes individuales de cada grupo.
              </p>
            )}
            <table className="data">
              <thead>
                <tr>
                  <th className="col-expand" aria-label="Expandir" />
                  {!estado.jurisdiccion && <th className="col-juris">Jurisdicción</th>}
                  <th className="col-proveedor">Proveedor</th>
                  <th className="col-medio">Medio</th>
                  <th className="col-monto right">Monto (deflactado)</th>
                </tr>
              </thead>
              <tbody>
                {loadingAgrupado ? (
                  <tr className="row-msg"><td colSpan={colsAgrupado} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>Cargando datos…</td></tr>
                ) : rowsAgrupados.length === 0 ? (
                  <tr className="row-msg"><td colSpan={colsAgrupado} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>No hay resultados para los filtros seleccionados.</td></tr>
                ) : (
                  rowsAgrupados.map((row) => {
                    const key = groupKey(row);
                    const detalle = expandedMap.get(key);
                    const isExpanded = detalle !== undefined;
                    const cargandoPrimera = detalle?.cargando && detalle.filas.length === 0;
                    const hayMas = isExpanded && detalle.filas.length < row.n;
                    return (
                      <Fragment key={key}>
                        {/* Fila agrupada */}
                        <tr
                          className="row-grupo"
                          onClick={puedeExpandir ? () => toggleGrupo(row) : undefined}
                          style={{ cursor: puedeExpandir ? "pointer" : "default" }}
                          title={puedeExpandir ? undefined : "Filtrá por jurisdicción y año para ver las órdenes individuales"}
                        >
                          <td className="col-expand" style={{ textAlign: "center" }}>
                            {puedeExpandir && (
                              <button
                                type="button"
                                className="expand-btn"
                                aria-expanded={isExpanded}
                                aria-label={isExpanded ? "Ocultar órdenes del grupo" : "Ver órdenes del grupo"}
                                onClick={(e) => { e.stopPropagation(); toggleGrupo(row); }}
                              >
                                {isExpanded ? "▾" : "▸"}
                              </button>
                            )}
                          </td>
                          {!estado.jurisdiccion && <td className="col-juris" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>—</td>}
                          <td className="col-proveedor">{row.proveedor ?? row.proveedor_norm ?? "–"}</td>
                          <td className="col-medio">{row.medio ?? row.medio_norm ?? "–"}</td>
                          <td className="col-monto monto">
                            <span style={{ marginRight: 8, color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)", fontWeight: 400 }}>
                              {fmtNum.format(row.n)} órdenes
                            </span>
                            {formatMonto(row.total)}
                          </td>
                        </tr>

                        {/* Filas hijas */}
                        {cargandoPrimera && (
                          <tr className="row-msg" style={{ background: "var(--color-bg-elev-2)" }}>
                            <td colSpan={colsAgrupado} style={{ padding: "0.5rem 1rem 0.5rem 2.5rem", color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>
                              Cargando órdenes…
                            </td>
                          </tr>
                        )}
                        {isExpanded && detalle.filas.map((orden) => (
                          <tr key={`${key}-${orden.id}`} className="row-detalle" style={{ background: "var(--color-bg-elev-2)" }}>
                            <td className="col-id" style={{ paddingLeft: "1.5rem", color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)" }}>#{orden.id}</td>
                            {!estado.jurisdiccion && <td className="col-juris" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>{orden.jurisdiccion}</td>}
                            <td className="col-anio" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>{orden.anio}</td>
                            <td className="col-resol" style={{ color: "var(--color-fg-subtle)", fontSize: "var(--text-small)" }}>{orden.resolucion ? (
                              orden.resolucion.startsWith("http")
                                ? <a href={orden.resolucion} target="_blank" rel="noopener" aria-label="Ver resolución oficial">↗ {orden.anio}</a>
                                : orden.resolucion
                            ) : "–"}</td>
                            <td className="col-monto monto" style={{ color: "var(--color-fg-subtle)" }}>
                              {formatMonto(orden.monto)}
                            </td>
                          </tr>
                        ))}

                        {/* Footer "ver más": carga la siguiente tanda sin traer todo de golpe */}
                        {isExpanded && detalle.filas.length > 0 && hayMas && (
                          <tr className="row-vermas" style={{ background: "var(--color-bg-elev-2)" }}>
                            <td colSpan={colsAgrupado} style={{ padding: "0.4rem 1rem 0.6rem 2.5rem" }}>
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={(e) => { e.stopPropagation(); verMasDetalle(row); }}
                                disabled={detalle.cargando}
                              >
                                {detalle.cargando
                                  ? "Cargando…"
                                  : `Ver ${Math.min(POR_TANDA_DETALLE, row.n - detalle.filas.length)} más`}
                              </button>
                              <span style={{ marginLeft: 10, color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)" }}>
                                mostrando {fmtNum.format(detalle.filas.length)} de {fmtNum.format(row.n)}
                              </span>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
            </>
          )}
        </div>
      </div>

      {/* ── PAGINACIÓN (individual y agrupado) ── */}
      {totalRegistros > POR_PAGINA && (
        <div className="pagination">
          <button
            type="button"
            className="btn-page"
            onClick={() => setPaginaActual(0)}
            disabled={paginaActual === 0 || loading}
            aria-label="Primera página"
          >«</button>
          <button
            type="button"
            className="btn-page"
            onClick={() => setPaginaActual((p) => Math.max(0, p - 1))}
            disabled={paginaActual === 0 || loading}
            aria-label="Página anterior"
          >‹</button>
          <span className="info">
            Página <strong>{paginaActual + 1}</strong> de <strong>{totalPaginas}</strong>
            {" "}· <strong>{fmtNum.format(totalRegistros)}</strong>{" "}
            {modoIndividual ? "órdenes" : "combinaciones"} en total
          </span>
          <button
            type="button"
            className="btn-page"
            onClick={() => setPaginaActual((p) => Math.min(totalPaginas - 1, p + 1))}
            disabled={paginaActual >= totalPaginas - 1 || loading}
            aria-label="Página siguiente"
          >›</button>
          <button
            type="button"
            className="btn-page"
            onClick={() => setPaginaActual(totalPaginas - 1)}
            disabled={paginaActual >= totalPaginas - 1 || loading}
            aria-label="Última página"
          >»</button>
        </div>
      )}
    </>
  );
}
