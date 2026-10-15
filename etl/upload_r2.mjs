#!/usr/bin/env node
/**
 * upload_r2.mjs — publica los chunks `pauta.sqlite.*` en Cloudflare R2 bajo un
 * prefijo versionado e inmutable: `v/<version>/pauta.sqlite.N`.
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
 * VERSIONADO: build_db.py calcula la versión (sha256 de la base con
 * meta.generado enmascarado, ver version_db) y la pone en el urlPrefix de
 * config.json. Este script sube exactamente las claves que va a pedir el front,
 * derivadas de config.json:
 *   - cada versión se sube una sola vez y nunca se pisa: si v/<version>/ ya
 *     está completa en R2, no sube nada;
 *   - los chunks van con Cache-Control inmutable (el nombre ya fija el contenido);
 *   - manifest.json se sube último: que exista marca la versión como completa.
 * Así, subir antes de que Pages publique el deploy es inofensivo (nadie
 * referencia todavía la versión nueva) y una pestaña abierta sigue leyendo
 * entera la versión vieja. El cambio de versión lo hace config.json.
 *
 * Corre en el build de Cloudflare Pages, después de build_db.py. Variables de
 * entorno necesarias (setearlas en Pages → Settings → Environment variables):
 *   R2_BUCKET             nombre del bucket (ej: "datospautaoficial-db")
 *   CLOUDFLARE_API_TOKEN  token con permiso "Edit" de R2
 *   CLOUDFLARE_ACCOUNT_ID id de la cuenta de Cloudflare
 *   R2_PUBLIC_URL         (la usa build_db.py para el urlPrefix de config.json)
 *
 * `--dry-run`: hace todo menos ejecutar wrangler — valida los chunks contra
 * config.json, consulta la versión en R2 por la URL pública (solo lectura) e
 * imprime los comandos que correría. No necesita credenciales.
 *
 * Si R2_BUCKET no está seteada y config.json usa /data/ (build local), no hace
 * nada: así `py etl/build_db.py && npm run build && npx http-server dist` sigue
 * funcionando local sirviendo los chunks desde /data/.
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const DRY_RUN = process.argv.includes("--dry-run");
const CACHE_CHUNKS = "public, max-age=31536000, immutable";
const dir = "public/data";
const bucket = process.env.R2_BUCKET;
const publicUrl = (process.env.R2_PUBLIC_URL || "").trim().replace(/\/+$/, "");

// Los errores esperables cortan con este tipo y salen con exit code 1 sin
// process.exit(): en Windows, salir con fetch recien usado dispara un assert
// de libuv y el exit code queda en 127.
class Falla extends Error {}
function fail(msg) {
  throw new Falla(msg);
}

const SALTEO = "[r2] R2_BUCKET no seteada — salteo la subida a R2 (build local).";

async function main() {
  const configPath = join(dir, "config.json");
  if (!existsSync(configPath)) {
    if (!bucket) return console.log(SALTEO);
    fail(`no encontré ${configPath} (¿corriste build_db.py antes?)`);
  }
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  const { urlPrefix, databaseLengthBytes, serverChunkSize, suffixLength } = config;

  if (!/^https?:\/\//.test(urlPrefix)) {
    if (!bucket) return console.log(SALTEO);
    fail(`R2_BUCKET está seteada pero config.json tiene urlPrefix local (${urlPrefix}): ` +
      "build_db.py corrió sin R2_PUBLIC_URL y el front pediría los chunks a Pages.");
  }

  const m = /^(https?:\/\/.+)\/v\/([0-9a-f]{16})\/pauta\.sqlite\.$/.exec(urlPrefix);
  if (!m) fail(`urlPrefix sin versión: ${urlPrefix} (se espera <R2_PUBLIC_URL>/v/<version>/pauta.sqlite.)`);
  const [, base, version] = m;
  if (publicUrl && publicUrl !== base) {
    fail(`config.json apunta a ${base} pero R2_PUBLIC_URL es ${publicUrl}.`);
  }
  const prefijo = `v/${version}/`;

  // Chunks que va a pedir el front: sql.js-httpvfs arma cada URL como
  // urlPrefix + String(i).padStart(suffixLength, "0").
  const n = Math.ceil(databaseLengthBytes / serverChunkSize);
  const chunks = [];
  for (let i = 0; i < n; i++) {
    const name = `pauta.sqlite.${String(i).padStart(suffixLength, "0")}`;
    const path = join(dir, name);
    const esperado = i < n - 1 ? serverChunkSize : databaseLengthBytes - serverChunkSize * (n - 1);
    if (!existsSync(path)) fail(`falta ${path} (config.json espera ${n} chunks).`);
    const bytes = statSync(path).size;
    if (bytes !== esperado) fail(`${path} mide ${bytes} bytes; config.json espera ${esperado}.`);
    const sha256 = createHash("sha256").update(readFileSync(path)).digest("hex");
    chunks.push({ name, path, bytes, sha256 });
  }

  // Estado de la versión en R2, consultado por la URL pública (la misma que usa
  // el front). Devuelve null si está completa o el motivo por el que hay que
  // subirla. El ?cb= esquiva cualquier caché intermedio (R2 ignora el query).
  async function faltante() {
    const cb = `?cb=${Date.now()}`;
    const r = await fetch(`${base}/${prefijo}manifest.json${cb}`, { cache: "no-store" });
    if (r.status === 404) return "la versión no existe en R2";
    if (!r.ok) throw new Error(`GET ${prefijo}manifest.json -> HTTP ${r.status}`);
    const remoto = await r.json();
    const coincide =
      remoto.version === version &&
      remoto.databaseLengthBytes === databaseLengthBytes &&
      remoto.serverChunkSize === serverChunkSize &&
      remoto.suffixLength === suffixLength &&
      Array.isArray(remoto.chunks) &&
      remoto.chunks.length === n &&
      remoto.chunks.every((c, i) => c.name === chunks[i].name && c.bytes === chunks[i].bytes);
    if (!coincide) {
      fail(`el manifest.json de ${prefijo} en R2 no coincide con este build ` +
        "(misma versión, otra estructura). No piso nada: revisarlo a mano.");
    }
    for (const c of chunks) {
      const h = await fetch(`${base}/${prefijo}${c.name}${cb}`, { method: "HEAD", cache: "no-store" });
      if (h.status === 404) return `falta ${c.name}`;
      if (!h.ok) throw new Error(`HEAD ${prefijo}${c.name} -> HTTP ${h.status}`);
      const largo = Number(h.headers.get("content-length"));
      if (largo !== c.bytes) return `${c.name} mide ${largo} bytes en R2`;
    }
    return null;
  }

  let motivo;
  try {
    motivo = await faltante();
  } catch (e) {
    if (e instanceof Falla) throw e;
    if (!bucket) fail(`no pude verificar ${prefijo} en R2 (${e.message}) y sin R2_BUCKET no la puedo subir.`);
    // Subir de nuevo una versión que ya está es inofensivo: misma versión, mismo
    // contenido (salvo los bytes de meta.generado, ver version_db).
    motivo = `no pude verificar R2 (${e.message}), subo todo`;
    console.warn(`[r2] AVISO: ${motivo}`);
  }

  if (motivo === null) {
    return console.log(`[r2] ${prefijo} ya está completa en R2 (${n} chunks) — no subo nada.`);
  }
  if (!bucket) {
    fail(`config.json apunta a ${prefijo} pero ${motivo} y R2_BUCKET no está seteada: ` +
      "el sitio quedaría sin base.");
  }

  const manifest = {
    version,
    databaseLengthBytes,
    serverChunkSize,
    suffixLength,
    chunks: chunks.map(({ name, bytes, sha256 }) => ({ name, bytes, sha256 })),
    subido: new Date().toISOString(),
    commit: process.env.CF_PAGES_COMMIT_SHA || null,
  };
  mkdirSync(join("etl", "build"), { recursive: true });
  const manifestPath = join("etl", "build", "r2_manifest.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

  function put(key, file, contentType, cacheControl) {
    const args = [
      "--yes", "wrangler", "r2", "object", "put",
      `${bucket}/${key}`,
      `--file=${file}`,
      `--content-type=${contentType}`,
      `--cache-control=${cacheControl}`,
      "--remote",
    ];
    if (DRY_RUN) {
      console.log(`[r2]   (dry-run) npx ${args.map((a) => (/\s/.test(a) ? JSON.stringify(a) : a)).join(" ")}`);
      return;
    }
    execFileSync("npx", args, { stdio: "inherit" });
  }

  const mbTotal = (databaseLengthBytes / 1048576).toFixed(1);
  console.log(`[r2] subiendo ${prefijo} a R2://${bucket} (${motivo}): ${n} chunks, ${mbTotal} MB`);
  for (const c of chunks) {
    console.log(`[r2]   ${c.name}  (${(c.bytes / 1048576).toFixed(1)} MB)`);
    put(`${prefijo}${c.name}`, c.path, "application/octet-stream", CACHE_CHUNKS);
  }
  // Último: con manifest.json la versión cuenta como completa.
  put(`${prefijo}manifest.json`, manifestPath, "application/json", "no-cache");

  if (DRY_RUN) {
    console.log(`[r2] DRY-RUN: no se ejecutó wrangler. Manifest en ${manifestPath}.`);
  } else {
    console.log(`[r2] OK: ${prefijo} publicada (${n} chunks + manifest.json).`);
  }
}

try {
  await main();
} catch (e) {
  if (!(e instanceof Falla)) throw e;
  console.error(`[r2] ERROR: ${e.message}`);
  process.exitCode = 1;
}
