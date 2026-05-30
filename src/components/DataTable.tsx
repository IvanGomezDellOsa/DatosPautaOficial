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

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const JURISDICCIONES = ["CABA", "Nación", "PBA", "Santa Fe"];
const ANIOS = Array.from({ length: 23 }, (_, i) => 2025 - i); // 2025..2003
const POR_PAGINA = 100;

const fmtARS = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat("es-AR");

function formatMonto(v: number | null): string {
  if (v == null) return "–";
  return `$ ${fmtARS.format(Math.round(v))}`;
}

// ---------------------------------------------------------------------------
// Hook: datos de la tabla
// ---------------------------------------------------------------------------

function useTabla(filtros: FiltrosTabla) {
  const [rows, setRows] = useState<Orden[]>([]);
  const [totalFilas, setTotalFilas] = useState(0);
  const [totalMonto, setTotalMonto] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pagina, setPagina] = useState(0);

  const cargar = useCallback(
    async (pag: number) => {
      setLoading(true);
      try {
        const [{ filas, totalFilas: total }, tots] = await Promise.all([
          getOrdenes({ ...filtros, pagina: pag, porPagina: POR_PAGINA }),
          getTotalesFiltro(filtros),
        ]);
        setRows((prev) => (pag === 0 ? filas : [...prev, ...filas]));
        setTotalFilas(total);
        setTotalMonto(tots.montoTotal);
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(filtros)],
  );

  useEffect(() => {
    setPagina(0);
    cargar(0);
  }, [cargar]);

  const cargarMas = useCallback(() => {
    const sig = pagina + 1;
    setPagina(sig);
    cargar(sig);
  }, [pagina, cargar]);

  return { rows, totalFilas, totalMonto, loading, cargarMas };
}

// ---------------------------------------------------------------------------
// Hook: gobierno activo
// ---------------------------------------------------------------------------

function useGobierno(juris: string | null, anio: number | null) {
  const [gov, setGov] = useState<{ name: string; role: string } | null>(null);
  useEffect(() => {
    if (!juris || !anio) { setGov(null); return; }
    query<{ name: string; role: string }>(
      `SELECT name, role FROM governments
       WHERE jurisdiccion = ?
         AND CAST(substr(date_from,1,4) AS INTEGER) <= ?
         AND (date_to IS NULL OR CAST(substr(date_to,1,4) AS INTEGER) >= ?)
       ORDER BY date_from DESC LIMIT 1`,
      [juris, anio, anio],
    ).then((rows) => setGov(rows[0] ?? null));
  }, [juris, anio]);
  return gov;
}

// ---------------------------------------------------------------------------
// Columnas TanStack Table
// ---------------------------------------------------------------------------

const col = createColumnHelper<Orden>();
const columns = [
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
      return v ? (
        <a href={v} target="_blank" rel="noopener" aria-label="Ver resolución oficial">↗</a>
      ) : "–";
    },
    meta: { align: "right" },
  }),
];

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function DataTable() {
  // Estado de filtros (sincronizado con URL)
  const [estado, setEstado] = useState<EstadoTabla>(() => leerEstadoTabla());

  // Búsqueda con MiniSearch
  const [textoBusq, setTextoBusq] = useState("");
  const [sugerencias, setSugerencias] = useState<EntidadBusqueda[]>([]);
  const [mostrarSugs, setMostrarSugs] = useState(false);
  const busqRef = useRef<HTMLDivElement>(null);

  const filtros = estadoAFiltros(estado);
  const { rows, totalFilas, totalMonto, loading, cargarMas } = useTabla(filtros);
  const gobierno = useGobierno(estado.jurisdiccion, estado.anio);

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

  // TanStack Table
  const [sorting, setSorting] = useState([{ id: "monto_deflactado", desc: true }]);
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: (upd) => {
      const next = typeof upd === "function" ? upd(sorting) : upd;
      setSorting(next);
      if (next[0]) {
        setFiltro({
          ordenPor: next[0].id === "fecha" ? "fecha" : "monto",
          desc: next[0].desc,
        });
      }
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
  });

  const hayMas = rows.length < totalFilas;

  return (
    <>
      {/* ── FILTER BAR ── */}
      <div className="filter-bar">
        <div className="row1">
          <span className="lead">Estás viendo</span>

          {/* Chip jurisdicción activa o select */}
          {estado.jurisdiccion ? (
            <span className="chip-active">
              <span className="label">Jurisdicción:</span>
              <strong>{estado.jurisdiccion}</strong>
              <button className="close" aria-label="Quitar" onClick={() => setFiltro({ jurisdiccion: null })}>×</button>
            </span>
          ) : (
            <select
              className="chip-add"
              value=""
              onChange={(e) => e.target.value && setFiltro({ jurisdiccion: e.target.value })}
              aria-label="Filtrar por jurisdicción"
            >
              <option value="">+ Jurisdicción</option>
              {JURISDICCIONES.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          )}

          {/* Chip año activo o select */}
          {estado.anio ? (
            <span className="chip-active">
              <span className="label">Año:</span>
              <strong>{estado.anio}</strong>
              <button className="close" aria-label="Quitar" onClick={() => setFiltro({ anio: null })}>×</button>
            </span>
          ) : (
            <select
              className="chip-add"
              value=""
              onChange={(e) => e.target.value && setFiltro({ anio: Number(e.target.value) })}
              aria-label="Filtrar por año"
            >
              <option value="">+ Año</option>
              {ANIOS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          )}

          {/* Chip entidad activa */}
          {estado.entidadNorm && (
            <span className="chip-active">
              <span className="label">{estado.entidadTipo === "medio" ? "Medio:" : "Proveedor:"}</span>
              <strong>{textoBusq || estado.entidadNorm}</strong>
              <button className="close" aria-label="Quitar" onClick={quitarEntidad}>×</button>
            </span>
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
        <div className="table-scroll">
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
              onClick={cargarMas}
              disabled={loading}
              style={{ background:"var(--color-bg-elev-2)", border:"1px solid var(--color-border-strong)", color:"var(--color-fg)", padding:"8px 20px", borderRadius:8, cursor:"pointer", fontSize:"var(--text-small)", fontWeight:500 }}
            >
              {loading ? "Cargando…" : `Cargar más (${fmtNum.format(totalFilas - rows.length)} restantes)`}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
