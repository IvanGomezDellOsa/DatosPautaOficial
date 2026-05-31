#!/usr/bin/env python3
"""check_build.py — valida que el build este listo para deployar a Cloudflare Pages.

Corre DESPUES de `python3 etl/build_db.py && npm run build`.

Verifica:
  1. config.json es JSON valido y tiene todos los campos requeridos.
  2. Los chunks suman exactamente databaseLengthBytes (build consistente).
  3. Ningun archivo en dist/ supera 25 MiB (limite duro de CF Pages).
  4. El monolitico pauta.sqlite NO esta en dist/ (lo bloquearia en CF Pages).

Uso:
  py etl/check_build.py        # Windows
  python3 etl/check_build.py   # Linux/Mac

Retorna exit code 0 si todo esta OK, 1 si hay algun problema.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CF_LIMIT = 25 * 1024 * 1024  # 25 MiB en bytes

ok = True

def check(label, passed, detail=""):
    global ok
    icon = "OK " if passed else "ERR"
    print(f"  {icon}  {label}" + (f"\n       {detail}" if detail else ""))
    if not passed:
        ok = False

print("\n── Validando build para Cloudflare Pages ──\n")

# ── 1. config.json válido ────────────────────────────────────────────────────
config_path = REPO / "public" / "data" / "config.json"
config = None
if not config_path.exists():
    check("config.json existe", False, f"No encontrado en {config_path}")
else:
    try:
        config = json.loads(config_path.read_text())
        campos = ["requestChunkSize", "serverMode", "urlPrefix",
                  "serverChunkSize", "databaseLengthBytes", "suffixLength"]
        faltantes = [c for c in campos if c not in config]
        check("config.json es JSON válido y completo",
              not faltantes,
              f"Faltan campos: {faltantes}" if faltantes else "")
    except json.JSONDecodeError as e:
        check("config.json es JSON válido y completo", False, f"JSON inválido: {e}")

# ── 2. Chunks consistentes con config.json ───────────────────────────────────
if config:
    prefix = REPO / "public" / "data" / "pauta.sqlite."
    suffix_len = config.get("suffixLength", 1)
    db_size_esperado = config.get("databaseLengthBytes", 0)
    server_chunk = config.get("serverChunkSize", 0)
    n_chunks_esperado = -(-db_size_esperado // server_chunk)  # ceil division

    chunks = sorted(REPO.glob("public/data/pauta.sqlite.*"))
    chunks = [c for c in chunks if c.suffix.lstrip(".").isdigit()]

    check(f"Cantidad de chunks ({len(chunks)} encontrados, {n_chunks_esperado} esperados)",
          len(chunks) == n_chunks_esperado,
          f"Chunks: {[c.name for c in chunks]}" if len(chunks) != n_chunks_esperado else "")

    total_bytes = sum(c.stat().st_size for c in chunks)
    check(f"Suma de chunks == databaseLengthBytes ({total_bytes:,} == {db_size_esperado:,})",
          total_bytes == db_size_esperado,
          f"Diferencia: {total_bytes - db_size_esperado:+,} bytes — build inconsistente, regenerá la DB" if total_bytes != db_size_esperado else "")

# ── 3. Ningún archivo en dist/ supera 25 MiB ─────────────────────────────────
dist = REPO / "dist"
if not dist.exists():
    check("dist/ existe", False, "Corré npm run build primero")
else:
    grandes = [(f, f.stat().st_size) for f in dist.rglob("*")
               if f.is_file() and f.stat().st_size > CF_LIMIT]
    if grandes:
        detalle = "\n       ".join(
            f"{f.relative_to(dist)}  ({s / 1024 / 1024:.1f} MiB)" for f, s in grandes
        )
        check("Ningún archivo en dist/ supera 25 MiB", False, detalle)
    else:
        check("Ningún archivo en dist/ supera 25 MiB", True)

# ── 4. Monolítico pauta.sqlite NO está en dist/ ──────────────────────────────
monolito = dist / "data" / "pauta.sqlite"
check("dist/data/pauta.sqlite NO existe (bloquearía deploy)",
      not monolito.exists(),
      "Borralo con: del dist\\data\\pauta.sqlite" if monolito.exists() else "")

# ── Resultado final ───────────────────────────────────────────────────────────
print()
if ok:
    print("  ✓  Todo OK — podés deployar a Cloudflare Pages.\n")
else:
    print("  ✗  Hay problemas — no deployar hasta resolverlos.\n")

sys.exit(0 if ok else 1)
