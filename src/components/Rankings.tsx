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
import type { SeedRankings } from "../lib/home";

const fmtARS = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

type TipoRanking = "proveedor" | "medio" | "grupo";

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
  tipo: TipoRanking;
  onTipoChange: (t: TipoRanking) => void;
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
        <div className="segmented" role="group" aria-label="Tipo de entidad">
          <button
            className={tipo === "proveedor" ? "on" : ""}
            aria-pressed={tipo === "proveedor"}
            type="button"
            onClick={() => onTipoChange("proveedor")}
          >
            Proveedor
          </button>
          <button
            className={tipo === "medio" ? "on" : ""}
            aria-pressed={tipo === "medio"}
            type="button"
            onClick={() => onTipoChange("medio")}
          >
            Medio
          </button>
          <button
            className={tipo === "grupo" ? "on" : ""}
            aria-pressed={tipo === "grupo"}
            type="button"
            onClick={() => onTipoChange("grupo")}
          >
            Grupo mediático
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


      {tipo === "grupo" && items.length > 0 && (
        <p className="card-disclaimer">
          Agrupación según el{" "}
          <a
            href="https://argentina.mom-gmr.org/es/propietarios/grupos-mediaticos/"
            target="_blank"
            rel="noopener"
            style={{ color: "var(--color-fg-subtle)", textDecoration: "underline" }}
          >
            Media Ownership Monitor Argentina
          </a>{" "}
          (2018), CC BY-ND 4.0. La pauta se asigna por medio, no al holding.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function Rankings({ initial }: { initial?: SeedRankings }) {
  // Ranking contextual (sigue los filtros de la tabla)
  const [tipoCtx, setTipoCtx] = useState<TipoRanking>("proveedor");
  const [itemsCtx, setItemsCtx] = useState<RankingItem[]>(
    initial ? initial.rankingContextual.proveedor : [],
  );
  const [loadingCtx, setLoadingCtx] = useState(!initial);
  const [tituloCtx, setTituloCtx] = useState(
    initial
      ? `${initial.filtroInicial.jurisdiccion} · ${initial.filtroInicial.anio}`
      : "Sin filtros activos",
  );

  // Ranking global (toda la base)
  const [tipoGlb, setTipoGlb] = useState<TipoRanking>("proveedor");
  const [itemsGlb, setItemsGlb] = useState<RankingItem[]>(
    initial ? initial.rankingGlobal.proveedor : [],
  );
  const [loadingGlb, setLoadingGlb] = useState(!initial);

  const cargarContextual = useCallback(async () => {
    const estado = leerEstadoTabla();
    const { jurisdiccion, anio } = estado;

    // Título dinámico
    const partes = [];
    if (jurisdiccion) partes.push(jurisdiccion);
    if (anio) partes.push(String(anio));
    setTituloCtx(partes.length ? partes.join(" · ") : "Todas las jurisdicciones");

    // Si los filtros coinciden con el seed de home.json, servimos desde ahí
    // (sin inicializar sql.js). Funciona también al alternar proveedor/medio.
    if (
      initial &&
      (jurisdiccion ?? null) === (initial.filtroInicial.jurisdiccion ?? null) &&
      (anio ?? null) === (initial.filtroInicial.anio ?? null)
    ) {
      setItemsCtx(initial.rankingContextual[tipoCtx]);
      setLoadingCtx(false);
      return;
    }

    setLoadingCtx(true);
    try {
      const items = await getRanking({
        jurisdiccion: jurisdiccion ?? undefined,
        anio: anio ?? undefined,
        tipo: tipoCtx,
        limite: 5,
      });
      setItemsCtx(items);
    } catch {
      setItemsCtx([]); // falla de red/DB → "Sin datos para esta selección"
    } finally {
      setLoadingCtx(false);
    }
  }, [tipoCtx, initial]);

  const cargarGlobal = useCallback(async () => {
    // El ranking global es invariante: siempre sale del seed (sin sql.js).
    if (initial) {
      setItemsGlb(initial.rankingGlobal[tipoGlb]);
      setLoadingGlb(false);
      return;
    }
    setLoadingGlb(true);
    try {
      const items = await getRanking({ tipo: tipoGlb, limite: 5 });
      setItemsGlb(items);
    } catch {
      setItemsGlb([]);
    } finally {
      setLoadingGlb(false);
    }
  }, [tipoGlb, initial]);

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
        subtitulo="deflactado"
        items={itemsCtx}
        loading={loadingCtx}
        tipo={tipoCtx}
        onTipoChange={setTipoCtx}
      />
      <RankingCard
        titulo="Base completa"
        subtitulo="deflactado"
        items={itemsGlb}
        loading={loadingGlb}
        tipo={tipoGlb}
        onTipoChange={setTipoGlb}
      />
    </div>
  );
}
