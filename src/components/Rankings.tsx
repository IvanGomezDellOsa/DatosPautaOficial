/**
 * Rankings.tsx — dos tarjetas de ranking: contextual y global.
 *
 * Contextual: top proveedores/medios de los filtros activos en la URL.
 *   Se re-ejecuta cuando cambia la URL (escucha popstate).
 * Global: top de toda la base, sin filtros. Se calcula una vez al montar.
 */

import { useState, useEffect, useCallback } from "react";
import { getRanking, type RankingItem } from "../lib/queries";
import { leerEstadoTabla } from "../lib/url-state";

const fmtARS = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

function formatMonto(v: number): string {
  if (v >= 1_000_000_000) return `$ ${(v / 1_000_000_000).toFixed(1).replace(".", ",")} MM`;
  if (v >= 1_000_000) return `$ ${Math.round(v / 1_000_000).toLocaleString("es-AR")} M`;
  return `$ ${fmtARS.format(Math.round(v))}`;
}

// ---------------------------------------------------------------------------
// Tarjeta de ranking
// ---------------------------------------------------------------------------

interface RankingCardProps {
  titulo: string;
  subtitulo: string;
  items: RankingItem[];
  loading: boolean;
  tipo: "proveedor" | "medio";
  onTipoChange: (t: "proveedor" | "medio") => void;
}

function RankingCard({ titulo, subtitulo, items, loading, tipo, onTipoChange }: RankingCardProps) {
  const max = items[0]?.total ?? 1;

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="card-title">{titulo}</div>
          <div className="card-sub">{subtitulo}</div>
        </div>
        <div className="segmented" role="tablist" aria-label="Tipo">
          <button
            className={tipo === "proveedor" ? "on" : ""}
            type="button"
            onClick={() => onTipoChange("proveedor")}
          >
            Proveedor
          </button>
          <button
            className={tipo === "medio" ? "on" : ""}
            type="button"
            onClick={() => onTipoChange("medio")}
          >
            Medio
          </button>
        </div>
      </div>

      <div className="ranking-rows">
        {loading ? (
          <div style={{ padding: "2rem", color: "var(--color-fg-subtle)", textAlign: "center", fontSize: "var(--text-small)" }}>
            Calculando…
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: "2rem", color: "var(--color-fg-subtle)", textAlign: "center", fontSize: "var(--text-small)" }}>
            Sin datos para esta selección.
          </div>
        ) : (
          items.map((item, i) => {
            const pct = Math.round((item.total / max) * 100);
            return (
              <div className="ranking-row" key={item.norm}>
                <span className="name">{item.nombre}</span>
                <span className="monto">{formatMonto(item.total)}</span>
                <div
                  className="bar"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${item.nombre}: ${pct}%`}
                >
                  <span
                    style={{
                      width: `${pct}%`,
                      transition: `width 600ms cubic-bezier(.22,1,.36,1) ${i * 60}ms`,
                    }}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>

      {items.length > 0 && (
        <p className="card-disclaimer">
          Los totales son aproximaciones inferiores: al haber huecos de cobertura, el monto real puede ser mayor.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function Rankings() {
  // Ranking contextual (sigue los filtros de la tabla)
  const [tipoCtx, setTipoCtx] = useState<"proveedor" | "medio">("proveedor");
  const [itemsCtx, setItemsCtx] = useState<RankingItem[]>([]);
  const [loadingCtx, setLoadingCtx] = useState(true);
  const [tituloCtx, setTituloCtx] = useState("Top 5 — filtros activos");

  // Ranking global (toda la base)
  const [tipoGlb, setTipoGlb] = useState<"proveedor" | "medio">("proveedor");
  const [itemsGlb, setItemsGlb] = useState<RankingItem[]>([]);
  const [loadingGlb, setLoadingGlb] = useState(true);

  const cargarContextual = useCallback(async () => {
    setLoadingCtx(true);
    try {
      const estado = leerEstadoTabla();
      const { jurisdiccion, anio } = estado;

      // Título dinámico
      const partes = [];
      if (jurisdiccion) partes.push(jurisdiccion);
      if (anio) partes.push(String(anio));
      setTituloCtx(`Top 5 — ${partes.length ? partes.join(" ") : "toda la base"}`);

      const items = await getRanking({
        jurisdiccion: jurisdiccion ?? undefined,
        anio: anio ?? undefined,
        tipo: tipoCtx,
        limite: 5,
      });
      setItemsCtx(items);
    } finally {
      setLoadingCtx(false);
    }
  }, [tipoCtx]);

  const cargarGlobal = useCallback(async () => {
    setLoadingGlb(true);
    try {
      const items = await getRanking({ tipo: tipoGlb, limite: 5 });
      setItemsGlb(items);
    } finally {
      setLoadingGlb(false);
    }
  }, [tipoGlb]);

  // Escucha cambios de URL para sincronizar el ranking contextual con la tabla
  useEffect(() => {
    cargarContextual();
    const handler = () => cargarContextual();
    window.addEventListener("popstate", handler);
    // También escucha el replaceState que usa url-state.ts
    const orig = window.history.replaceState.bind(window.history);
    window.history.replaceState = function (...args) {
      orig(...args);
      handler();
    };
    return () => {
      window.removeEventListener("popstate", handler);
      window.history.replaceState = orig;
    };
  }, [cargarContextual]);

  useEffect(() => { cargarGlobal(); }, [cargarGlobal]);

  return (
    <div className="rankings">
      <RankingCard
        titulo={tituloCtx}
        subtitulo="Contextual · deflactado"
        items={itemsCtx}
        loading={loadingCtx}
        tipo={tipoCtx}
        onTipoChange={setTipoCtx}
      />
      <RankingCard
        titulo="Top 5 — toda la base"
        subtitulo="Global · deflactado"
        items={itemsGlb}
        loading={loadingGlb}
        tipo={tipoGlb}
        onTipoChange={setTipoGlb}
      />
    </div>
  );
}
