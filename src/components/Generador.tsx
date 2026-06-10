/**
 * Generador.tsx — sección "Cuánto recibió".
 *
 * Buscador MiniSearch → query getCuantoRecibio → resultado con monto total.
 * Year pills filtran por año específico o histórico.
 * Botones de compartir generan deeplinks (url-state.ts urlGenerador).
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { getCuantoRecibio, type ResultadoCuantoRecibio, type TotalPorAnioJuris, type TipoEntidad } from "../lib/queries";
import { urlGenerador } from "../lib/url-state";
import { buscar, buscarGrupos, getGrupoPorNorm, type EntidadBusqueda, type GrupoInfo } from "../lib/search";
import { descargarPlaca } from "../lib/generarImagenCanvas";

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

const fmtARS = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const fmtARS1 = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 });
const fmtNum = new Intl.NumberFormat("es-AR");

function formatMontoGrande(v: number): string {
  return fmtARS.format(Math.round(v));
}

function humanizarMonto(v: number): { num: string; unidad: string } | null {
  if (v < 1e6) return null;
  const m = v / 1e6;
  const rounded = Math.round(m * 10) / 10;
  const num = m >= 100 ? fmtARS.format(Math.round(m)) : fmtARS1.format(rounded);
  return { num, unidad: rounded === 1 ? "millón" : "millones" };
}

// ---------------------------------------------------------------------------
// Desglose por jurisdicción para el resultado
// ---------------------------------------------------------------------------

interface FilaJuris {
  juris: string;
  total: number;
  n: number;
  anioMin: number;
  anioMax: number;
}

function desglosePorJuris(
  porAnio: TotalPorAnioJuris[],
  anioSel: number | "historico",
): FilaJuris[] {
  const base = anioSel === "historico" ? porAnio : porAnio.filter((r) => r.anio === anioSel);
  const map = new Map<string, { total: number; n: number; anios: number[] }>();
  for (const r of base) {
    const cur = map.get(r.jurisdiccion) ?? { total: 0, n: 0, anios: [] };
    cur.total += r.total ?? 0;
    cur.n += r.n_ordenes ?? 0;
    cur.anios.push(r.anio);
    map.set(r.jurisdiccion, cur);
  }
  return [...map.entries()]
    .map(([juris, v]) => ({
      juris,
      total: v.total,
      n: v.n,
      anioMin: Math.min(...v.anios),
      anioMax: Math.max(...v.anios),
    }))
    .sort((a, b) => b.total - a.total);
}

// ---------------------------------------------------------------------------
// Sub-componente: tabla de desglose por jurisdicción
// ---------------------------------------------------------------------------

function DesgloseJuris({
  porAnio,
  anioSel,
  tipo,
}: {
  porAnio: TotalPorAnioJuris[];
  anioSel: number | "historico";
  tipo: TipoEntidad;
}) {
  const filas = desglosePorJuris(porAnio, anioSel);
  if (!filas.length) return null;
  const maxTotal = Math.max(...filas.map((f) => f.total), 1);
  return (
    <div className="desglose-juris" style={{ marginTop:"1.25rem", width:"100%", maxWidth:480, marginLeft:"auto", marginRight:"auto" }}>
      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"var(--text-small)" }}>
        <thead>
          <tr style={{ color:"var(--color-fg-subtle)", fontSize:"var(--text-micro)" }}>
            <th style={{ textAlign:"left", fontWeight:500, paddingBottom:6 }}>Jurisdicción</th>
            <th style={{ textAlign:"left", fontWeight:500, paddingBottom:6 }}>Período</th>
            <th style={{ textAlign:"right", fontWeight:500, paddingBottom:6 }}>Monto</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.juris} style={{ borderTop:"1px solid var(--color-border)" }}>
              <td style={{ padding:"6px 0", paddingRight:8, whiteSpace:"nowrap", color:"var(--color-fg)" }}>{f.juris}</td>
              <td style={{ padding:"6px 0", paddingRight:8 }}>
                <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                  <span style={{ color:"var(--color-fg-subtle)", whiteSpace:"nowrap", fontSize:"var(--text-micro)" }}>
                    {f.anioMin === f.anioMax ? f.anioMin : `${f.anioMin}–${f.anioMax}`}
                  </span>
                  <div style={{ flexGrow:1, height:4, background:"var(--color-border)", borderRadius:2, minWidth:40 }}>
                    <div style={{ height:"100%", background:"var(--color-accent)", borderRadius:2, width:`${Math.round((f.total / maxTotal) * 100)}%` }} />
                  </div>
                </div>
              </td>
              <td style={{ padding:"6px 0", textAlign:"right", color:"var(--color-fg)", whiteSpace:"nowrap" }}>
                $ {fmtARS.format(Math.round(f.total))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: panel de transparencia + disclaimer (solo modo grupo)
// ---------------------------------------------------------------------------

function PanelGrupo({
  grupo,
  abierto,
  onToggle,
}: {
  grupo: GrupoInfo;
  abierto: boolean;
  onToggle: () => void;
}) {
  const conDatos = grupo.miembros.filter((m) => m.total > 0).length;
  return (
    <div
      className="gen-grupo-panel"
      style={{ marginTop: "1.25rem", width: "100%", maxWidth: 480, marginLeft: "auto", marginRight: "auto", textAlign: "left" }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={abierto}
        style={{
          display: "flex", alignItems: "center", gap: 6, width: "100%",
          background: "none", border: "none", cursor: "pointer", padding: "6px 0",
          color: "var(--color-fg)", fontSize: "var(--text-small)", fontWeight: 600, textAlign: "left",
        }}
      >
        <span style={{ color: "var(--color-fg-subtle)", fontSize: "0.7em" }}>{abierto ? "▼" : "▶"}</span>
        Qué medios y empresas se suman ({conDatos})
      </button>

      {abierto && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-small)", marginTop: 6 }}>
          <tbody>
            {grupo.miembros.map((m) => (
              <tr key={`${m.eje}:${m.norm}`} style={{ borderTop: "1px solid var(--color-border)", opacity: m.total > 0 ? 1 : 0.45 }}>
                <td style={{ padding: "6px 0", paddingRight: 8, color: "var(--color-fg)" }}>
                  {m.nombre}
                  <span style={{ marginLeft: 6, color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                    {m.eje === "medio" ? "medio" : "empresa"}
                  </span>
                </td>
                <td style={{ padding: "6px 0", textAlign: "right", whiteSpace: "nowrap", color: "var(--color-fg)" }}>
                  {m.total > 0 ? `$ ${fmtARS.format(Math.round(m.total))}` : "sin registros"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p style={{ marginTop: "0.9rem", color: "var(--color-fg-subtle)", fontSize: "var(--text-micro)", lineHeight: 1.5 }}>
        Agrupación según el <a href="https://argentina.mom-gmr.org/es/propietarios/grupos-mediaticos/" target="_blank" rel="noopener" style={{ color: "var(--color-fg-subtle)", textDecoration: "underline" }}>Media Ownership Monitor Argentina</a> (2018), CC BY-ND 4.0. La pauta se asigna por medio, no al holding.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Year pills: Histórico + últimos 5 años + "…"
// ---------------------------------------------------------------------------

const ANIOS_PILLS = [2025, 2024, 2023, 2022, 2021];

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

interface GeneradorProps {
  initial?: { entidad: EntidadBusqueda; resultado: ResultadoCuantoRecibio; tipo: TipoEntidad } | null;
}

export default function Generador({ initial }: GeneradorProps) {
  const [tipo, setTipo] = useState<TipoEntidad>(initial?.tipo ?? "grupo");
  const [textoBusq, setTextoBusq] = useState(initial ? initial.entidad.nombre : "Clarín");
  const [sugerencias, setSugerencias] = useState<EntidadBusqueda[]>([]);
  const [mostrarSugs, setMostrarSugs] = useState(false);
  const [entidadActual, setEntidadActual] = useState<EntidadBusqueda | null>(initial ? initial.entidad : null);
  const [anioSel, setAnioSel] = useState<number | "historico">("historico");
  const [resultado, setResultado] = useState<ResultadoCuantoRecibio | null>(initial ? initial.resultado : null);
  const [loading, setLoading] = useState(false);
  const [generandoImg, setGenerandoImg] = useState(false);
  const [toast, setToast] = useState("");
  // Modo grupo: detalle del holding seleccionado (miembros que se suman).
  const [grupoInfo, setGrupoInfo] = useState<GrupoInfo | null>(null);
  const [mostrarMiembros, setMostrarMiembros] = useState(false);
  const busqRef = useRef<HTMLDivElement>(null);

  // Búsqueda al tipear: proveedor/medio van por MiniSearch; grupo filtra
  // grupos.json en cliente (son pocos). Con texto vacío en modo grupo igual
  // listamos los grupos con datos para poblar el desplegable.
  useEffect(() => {
    if (tipo === "grupo") {
      buscarGrupos(textoBusq).then(setSugerencias);
      return;
    }
    if (!textoBusq.trim()) { setSugerencias([]); return; }
    buscar(textoBusq, tipo).then(setSugerencias);
  }, [textoBusq, tipo]);

  // Cargar el detalle (miembros) del grupo seleccionado para el panel de
  // transparencia. Sólo aplica en modo grupo.
  useEffect(() => {
    if (entidadActual && entidadActual.tipo === "grupo") {
      getGrupoPorNorm(entidadActual.norm).then(setGrupoInfo);
    } else {
      setGrupoInfo(null);
    }
  }, [entidadActual]);

  // Cerrar sugerencias al click fuera
  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (busqRef.current && !busqRef.current.contains(e.target as Node))
        setMostrarSugs(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  // Consultar cuando cambia la entidad o el año
  const consultar = useCallback(async (e: EntidadBusqueda) => {
    setLoading(true);
    try {
      const res = await getCuantoRecibio(e.norm, e.tipo, e.nombre);
      setResultado(res);
    } finally {
      setLoading(false);
    }
  }, []);

  // En el primer render, si el demo viene sembrado desde home.json, NO se
  // consulta sql.js (el resultado ya está). Solo consulta al cambiar de entidad.
  const primeraConsulta = useRef(true);
  useEffect(() => {
    if (primeraConsulta.current) {
      primeraConsulta.current = false;
      if (initial && entidadActual === initial.entidad) return; // sembrado
    }
    if (entidadActual) consultar(entidadActual);
  }, [entidadActual, consultar]);

  // Demo "Clarín" al montar. Solo si NO hay seed; el buscar() de montaje es lo
  // que disparaba la descarga de search.json (1,5 MB) en el primer paint.
  useEffect(() => {
    if (initial) return;
    buscar("Clarín", "proveedor", 1).then((res) => {
      if (res[0]) {
        setEntidadActual(res[0]);
        setTextoBusq(res[0].nombre);
      }
    });
  }, []);

  const elegirEntidad = (e: EntidadBusqueda) => {
    setEntidadActual(e);
    setTextoBusq(e.nombre);
    setMostrarSugs(false);
  };

  // Cambio de toggle Proveedor / Medio / Grupo mediático. Limpia la selección;
  // en modo grupo precarga el grupo más grande para que la vista no quede vacía.
  const cambiarTipo = (t: TipoEntidad) => {
    if (t === tipo) return;
    setTipo(t);
    setEntidadActual(null);
    setResultado(null);
    setGrupoInfo(null);
    setMostrarMiembros(false);
    setMostrarSugs(false);
    if (t === "grupo") {
      buscarGrupos("", 1).then((res) => {
        if (res[0]) { setEntidadActual(res[0]); setTextoBusq(res[0].nombre); }
      });
    } else {
      setTextoBusq("");
    }
  };

  // Calcular monto para el año/período seleccionado
  const montoMostrado = (): number => {
    if (!resultado) return 0;
    if (anioSel === "historico") return resultado.totalHistorico;
    return resultado.porAnio
      .filter((r) => r.anio === anioSel)
      .reduce((acc, r) => acc + (r.total ?? 0), 0);
  };

  const hayDatos = montoMostrado() > 0;

  // Compartir
  const compartirUrl = () => {
    if (!entidadActual) return "";
    return urlGenerador({ norm: entidadActual.norm, tipo: entidadActual.tipo, anio: anioSel });
  };

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 2200);
  };

  const onDescargarImagen = async () => {
    if (!entidadActual || !resultado) return;
    setGenerandoImg(true);
    try {
      const filas = desglosePorJuris(resultado.porAnio, anioSel);
      const periodoImg =
        anioSel === "historico" && resultado.porAnio.length > 0
          ? `${Math.min(...resultado.porAnio.map((r) => r.anio))}–${Math.max(...resultado.porAnio.map((r) => r.anio))}`
          : String(anioSel);
      await descargarPlaca({
        nombre: entidadActual.nombre,
        periodo: periodoImg,
        juris: filas.map((f) => ({
          nombre: f.juris,
          monto: f.total,
          periodo: f.anioMin === f.anioMax ? String(f.anioMin) : `${f.anioMin}–${f.anioMax}`,
        })),
      });
    } finally {
      setGenerandoImg(false);
    }
  };

  const onShareX = () => {
    if (!entidadActual) return;
    const hum = humanizarMonto(montoMostrado());
    const montoTxt = hum ? `$${hum.num} ${hum.unidad}` : `$${formatMontoGrande(montoMostrado())}`;
    const texto = `${entidadActual.nombre} recibió ${montoTxt} de pauta oficial. Fuente: datospautaoficial.com.ar`;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(texto + "\n" + compartirUrl())}`, "_blank", "noopener");
  };

  const onCopiarLink = async () => {
    await navigator.clipboard.writeText(compartirUrl()).catch(() => {});
    showToast("Link copiado al portapapeles");
  };

  const contextoAnio =
    anioSel === "historico"
      ? resultado
        ? `${Math.min(...resultado.porAnio.map((r) => r.anio))} — ${Math.max(...resultado.porAnio.map((r) => r.anio))} (histórico)`
        : "(histórico)"
      : String(anioSel);

  return (
    <div className="gen-card">
      {/* ── Búsqueda ── */}
      <div className="gen-search-row">
        <div className="segmented" role="tablist" aria-label="Tipo">
          <button className={tipo === "proveedor" ? "on" : ""} type="button" onClick={() => cambiarTipo("proveedor")}>Proveedor</button>
          <button className={tipo === "medio" ? "on" : ""} type="button" onClick={() => cambiarTipo("medio")}>Medio</button>
          <button className={tipo === "grupo" ? "on" : ""} type="button" onClick={() => cambiarTipo("grupo")}>Grupo mediático</button>
        </div>

        <div className="gen-search-input-wrap" ref={busqRef} style={{ position: "relative" }}>
          <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            className="gen-search-input"
            type="search"
            value={textoBusq}
            placeholder={tipo === "grupo" ? "Buscar grupo mediático…" : "Buscar proveedor o medio…"}
            aria-label="Buscar entidad"
            onChange={(e) => { setTextoBusq(e.target.value); setMostrarSugs(true); }}
            onFocus={() => setMostrarSugs(true)}
          />
          <span className="chevron-icon">▾</span>

          {mostrarSugs && sugerencias.length > 0 && (
            <ul role="listbox" style={{ position:"absolute", top:"100%", left:0, right:0, zIndex:50, background:"var(--color-bg-elev-2)", border:"1px solid var(--color-border-strong)", borderRadius:8, marginTop:4, padding:"4px 0", listStyle:"none", boxShadow:"0 8px 32px rgba(0,0,0,.4)" }}>
              {sugerencias.map((s) => (
                <li key={s.id} role="option" aria-selected={entidadActual?.norm === s.norm}
                  onClick={() => elegirEntidad(s)}
                  style={{ padding:"8px 14px", cursor:"pointer", fontSize:"var(--text-small)", display:"flex", justifyContent:"space-between", alignItems:"center", gap:8 }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-elev-3)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                >
                  <span>{s.nombre}</span>
                  <span style={{ color:"var(--color-fg-subtle)", fontSize:"var(--text-micro)", whiteSpace:"nowrap", flexShrink:0 }}>{fmtNum.format(s.n)} órdenes</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── Resultado o vacío ── */}
      {entidadActual && !loading && !hayDatos ? (
        <div className="gen-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-fg-subtle)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin:"0 auto 1rem", display:"block" }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <div style={{ color:"var(--color-fg-strong)", fontWeight:600, marginBottom:"0.5rem" }}>No encontramos registros</div>
          <div style={{ color:"var(--color-fg-subtle)", fontSize:"var(--text-small)", maxWidth:400, margin:"0 auto", lineHeight:1.5 }}>
            La base de datos oficial tiene baches de información. Verificá el nombre o probá por razón social.
          </div>
        </div>
      ) : (
        <div className="gen-result">
          <div className="gen-entity-name">{entidadActual?.nombre ?? "—"}</div>
          <div className="gen-said">recibió en <span style={{ color:"var(--color-accent)", fontWeight:600 }}>Pauta Oficial</span></div>
          <div className="gen-narrative">
            <div className="monto" style={{ opacity: loading ? 0.4 : 1, transition:"opacity 200ms" }}>
              {(() => {
                const hum = humanizarMonto(montoMostrado());
                if (hum) return (
                  <>
                    <span className="currency-prefix">$</span>{hum.num}
                    <span className="monto-unidad"> {hum.unidad}</span>
                  </>
                );
                return <><span className="currency-prefix">$</span>{formatMontoGrande(montoMostrado())}</>;
              })()}
            </div>
            {resultado && resultado.porAnio.length > 0 && (
              <>
                <div className="gen-separator" />
                <DesgloseJuris porAnio={resultado.porAnio} anioSel={anioSel} tipo={tipo} />
              </>
            )}
            {tipo === "grupo" && grupoInfo && (
              <PanelGrupo
                grupo={grupoInfo}
                abierto={mostrarMiembros}
                onToggle={() => setMostrarMiembros((v) => !v)}
              />
            )}
            <p className="approx">
              <strong>* Aproximado.</strong> Al haber huecos de cobertura en los datos públicos, el monto real recibido puede ser mayor.
            </p>
          </div>
        </div>
      )}

      {/* ── Year pills ── */}
      <div className="gen-controls-row">
        <div className="year-pills" role="tablist" aria-label="Período">
          <button className={anioSel === "historico" ? "year-pill on" : "year-pill"} type="button" onClick={() => setAnioSel("historico")}>Histórico</button>
          {ANIOS_PILLS.map((a) => (
            <button key={a} className={anioSel === a ? "year-pill on" : "year-pill"} type="button" onClick={() => setAnioSel(a)}>{a}</button>
          ))}
        </div>
      </div>

      {/* ── Share buttons ── */}
      <div className="share-block">
        <p className="share-cta">Compartí en tus redes sociales</p>
        <div className="share-buttons">
          <button
            className="share-btn share-btn--primary"
            type="button"
            onClick={onDescargarImagen}
            disabled={generandoImg || !hayDatos}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            {generandoImg ? "Generando…" : "Descargar imagen"}
          </button>
          <button className="share-btn" type="button" onClick={onShareX}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Compartir en X
          </button>
          <button className="share-btn" type="button" onClick={onCopiarLink}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
            </svg>
            Copiar link
          </button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="toast show" style={{ position:"fixed", bottom:"2rem", left:"50%", transform:"translateX(-50%)" }}>
          {toast}
        </div>
      )}
    </div>
  );
}
