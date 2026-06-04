/**
 * DataTable.tsx — tabla principal de órdenes con filtros y búsqueda.
 *
 * Reemplaza el bloque estático filter-bar + toolbar + table-wrap del index.
 * Se hidrata con client:visible (solo cuando entra en pantalla).
 *
 * Arquitectura:
 *  - Filtros activos se leen/escriben en la URL (url-state.ts).
 *  - getOrdenes() + getTotalesFiltro() traen los datos via sql.js-httpvfs.
 *  - MiniSearch (search.ts) resuelve texto → norm para el filtro SQL.
 *  - TanStack Table maneja columnas y sorting declarativo.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import {
  getOrdenes,
  getTotalesFiltro,
  type Orden,
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
const POR_PAGINA = 100;

const fmtARS = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtNum = new Intl.NumberFormat("es-AR");

function formatMonto(v: number | null): string {
  if (v == null) return "–";
  return `$ ${fmtARS.format(Math.round(v))}`;
}

// ---------------------------------------------------------------------------
// Hook: datos de la tabla
// ---------------------------------------------------------------------------

function useTabla(filtros: FiltrosTabla, seed: SeedTabla | undefined, canSeed: boolean) {
  const sembrar = canSeed && !!seed;
  const [rows, setRows] = useState<Orden[]>(sembrar ? seed!.tabla.filas : []);
  const [totalFilas, setTotalFilas] = useState(sembrar ? seed!.tabla.totalFilas : 0);
  const [totalMonto, setTotalMonto] = useState(sembrar ? seed!.totales.montoTotal : 0);
  const [loading, setLoading] = useState(!sembrar);
  const [pagina, setPagina] = useState(0);
  const [colCounts, setColCounts] = useState(
    sembrar
      ? {
          c_fecha: seed!.totales.c_fecha, c_medio: seed!.totales.c_medio,
          c_proveedor: seed!.totales.c_proveedor, c_monto: seed!.totales.c_monto,
          c_resolucion: seed!.totales.c_resolucion,
        }
      : { c_fecha: 1, c_medio: 1, c_proveedor: 1, c_monto: 1, c_resolucion: 1 },
  );
  const firstLoad = useRef(true);

  const cargar = useCallback(
    async (pag: number) => {
      setLoading(true);
      try {
        const ordenesP = getOrdenes({ ...filtros, pagina: pag, porPagina: POR_PAGINA });
        if (pag === 0) {
          // Solo en la primera pagina pedimos los totales del filtro (conteo,
          // suma y conteos por columna). En "Cargar mas" NO se re-piden: son
          // identicos para todas las paginas del mismo filtro y la query es cara
          // (escanea el set filtrado). Evita duplicar el trabajo al paginar.
          const [{ filas, totalFilas: total }, tots] = await Promise.all([
            ordenesP,
            getTotalesFiltro(filtros),
          ]);
          setRows(filas);
          setTotalFilas(total);
          setTotalMonto(tots.montoTotal);
          setColCounts({
            c_fecha: tots.c_fecha,
            c_medio: tots.c_medio,
            c_proveedor: tots.c_proveedor,
            c_monto: tots.c_monto,
            c_resolucion: tots.c_resolucion,
          });
        } else {
          const { filas } = await ordenesP;
          setRows((prev) => [...prev, ...filas]);
        }
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(filtros)],
  );

  useEffect(() => {
    if (firstLoad.current) {
      firstLoad.current = false;
      if (sembrar) return; // estado inicial servido desde home.json — no se consulta sql.js
    }
    setPagina(0);
    cargar(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargar]);

  const cargarMas = useCallback(() => {
    const sig = pagina + 1;
    setPagina(sig);
    cargar(sig);
  }, [pagina, cargar]);

  return { rows, totalFilas, totalMonto, loading, cargarMas, colCounts };
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
      if (seedMatch) return; // sembrado desde home.json — no se consulta sql.js
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
// Columnas TanStack Table
// ---------------------------------------------------------------------------

const col = createColumnHelper<Orden>();
const columns = [
  col.accessor("id",       { header: "#ID",         enableSorting: true, meta: { align: "right" } }),
  col.accessor("jurisdiccion", { header: "Jurisdicción", cell: (i) => i.getValue() ?? "–" }),
  col.accessor("fecha",    { header: "Fecha",     cell: (i) => i.getValue() ?? "–" }),
  col.accessor("medio",    { header: "Medio",     cell: (i) => i.getValue() ?? "–" }),
  col.accessor("proveedor",{ header: "Proveedor", cell: (i) => i.getValue() ?? "–" }),
  col.accessor("monto_deflactado", {
    header: "Monto (deflactado)",
    cell: (i) => formatMonto(i.getValue()),
    meta: { align: "right" },
  }),
  col.accessor("resolucion", {
    header: "Resol.",
    enableSorting: false,
    cell: (i) => {
      const v = i.getValue();
      if (!v) return "–";
      if (typeof v === "string" && v.startsWith("http")) {
        return <a href={v} target="_blank" rel="noopener" aria-label="Ver resolución oficial">↗</a>;
      }
      return <span title={v} style={{ fontSize: "0.75em", color: "var(--color-fg-muted)" }}>{v}</span>;
    },
    meta: { align: "right" },
  }),
];

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function DataTable({ initial }: { initial?: SeedTabla }) {
  // Estado de filtros (sincronizado con URL)
  const [estado, setEstado] = useState<EstadoTabla>(() => leerEstadoTabla());

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

  const filtros = estadoAFiltros(estado);
  // ¿El estado inicial coincide con el seed de home.json? Si sí, pintamos desde
  // el seed y NO se inicializa sql.js. Si la URL trae filtros distintos
  // (permalink), canSeed=false y se consulta normal. Se evalúa una vez (montaje).
  const canSeed = useRef(
    !!initial &&
      (filtros.jurisdiccion ?? null) === (initial.filtroInicial.jurisdiccion ?? null) &&
      (filtros.anio ?? null) === (initial.filtroInicial.anio ?? null) &&
      !filtros.entidadNorm &&
      (filtros.deflactado ?? true) === initial.filtroInicial.deflactado &&
      (filtros.ordenPor ?? "fecha") === initial.filtroInicial.ordenPor &&
      (filtros.desc ?? false) === initial.filtroInicial.desc,
  ).current;
  const { rows, totalFilas, totalMonto, loading, cargarMas, colCounts } = useTabla(filtros, initial, canSeed);
  const hasNoFilters = !estado.jurisdiccion && !estado.anio && !estado.entidadNorm;
  const seedGob: SeedGob = canSeed && initial
    ? { juris: initial.filtroInicial.jurisdiccion, anio: initial.filtroInicial.anio, value: initial.gobierno }
    : null;
  const gobierno = useGobierno(estado.jurisdiccion, estado.anio, seedGob);

  // Actualiza estado + URL
  const setFiltro = useCallback((patch: Partial<EstadoTabla>) => {
    setEstado((prev) => {
      const next = { ...prev, ...patch };
      escribirEstadoTabla(next);
      return next;
    });
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
    setFiltro({ entidadNorm: e.norm, entidadTipo: e.tipo });
    setTextoBusq(e.nombre);
    setMostrarSugs(false);
  };

  const quitarEntidad = () => {
    setFiltro({ entidadNorm: null });
    setTextoBusq("");
  };

  // TanStack Table — sorting inicial derivado del estado (default: fecha asc).
  const [sorting, setSorting] = useState(() => {
    const id = estado.ordenPor === "monto" ? "monto_deflactado" : estado.ordenPor;
    return [{ id, desc: estado.desc }];
  });
  const table = useReactTable({
    data: rows,
    columns,
    state: { 
      sorting,
      columnVisibility: {
        jurisdiccion: !estado.jurisdiccion,
        fecha: hasNoFilters || colCounts.c_fecha > 0,
        medio: hasNoFilters || colCounts.c_medio > 0,
        proveedor: hasNoFilters || colCounts.c_proveedor > 0,
        monto_deflactado: hasNoFilters || colCounts.c_monto > 0,
        resolucion: hasNoFilters || colCounts.c_resolucion > 0,
      }
    },
    onSortingChange: (upd) => {
      const next = typeof upd === "function" ? upd(sorting) : upd;
      setSorting(next);
      if (next[0]) {
        const op = next[0].id === "fecha" ? "fecha"
                 : next[0].id === "id"    ? "id"
                 : "monto";
        setFiltro({ ordenPor: op, desc: next[0].desc });
      }
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const prevRows = useRef(rows.length);

  useEffect(() => {
    if (rows.length > prevRows.current && prevRows.current >= 100) {
      if (scrollRef.current) {
        // Desplazar suavemente hacia abajo para indicar que cargaron más filas
        scrollRef.current.scrollBy({ top: 400, behavior: "smooth" });
      }
    }
    prevRows.current = rows.length;
  }, [rows.length]);

  const hayMas = rows.length < totalFilas;

  return (
    <>
      {/* ── FILTER BAR ── */}
      <div className="filter-bar">
        <div className="row1">
          <span className="lead">Estás viendo</span>

          {/* Chip jurisdicción activa o select */}
          {estado.jurisdiccion ? (
            <button className="chip-active" aria-label="Quitar Jurisdicción" onClick={() => setFiltro({ jurisdiccion: null })}>
              <span className="label">Jurisdicción:</span>
              <strong>{estado.jurisdiccion}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          ) : (
            <select
              className="chip-add"
              value=""
              onChange={(e) => e.target.value && setFiltro({ jurisdiccion: e.target.value })}
              aria-label="Filtrar por jurisdicción"
            >
              <option value="">+ Jurisdicción</option>
              {jurisFiltradas.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          )}

          {/* Chip año activo o select */}
          {estado.anio ? (
            <button className="chip-active" aria-label="Quitar Año" onClick={() => setFiltro({ anio: null })}>
              <span className="label">Año:</span>
              <strong>{estado.anio}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          ) : (
            <select
              className="chip-add"
              value=""
              onChange={(e) => e.target.value && setFiltro({ anio: Number(e.target.value) })}
              aria-label="Filtrar por año"
            >
              <option value="">+ Año</option>
              {aniosFiltrados.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          )}

          {/* Chip entidad activa */}
          {estado.entidadNorm && (
            <button className="chip-active" aria-label="Quitar Entidad" onClick={quitarEntidad}>
              <span className="label">{estado.entidadTipo === "medio" ? "Medio:" : "Proveedor:"}</span>
              <strong>{textoBusq || estado.entidadNorm}</strong>
              <span className="close" aria-hidden="true">×</span>
            </button>
          )}
        </div>

        <div className="row2">
          <span className="totals">
            <strong>{fmtNum.format(totalFilas)}</strong> órdenes
            {totalMonto > 0 && (
              <> · <strong>$ {fmtARS.format(Math.round(totalMonto))}</strong></>
            )}
          </span>
          <div className="row2-right">
            <a href="#receptores" className="btn-ranking-inline" style={{ display:"inline-flex", alignItems:"center", gap:6, background:"var(--color-bg-elev-2)", border:"1px solid var(--color-border-strong)", padding:"4px 10px", borderRadius:6, color:"var(--color-fg)", fontSize:"var(--text-micro)", textDecoration:"none", fontWeight:600, marginBottom:6, transition:"border-color 150ms ease" }}>
              <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>
              Ver Ranking
            </a>
            <span className="deflation-note">· Montos deflactados con IPC INDEC mensual</span>
            <span className="approx">· Los totales son aproximaciones inferiores: al haber huecos de cobertura, el monto real puede ser mayor.</span>
          </div>
        </div>

        {gobierno && (
          <div className="row3">
            <span className="governance-tag">
              <span className="label">Gestión</span>
              <strong>{gobierno.name}</strong> — {gobierno.role}
            </span>
          </div>
        )}
      </div>

      {/* ── TOOLBAR (búsqueda) ── */}
      <div className="toolbar">
        <div className="search-input-wrap" ref={busqRef} style={{ position: "relative" }}>
          <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            className="search-input"
            type="search"
            placeholder="Buscar proveedor o medio…"
            aria-label="Buscar"
            value={textoBusq}
            onChange={(e) => { setTextoBusq(e.target.value); setMostrarSugs(true); }}
            onFocus={() => setMostrarSugs(true)}
          />
          <span className="search-kbd">/</span>

          {/* Dropdown de sugerencias */}
          {mostrarSugs && sugerencias.length > 0 && (
            <ul role="listbox" style={{ position:"absolute", top:"100%", left:0, right:0, zIndex:50, background:"var(--color-bg-elev-2)", border:"1px solid var(--color-border-strong)", borderRadius:8, marginTop:4, padding:"4px 0", listStyle:"none", boxShadow:"0 8px 32px rgba(0,0,0,.4)" }}>
              {sugerencias.map((s) => (
                <li key={s.id} role="option" aria-selected={estado.entidadNorm === s.norm}
                  onClick={() => elegirEntidad(s)}
                  style={{ padding:"8px 14px", cursor:"pointer", display:"flex", justifyContent:"space-between", fontSize:"var(--text-small)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-elev-3)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                >
                  <span>{s.nombre}</span>
                  <span style={{ color:"var(--color-fg-subtle)", fontSize:"var(--text-micro)", textTransform:"capitalize" }}>{s.tipo}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── TABLA ── */}
      <div className="table-wrap">
        <div className="table-scroll" ref={scrollRef}>
          <table className="data">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => {
                    const meta = header.column.columnDef.meta as { align?: string } | undefined;
                    const isSorted = header.column.getIsSorted();
                    return (
                      <th
                        key={header.id}
                        className={[meta?.align === "right" ? "right" : "", isSorted ? "active" : ""].filter(Boolean).join(" ")}
                        onClick={header.column.getToggleSortingHandler()}
                        style={{ cursor: header.column.getCanSort() ? "pointer" : "default" }}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && (
                          <span className="sort">{isSorted === "asc" ? "▴" : "▾"}</span>
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {loading && rows.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>Cargando datos…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign:"center", padding:"3rem", color:"var(--color-fg-subtle)" }}>No hay resultados para los filtros seleccionados.</td></tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta as { align?: string } | undefined;
                      return (
                        <td key={cell.id} className={[
                          meta?.align === "right" ? "monto" : "",
                          cell.column.id === "resolucion" ? "resol" : "",
                          `col-${cell.column.id}`
                        ].filter(Boolean).join(" ")}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {hayMas && (
          <div style={{ textAlign:"center", padding:"1.5rem 0" }}>
            <button
              className="btn-load-more"
              onClick={cargarMas}
              disabled={loading}
            >
              {loading ? "Cargando…" : `Cargar 100 más (${fmtNum.format(totalFilas - rows.length)} restantes)`}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
