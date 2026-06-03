# Servir la SQLite desde Cloudflare R2 (fix del "malformed")

## Por qué

Cloudflare **Pages no soporta HTTP range requests**: ante un pedido `Range:`
devuelve `200` con el **archivo completo** en vez de `206 Partial Content`
([doc oficial](https://developers.cloudflare.com/pages/configuration/serving-pages/#behavior):
*"Pages currently returns 200 responses for HTTP range requests"*).

sql.js-httpvfs lee la SQLite por rangos. Al recibir el archivo entero, toma
bytes del offset 0 como si fueran de otro offset → SQLite tira **`database disk
image is malformed`**. Es intermitente: el Tiered Cache de Pages sirve 206
cuando el chunk está caliente, pero en frío (incógnito, post-deploy, datacenter
nuevo, expiración de TTL) vuelve a 200 → rompe.

**Cloudflare R2 sí devuelve 206**, así que servimos **solo los chunks
`pauta.sqlite.*` desde R2**. Todo lo demás (HTML/JS/CSS, `config.json`,
`search.json`, `home.json`) se queda en Pages — se baja entero, no usa rangos.

El código ya está listo (`build_db.py` lee `R2_PUBLIC_URL`; `etl/upload_r2.mjs`
sube los chunks en el build). Falta la configuración en el dashboard.

## Pasos (una sola vez)

### 1. Crear el bucket R2
Dashboard de Cloudflare → **R2** → **Create bucket** → nombre: `datospautaoficial-db`.

### 2. Acceso público (r2.dev)
Bucket → **Settings** → **Public access** → habilitar el dominio gestionado
`r2.dev`. Copiar la URL, queda como `https://pub-XXXXXXXX.r2.dev`.

> r2.dev tiene rate limiting (Cloudflare lo throttlea ante abuso). Para tráfico
> de producción conviene, más adelante, conectar un **dominio propio** al bucket
> (ej. `db.datospautaoficial.com.ar`) cuando el apex esté en Cloudflare. Solo hay
> que cambiar `R2_PUBLIC_URL`; el código no cambia.

### 3. CORS del bucket
El front baja los chunks desde otro origen (R2), así que el bucket necesita CORS.
Bucket → **Settings** → **CORS Policy** → pegar (clave: **exponer**
`accept-ranges` y `content-range`, si no sql.js no ve el soporte de rangos):

```json
[
  {
    "AllowedOrigins": ["https://datospautaoficial.pages.dev"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["range", "if-match", "if-none-match"],
    "ExposeHeaders": ["accept-ranges", "content-range", "content-length", "etag"],
    "MaxAgeSeconds": 3600
  }
]
```

> Cuando el sitio pase a un dominio propio, agregar ese origen al array.

### 4. Token de API para subir (wrangler)
Dashboard → **My Profile** → **API Tokens** → **Create Token** → permiso
**"Workers R2 Storage : Edit"** (a nivel cuenta). Guardar el token.
El **Account ID** está en R2 → Overview (o en la URL del dashboard).

### 5. Variables de entorno en Pages
Pages project → **Settings** → **Environment variables** → **Production** (y
Preview si querés que los previews también usen R2):

| Variable | Valor |
|---|---|
| `R2_BUCKET` | `datospautaoficial-db` |
| `R2_PUBLIC_URL` | `https://pub-XXXXXXXX.r2.dev` |
| `CLOUDFLARE_API_TOKEN` | el token del paso 4 |
| `CLOUDFLARE_ACCOUNT_ID` | tu account id |

### 6. Cambiar el build command
Pages → **Settings** → **Builds & deployments** → **Build command**:

```
python3 etl/build_db.py && node etl/upload_r2.mjs && npm run build && rm -f dist/data/pauta.sqlite.*
```

- `build_db.py` genera los chunks y pone `urlPrefix` apuntando a R2 (porque
  `R2_PUBLIC_URL` está seteada).
- `upload_r2.mjs` sube los 9 chunks a R2.
- `rm -f dist/data/pauta.sqlite.*` los saca del deploy de Pages (ya viven en R2;
  evita subir ~167 MB al doble).

### 7. Commit + push
```
git add etl/build_db.py etl/upload_r2.mjs etl/R2_SETUP.md
git commit -m "fix: servir la SQLite desde R2 (Pages no soporta range requests -> 206)"
git push
```

## Cómo verificar
En el sitio, DevTools → Network → un request a `pauta.sqlite.N` debe:
- ir a `pub-XXXX.r2.dev` (no a pages.dev),
- responder **206 Partial Content** con header `content-range`,
- y **no** aparecer el warning `Accept-Ranges=bytes` en consola.

Probá en **incógnito** y con **Cargar más** / ordenar: ya no debe tirar
`database disk image is malformed`.

## Testeo local (sin R2)
`R2_PUBLIC_URL` y `R2_BUCKET` no están seteadas en tu máquina, así que:
- `build_db.py` deja `urlPrefix = /data/pauta.sqlite.` (sirve los chunks locales),
- `upload_r2.mjs` no hace nada.

```
py etl/build_db.py && npm run build && npx http-server dist -p 8080
```
funciona igual que antes.
