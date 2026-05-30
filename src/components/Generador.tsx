/**
 * Generador.tsx — sección "Cuánto recibió".
 *
 * Buscador MiniSearch → query getCuantoRecibio → resultado con monto total.
 * Year pills filtran por año específico o histórico.
 * Botones de compartir generan deeplinks (url-state.ts urlGenerador).
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { getCuantoRecibio, type ResultadoCuantoRecibio } from "../lib/queries";
import { urlGenerador } from "../lib/url-state";
import { buscar, type EntidadBusqueda } from "../lib/search";

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

const fmtARS = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat("es-AR");

function formatMontoGrande(v: number): string {
  return fmtARS.format(Math.round(v));
}

// ---------------------------------------------------------------------------
// Year pills: Histórico + últimos 5 años + "…"
// ---------------------------------------------------------------------------

const ANIOS_PILLS = [2025, 2024, 2023, 2022, 2021];

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export default function Generador() {
  const [tipo, setTipo] = useState<"proveedor" | "medio">("proveedor");
  const [textoBusq, setTextoBusq] = useState("Clarín");
  const [sugerencias, setSugerencias] = useState<EntidadBusqueda[]>([]);
  const [mostrarSugs, setMostrarSugs] = useState(false);
  const [entidadActual, setEntidadActual] = useState<EntidadBusqueda | null>(null);
  const [anioSel, setAnioSel] = useState<number | "historico">("historico");
  const [resultado, setResultado] = useState<ResultadoCuantoRecibio | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const busqRef = useRef<HTMLDivElement>(null);

  // Búsqueda MiniSearch al tipear
  useEffect(() => {
    if (!textoBusq.trim()) { setSugerencias([]); return; }
    buscar(textoBusq, tipo).then(setSugerencias);
  }, [textoBusq, tipo]);

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

  useEffect(() => {
    if (entidadActual) consultar(entidadActual);
  }, [entidadActual, consultar]);

  // Cargar "Clarín" al montar como demostración
  useEffect(() => {
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

  // Calcular monto para el año/período seleccionado
  const montoMostrado = (): number => {
    if (!resultado) return 0;
    if (anioSel === "historico") return resultado.totalHistorico;
    return resultado.porAnio
      .filter((r) => r.anio === anioSel)
      .reduce((acc, r) => acc + (r.total ?? 0), 0);
  };

  const ordenesContadas = (): number => {
    if (!resultado) return 0;
    if (anioSel === "historico") return resultado.nOrdenesHistorico;
    return resultado.porAnio
      .filter((r) => r.anio === anioSel)
      .reduce((acc, r) => acc + (r.n_ordenes ?? 0), 0);
  };

  const jurisdiccionesContadas = (): number => {
    if (!resultado || anioSel === "historico") {
      return new Set(resultado?.porAnio.map((r) => r.jurisdiccion) ?? []).size;
    }
    return new Set(resultado.porAnio.filter((r) => r.anio === anioSel).map((r) => r.jurisdiccion)).size;
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

  const onShareX = () => {
    if (!entidadActual) return;
    const monto = formatMontoGrande(montoMostrado());
    const texto = `${entidadActual.nombre} recibió $ ${monto} en publicidad oficial · datospautaoficial.com.ar`;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(texto + "\n" + compartirUrl())}`, "_blank", "noopener");
  };

  const onShareIG = async () => {
    if (navigator.share) {
      await navigator.share({ title: "Datos Pauta Oficial", url: compartirUrl() }).catch(() => {});
    } else {
      await navigator.clipboard.writeText(compartirUrl()).catch(() => {});
      showToast("Link copiado · pegalo en Instagram");
    }
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
          <button className={tipo === "proveedor" ? "on" : ""} type="button" onClick={() => { setTipo("proveedor"); setEntidadActual(null); setResultado(null); }}>Proveedor</button>
          <button className={tipo === "medio" ? "on" : ""} type="button" onClick={() => { setTipo("medio"); setEntidadActual(null); setResultado(null); }}>Medio</button>
        </div>

        <div className="gen-search-input-wrap" ref={busqRef} style={{ position: "relative" }}>
          <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            className="gen-search-input"
            type="search"
            value={textoBusq}
            placeholder="Buscar proveedor o medio…"
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
                  style={{ padding:"8px 14px", cursor:"pointer", fontSize:"var(--text-small)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-elev-3)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                >
                  {s.nombre}
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
          <div className="gen-entity-eyebrow">{tipo === "medio" ? "Medio" : "Proveedor"}</div>
          <div className="gen-entity-name">{entidadActual?.nombre ?? "—"}</div>
          <div className="gen-said">recibió en pauta oficial</div>
          <div className="gen-narrative">
            <div className="monto" style={{ opacity: loading ? 0.4 : 1, transition:"opacity 200ms" }}>
              <span className="currency-prefix">$</span>
              {formatMontoGrande(montoMostrado())}
            </div>
            <div className="context">
              en <strong style={{ color:"var(--color-fg)" }}>{contextoAnio}</strong>
            </div>
            {resultado && (
              <div className="meta">
                {fmtNum.format(ordenesContadas())} órdenes · {jurisdiccionesContadas()} jurisdicción{jurisdiccionesContadas() !== 1 ? "es" : ""}
              </div>
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
        <div className="share-buttons">
          <button className="share-btn" type="button" onClick={onShareX}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Compartir en X
          </button>
          <button className="share-btn" type="button" onClick={onShareIG}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="2" y="2" width="20" height="20" rx="5" ry="5"/>
              <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/>
              <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/>
            </svg>
            Compartir en Instagram
          </button>
          <button className="share-btn" type="button" onClick={onCopiarLink}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
