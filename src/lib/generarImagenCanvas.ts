// =====================================================================
// Placa para compartir en redes — Datos Pauta Oficial (v5)
// 1080×1080, Canvas API pura, client-side, sin dependencias.
//
// Decisiones de diseño:
// - Layout editorial alineado a la izquierda.
// - Monto humanizado a millones, en blanco: la jerarquía la dan tamaño
//   y peso, no el color. Sin cifra exacta debajo (ruido); los períodos
//   viven en las filas de jurisdicción.
//   El cian queda para acentos chicos: "Pauta Oficial", la regla y la URL.
// - Header con un solo lockup de marca: isotipo (bandera) + URL.
//   El wordmark del logo era redundante con la URL.
// - Desglose por jurisdicción con barras finas, sin rótulo de sección.
// - Contenido termina a ~150px del borde inferior (zona segura para la
//   UI de Instagram Stories).
//
// Uso:
//   const canvas = await generarImagenCanvas({
//     nombre: "Clarín",
//     periodo: "2009–2024",
//     juris: [
//       { nombre: "Nación", monto: 18234000000, periodo: "2009–2024" },
//       { nombre: "PBA",    monto: 4120000000,  periodo: "2016–2024" },
//     ],
//   });
//   canvas.toBlob(...) para descargar como PNG (o usar descargarPlaca).
// =====================================================================

export interface JurisdiccionPlaca {
  nombre: string;
  monto: number;
  periodo: string;
}

export interface DatosPlaca {
  nombre: string;
  periodo: string;
  juris: JurisdiccionPlaca[]; // ordenadas de mayor a menor monto
}

const W = 1080;
const H = 1080;
const PAD = 96;
const F = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";

const C = {
  bg: "#0b0f19", bg2: "#0e1424",
  border: "#243044", barBg: "#161e2e",
  fg: "#e2e8f0", fgStrong: "#f8fafc", fgSubtle: "#64748b", fgMid: "#94a3b8",
  accent: "#22d3ee",
};

// bbox del isotipo (la bandera, sin el wordmark) dentro de logo.webp;
// el archivo tiene padding negro y texto que acá no usamos
const LOGO_SRC = "/logo.webp";
const ICONO_CROP = { sx: 265, sy: 560, sw: 610, sh: 414 };

const fmt = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 });

// 18234000000 → { num: "18.234", unidad: "millones" } | null si < 1 millón
function humanizar(v: number): { num: string; unidad: string } | null {
  if (v < 1e6) return null;
  const m = v / 1e6;
  const num = m >= 100 ? fmt.format(Math.round(m)) : fmt1.format(Math.round(m * 10) / 10);
  const unidad = Math.round(m * 10) / 10 === 1 ? "millón" : "millones";
  return { num, unidad };
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

interface Segmento { text: string; font: string; color: string }

// Dibuja segmentos de distinta fuente/color en una línea
function drawMixed(ctx: CanvasRenderingContext2D, segs: Segmento[], x: number, baseline: number): void {
  let cx = x;
  ctx.textAlign = "left";
  for (const s of segs) {
    ctx.font = s.font;
    ctx.fillStyle = s.color;
    ctx.fillText(s.text, cx, baseline);
    cx += ctx.measureText(s.text).width;
  }
}

function fitFont(ctx: CanvasRenderingContext2D, text: string, weight: number, start: number, min: number, maxW: number): number {
  let s = start;
  ctx.font = `${weight} ${s}px ${F}`;
  while (ctx.measureText(text).width > maxW && s > min) {
    s -= 2;
    ctx.font = `${weight} ${s}px ${F}`;
  }
  return s;
}

// Devuelve el ancho dibujado
function drawIcono(ctx: CanvasRenderingContext2D, logo: HTMLImageElement, x: number, y: number, h: number): number {
  const { sx, sy, sw, sh } = ICONO_CROP;
  const w = h * (sw / sh);
  ctx.save();
  ctx.globalCompositeOperation = "lighten"; // anula el fondo negro del webp
  ctx.drawImage(logo, sx, sy, sw, sh, x, y, w, h);
  ctx.restore();
  return w;
}

let logoCache: Promise<HTMLImageElement> | null = null;
function cargarLogo(): Promise<HTMLImageElement> {
  if (!logoCache) {
    logoCache = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = LOGO_SRC;
    });
  }
  return logoCache;
}

export async function generarImagenCanvas(datos: DatosPlaca): Promise<HTMLCanvasElement> {
  const logo = await cargarLogo();
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  const d = datos;
  const colW = W - PAD * 2;
  const right = W - PAD;

  // ---- Fondo: gradiente vertical sutil ----
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, C.bg2);
  bg.addColorStop(0.55, C.bg);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
  ctx.textBaseline = "alphabetic";

  // ---- Header: un solo lockup de marca — isotipo + URL ----
  const iw = drawIcono(ctx, logo, PAD, 56, 56);
  ctx.font = `700 32px ${F}`;
  ctx.fillStyle = C.accent;
  ctx.textAlign = "left";
  ctx.fillText("datospautaoficial.com.ar", PAD + iw + 24, 95);

  // ---- Datos derivados ----
  const total = d.juris.reduce((a, j) => a + j.monto, 0);
  const hum = humanizar(total);
  const conDesglose = d.juris.length >= 2;
  const yShift = conDesglose ? 0 : 60; // sin desglose, el bloque respira más abajo

  // ---- Nombre de la entidad ----
  ctx.fillStyle = C.fgStrong;
  const ns = fitFont(ctx, d.nombre, 800, 92, 44, colW);
  ctx.font = `800 ${ns}px ${F}`;
  ctx.fillText(d.nombre, PAD, 270 + yShift);

  // ---- "recibió en Pauta Oficial" ----
  drawMixed(ctx, [
    { text: "recibió en ", color: C.fgSubtle, font: `400 40px ${F}` },
    { text: "Pauta Oficial", color: C.accent, font: `700 40px ${F}` },
  ], PAD, 338 + yShift);

  // ---- Monto protagonista (humanizado a millones, en blanco) ----
  // Sin cifra exacta debajo: es ruido, y el período ya está en las jurisdicciones.
  const my = 524 + yShift;
  if (hum) {
    const numTxt = "$" + hum.num;
    let ms = 168;
    while (ms > 70) {
      ctx.font = `800 ${ms}px ${F}`;
      const wNum = ctx.measureText(numTxt).width;
      ctx.font = `700 ${Math.round(ms * 0.34)}px ${F}`;
      const wUni = ctx.measureText(" " + hum.unidad).width;
      if (wNum + wUni <= colW) break;
      ms -= 4;
    }
    drawMixed(ctx, [
      { text: numTxt, color: C.fgStrong, font: `800 ${ms}px ${F}` },
      { text: " " + hum.unidad, color: C.fgMid, font: `700 ${Math.round(ms * 0.34)}px ${F}` },
    ], PAD, my);
  } else {
    const t = "$ " + fmt.format(total);
    const ms = fitFont(ctx, t, 800, 150, 60, colW);
    ctx.font = `800 ${ms}px ${F}`;
    ctx.fillStyle = C.fgStrong;
    ctx.fillText(t, PAD, my);
  }

  // ---- Regla cian: separador hacia el desglose ----
  ctx.fillStyle = C.accent;
  roundRect(ctx, PAD, my + 76, 140, 8, 4);
  ctx.fill();

  // ---- Desglose por jurisdicción (sin rótulo; barras finas) ----
  if (conDesglose) {
    const top = d.juris.slice(0, 3);
    const max = Math.max(...top.map((j) => j.monto), 1);
    let y = 688;
    for (const j of top) {
      ctx.fillStyle = C.fg;
      ctx.font = `600 27px ${F}`;
      ctx.fillText(j.nombre, PAD, y);
      const jw = ctx.measureText(j.nombre).width;
      ctx.fillStyle = C.fgSubtle;
      ctx.font = `400 22px ${F}`;
      ctx.fillText("  · " + j.periodo, PAD + jw + 4, y);
      ctx.textAlign = "right";
      ctx.fillStyle = C.fg;
      ctx.font = `500 26px ${F}`;
      ctx.fillText("$ " + fmt.format(j.monto), right, y);
      ctx.textAlign = "left";
      ctx.fillStyle = C.barBg;
      roundRect(ctx, PAD, y + 14, colW, 8, 4); ctx.fill();
      ctx.fillStyle = "rgba(34,211,238,0.45)";
      roundRect(ctx, PAD, y + 14, Math.max(colW * (j.monto / max), 8), 8, 4); ctx.fill();
      y += 84;
    }
  } else if (d.juris.length === 1) {
    // una sola jurisdicción → chip informativo
    const j = d.juris[0];
    const txt = j.nombre + " · " + j.periodo;
    ctx.font = `600 30px ${F}`;
    const tw = ctx.measureText(txt).width + 56;
    ctx.strokeStyle = C.border;
    ctx.lineWidth = 2;
    roundRect(ctx, PAD, 730, tw, 60, 30);
    ctx.stroke();
    ctx.fillStyle = C.fg;
    ctx.fillText(txt, PAD + 28, 771);
  }

  // ---- Disclaimer — termina a ~150px del borde (zona segura Stories) ----
  drawMixed(ctx, [
    { text: "Cifra aproximada por huecos en datos públicos. El monto real ", color: C.fgSubtle, font: `400 23px ${F}` },
    { text: "puede ser mayor", color: C.fg, font: `700 23px ${F}` },
    { text: ".", color: C.fgSubtle, font: `400 23px ${F}` },
  ], PAD, 930);

  // ---- Borde exterior sutil (separa la placa de feeds oscuros) ----
  ctx.strokeStyle = C.border;
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, W - 2, H - 2);

  return canvas;
}

// Helper de descarga
export async function descargarPlaca(datos: DatosPlaca): Promise<void> {
  const canvas = await generarImagenCanvas(datos);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (!blob) return resolve();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const slug = datos.nombre.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-");
      a.download = `pauta-oficial-${slug}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
      resolve();
    }, "image/png");
  });
}
