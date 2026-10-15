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
sube los chunks en el build). Lo que sigue es la configuración del dashboard.

### Un solo chunk

La base va en **un solo chunk** (`pauta.sqlite.0`, ~173 MB). Los chunks de
20 MiB existían por el límite de 25 MiB por archivo de Pages, que no aplica a
R2, y además rompían consultas: sql.js-httpvfs manda cada lectura al chunk
donde empieza, y cuando su lectura anticipada cruzaba el borde entre dos
chunks, R2 la cortaba en el fin del archivo y la página pedida no llegaba
(`database disk image is malformed` al filtrar por infobae o lapoliticaonline).
Con un chunk no hay borde. El resto (versionado, manifest, `suffixLength`) sigue
igual con N = 1. Tope: `wrangler r2 object put` sube hasta 300 MiB por objeto;
`build_db.py` corta el build si la base lo supera (habría que pasar a subida
multipart, no volver a partirla).

## Versionado de los chunks

Los chunks se publican bajo un prefijo por versión:

```
v/<version>/pauta.sqlite.0 … pauta.sqlite.N
v/<version>/manifest.json
```

**Por qué.** Antes cada build pisaba `pauta.sqlite.N` en la raíz del bucket, y
lo hacía *antes* de que Pages publicara el deploy nuevo. Si los datos cambiaban,
una pestaña abierta (o un caché) podía leer páginas de dos builds distintos →
`malformed` o resultados mezclados. Ahora:

- **Una versión no se pisa nunca.** `upload_r2.mjs` sube `v/<version>/` una sola
  vez; si ya está completa en R2, no sube nada.
- **El cambio de versión lo hace `config.json`**, que viaja con el deploy de
  Pages (`max-age=0, must-revalidate`). Subir a R2 antes de que Pages publique
  es inofensivo: nadie referencia todavía la versión nueva. El worker lee
  `config.json` una vez al arrancar, así que una pestaña abierta sigue leyendo
  entera la versión vieja.
- **Los chunks van con `Cache-Control: public, max-age=31536000, immutable`**
  (el nombre ya fija el contenido). `manifest.json` va con `no-cache`: lo lee
  solo el build.
- **`manifest.json` se sube último**: que exista marca la versión como
  completa. Un build que se corta a mitad de la subida deja chunks sin manifest;
  el próximo build los vuelve a subir todos.

**Qué es `<version>`.** Los primeros 16 hex del sha256 de `pauta.sqlite`,
calculado con el texto de `meta.generado` (la hora del build) puesto en ceros
(`version_db` en `build_db.py`). Verificado: dos builds seguidos con las mismas
entradas difieren solo en esos bytes, así que dan la misma versión y el deploy
no vuelve a subir 173 MB. Cualquier otro byte distinto da otra versión: un dato,
un índice, o una versión distinta de SQLite (la base de producción, armada con
la SQLite 3.37.2 de Cloudflare, no es byte a byte igual a una local con 3.45.3,
aunque las entradas sean las mismas). Por eso no se usa un hash de los CSV de
entrada: daría la misma versión a bases distintas (por ejemplo, al sacar un
índice sin tocar los CSV).

**Qué hace `upload_r2.mjs`.** Lee `config.json` y sube exactamente las claves que
va a pedir el front (`urlPrefix` + número de chunk). Antes de subir, consulta la
versión por la URL pública (`manifest.json` + `HEAD` de cada chunk):

| Estado en R2 | Qué hace |
|---|---|
| completa (manifest + todos los chunks con su tamaño) | no sube nada |
| no existe, o le falta algún chunk | sube todos los chunks y después el manifest |
| manifest con otra estructura (largo, chunks) | **falla** sin pisar nada |
| no responde | sube todo (es inofensivo: misma versión, mismo contenido) |

Además falla si `R2_BUCKET` está seteada pero `config.json` tiene un `urlPrefix`
local (falta `R2_PUBLIC_URL`), o si `config.json` apunta a una versión que no
está en R2 y no hay `R2_BUCKET` para subirla. `check_build.py` verifica que, con
`R2_BUCKET`, el `urlPrefix` sea absoluto y versionado.

## Pasos (una sola vez)

### 1. Crear el bucket R2
Dashboard de Cloudflare → **R2** → **Create bucket** → nombre: `datospautaoficial-db`.

### 2. Acceso público
Producción usa un **dominio propio** conectado al bucket:
`https://db.datospautaoficial.com.ar` (bucket → **Settings** → **Custom Domains**).

> La alternativa es el dominio gestionado `r2.dev` (bucket → **Settings** →
> **Public access**), pero tiene rate limiting: no sirve para producción.

### 3. CORS del bucket
El front baja los chunks desde otro origen (R2), así que el bucket necesita CORS.
Bucket → **Settings** → **CORS Policy** → pegar (clave: **exponer**
`accept-ranges` y `content-range`, si no sql.js no ve el soporte de rangos):

```json
[
  {
    "AllowedOrigins": ["https://datospautaoficial.com.ar", "https://datospautaoficial.pages.dev"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["range", "if-match", "if-none-match"],
    "ExposeHeaders": ["accept-ranges", "content-range", "content-length", "etag"],
    "MaxAgeSeconds": 3600
  }
]
```

El prefijo `v/` no cambia nada de CORS: es el mismo origen.

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
| `R2_PUBLIC_URL` | `https://db.datospautaoficial.com.ar` |
| `CLOUDFLARE_API_TOKEN` | el token del paso 4 |
| `CLOUDFLARE_ACCOUNT_ID` | tu account id |

En Preview, las cuatro o ninguna. Con `R2_PUBLIC_URL` y sin `R2_BUCKET`, el
build solo pasa si esa versión ya está en R2 (por ejemplo, la subió producción).

### 6. Build command
Pages → **Settings** → **Builds & deployments** → **Build command**. Recomendado:

```
python3 etl/build_db.py && npm run build && rm -f dist/data/pauta.sqlite.* && python3 etl/check_build.py && node etl/upload_r2.mjs
```

- `build_db.py` genera los chunks y pone `urlPrefix` apuntando a
  `R2_PUBLIC_URL/v/<version>/` (porque `R2_PUBLIC_URL` está seteada).
- `npm run build` arma el sitio; `rm -f dist/data/pauta.sqlite.*` saca los chunks
  del deploy de Pages (viven en R2; evita subir ~173 MB al doble).
- `check_build.py` valida config, chunks, límites de Pages y que el `urlPrefix`
  sea de R2 y versionado.
- `upload_r2.mjs` va último: solo sube si todo lo anterior pasó (menos versiones
  huérfanas). Tiene que terminar antes de que Pages publique, y eso está
  garantizado porque es parte del build.

El command anterior
(`python3 etl/build_db.py && node etl/upload_r2.mjs && npm run build && rm -f dist/data/pauta.sqlite.*`)
también funciona con el versionado; el nuevo agrega `check_build.py` y deja la
subida para el final.

## Migración desde los chunks sin versionar (una sola vez)

Hasta este cambio el bucket tenía los chunks en la raíz (`pauta.sqlite.0` …
`pauta.sqlite.8`), sin `Cache-Control`.

1. **Revisar las reglas de lifecycle del bucket** (dashboard → bucket →
   Settings → Object lifecycle rules, o
   `npx wrangler r2 bucket lifecycle list datospautaoficial-db`). Si hay una
   regla que borra objetos por antigüedad sobre todo el bucket o sobre `v/`,
   **sacarla**: borraría la versión en vivo (ver Limpieza). La regla por defecto
   que aborta multipart uploads incompletos no molesta.
2. (Opcional) Cambiar el build command al recomendado del paso 6.
3. Mergear y dejar que Pages buildee. En el log del build tiene que aparecer
   `[r2] subiendo v/<version>/ … (la versión no existe en R2)` y al final
   `[r2] OK: v/<version>/ publicada`.
4. Verificar (ver *Cómo verificar*): `config.json` en producción apunta a
   `…/v/<version>/pauta.sqlite.` y los chunks responden 206 con
   `Cache-Control: … immutable`.
5. **No borrar todavía los chunks de la raíz.** Las pestañas abiertas antes del
   deploy los siguen leyendo, y un rollback de Pages a un deploy anterior a la
   migración vuelve a apuntar ahí. El código nuevo nunca los toca, así que ya
   no cambian. Borrarlos (los 9 objetos `pauta.sqlite.N` de la raíz) recién
   cuando ya no quieras poder volver a un deploy anterior a la migración.

## Limpieza de versiones viejas

Cada cambio de datos (o de índices, o de la versión de SQLite del build) deja
una versión nueva de ~173 MB. Las viejas se borran **a mano**, nunca con una
regla automática por antigüedad.

**Por qué no lifecycle por antigüedad.** Las reglas de R2 miran solo prefijo y
edad desde la subida, no si la versión está en uso. Como una versión no se
vuelve a subir mientras los datos no cambian, la versión en vivo envejece igual
que las viejas: con datos quietos varios meses, una regla de "borrar en `v/` lo
de más de 90 días" borraría la base en vivo y el sitio quedaría sin datos.

**Procedimiento seguro:**

1. Ver la versión en vivo:
   ```
   curl -s https://datospautaoficial.com.ar/data/config.json
   ```
   (`urlPrefix` → `…/v/<version>/pauta.sqlite.`).
2. Decidir hasta dónde querés poder hacer rollback en Pages: cada deploy apunta a
   la versión con la que se buildeó (su `config.json` está en
   `https://<deploy>.datospautaoficial.pages.dev/data/config.json`). Conservar la
   versión en vivo y las de los deploys a los que podrías volver (por ejemplo,
   las 2 anteriores). Los previews también apuntan a su propia versión.
3. En el dashboard (bucket → Objects → carpeta `v/`) listar las versiones; el
   `manifest.json` de cada una tiene la fecha de subida (`subido`) y el commit.
4. Borrar solo los objetos de las carpetas `v/<version>/` que no estén en la
   lista del paso 2. Antes de borrar, volver a correr el paso 1 (que no haya
   entrado un deploy nuevo mientras tanto).

Si se borra por error la versión en vivo, un build nuevo del mismo commit
(Retry deployment) la arregla: o la vuelve a subir (no está completa → sube
todo) o, si cambió el entorno de build, publica otra versión y apunta a esa.

## Cómo verificar
En el sitio, DevTools → Network → un request a `pauta.sqlite.N` debe:
- ir a `db.datospautaoficial.com.ar/v/<version>/` (no a pages.dev ni a la raíz
  del bucket),
- responder **206 Partial Content** con header `content-range`,
- traer `cache-control: public, max-age=31536000, immutable`,
- y **no** aparecer el warning `Accept-Ranges=bytes` en consola.

Desde la terminal:
```
curl -s https://datospautaoficial.com.ar/data/config.json
curl -sI -r 0-15 https://db.datospautaoficial.com.ar/v/<version>/pauta.sqlite.0
```

Probá en **incógnito** y con **Cargar más** / ordenar: ya no debe tirar
`database disk image is malformed`.

> Sobre el caché: `immutable` hace que cualquier caché que guarde un chunk no
> pueda servir nunca contenido viejo o mezclado. En una prueba local con
> Chromium, las lecturas por rango del worker igual se volvieron a pedir al
> recargar, así que no esperes menos requests en visitas repetidas. **No**
> agregar una Cache Rule de Cloudflare ("Cache Everything") sobre
> `db.datospautaoficial.com.ar` sin probar antes, en frío, que un pedido con
> `Range:` siga devolviendo 206: es el mismo problema que tenía Pages.

## Testeo local (sin R2)
`R2_PUBLIC_URL` y `R2_BUCKET` no están seteadas en tu máquina, así que:
- `build_db.py` deja `urlPrefix = /data/pauta.sqlite.` (sirve los chunks locales),
- `upload_r2.mjs` no hace nada.

```
py etl/build_db.py && npm run build && npx http-server dist -p 8080
```
funciona igual que antes.

Para ver qué subiría un build de producción, sin credenciales, con
`--dry-run` (valida los chunks contra `config.json`, consulta R2 por la URL
pública —solo lectura— e imprime los comandos de wrangler sin correrlos). En
Git Bash:

```
R2_PUBLIC_URL=https://db.datospautaoficial.com.ar py etl/build_db.py
R2_BUCKET=datospautaoficial-db R2_PUBLIC_URL=https://db.datospautaoficial.com.ar node etl/upload_r2.mjs --dry-run
```

Ojo: eso deja `public/data/config.json` apuntando a R2 con la versión de *tu*
build (que no está subida). Volvé a correr `py etl/build_db.py` sin
`R2_PUBLIC_URL` antes de probar el sitio local.
