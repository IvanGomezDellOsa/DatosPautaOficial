#!/usr/bin/env node
/**
 * upload_r2.mjs — sube los chunks `pauta.sqlite.*` a Cloudflare R2.
 *
 * POR QUÉ EXISTE: Cloudflare Pages NO soporta HTTP range requests — ante un
 * pedido `Range:` devuelve `200` con el archivo completo en vez de `206 Partial
 * Content` (confirmado en su doc oficial). sql.js-httpvfs lee la SQLite por
 * rangos; al recibir el archivo entero interpreta bytes del offset 0 como si
 * fueran de otro offset y SQLite tira `database disk image is malformed`. Es
 * intermitente (anda con caché caliente, falla en frío/incógnito).
 *
 * SOLUCIÓN: servir SOLO los chunks de la SQLite desde Cloudflare R2, que sí
 * devuelve 206. El resto del sitio (HTML/JS/CSS, config.json, search.json,
 * home.json) se queda en Pages — esos se bajan enteros, no usan rangos.
 *
 * Corre en el build de Cloudflare Pages, después de build_db.py. Variables de
 * entorno necesarias (setearlas en Pages → Settings → Environment variables):
 *   R2_BUCKET             nombre del bucket (ej: "datospautaoficial-db")
 *   CLOUDFLARE_API_TOKEN  token con permiso "Edit" de R2
 *   CLOUDFLARE_ACCOUNT_ID id de la cuenta de Cloudflare
 *   R2_PUBLIC_URL         (la usa build_db.py para el urlPrefix de config.json)
 *
 * Si R2_BUCKET no está seteada (build local), no hace nada: así `py
 * etl/build_db.py && npm run build && npx http-server dist` sigue funcionando
 * local sirviendo los chunks desde /data/.
 */

import { execFileSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const bucket = process.env.R2_BUCKET;
const dir = "public/data";

if (!bucket) {
  console.log("[r2] R2_BUCKET no seteada — salteo la subida a R2 (build local).");
  process.exit(0);
}

const chunks = readdirSync(dir)
  .filter((f) => /^pauta\.sqlite\.\d+$/.test(f))
  .sort((a, b) => Number(a.split(".").pop()) - Number(b.split(".").pop()));

if (chunks.length === 0) {
  console.error(`[r2] ERROR: no encontré chunks en ${dir}/ (¿corriste build_db.py antes?)`);
  process.exit(1);
}

console.log(`[r2] subiendo ${chunks.length} chunks a R2://${bucket} ...`);
for (const f of chunks) {
  const path = join(dir, f);
  const mb = (statSync(path).size / 1048576).toFixed(1);
  console.log(`[r2]   ${f}  (${mb} MB)`);
  execFileSync(
    "npx",
    [
      "--yes", "wrangler", "r2", "object", "put",
      `${bucket}/${f}`,
      `--file=${path}`,
      "--content-type=application/octet-stream",
      "--remote",
    ],
    { stdio: "inherit" },
  );
}
console.log(`[r2] OK: ${chunks.length} chunks subidos a R2.`);
