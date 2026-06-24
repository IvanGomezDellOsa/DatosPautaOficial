[English](README.en.md) | [Español](README.md)

<p align="center">
  <img src="public/logo.webp" alt="Datos Pauta Oficial" width="600">
</p>

# Datos Pauta Oficial — The first and only unified database of Argentine official advertising spending

🌐 **Production deploy:** [datospautaoficial.com.ar](https://datospautaoficial.com.ar)

A public, neutral and open source website that consolidates Argentina's official advertising (pauta) data in a single place: **540,413 advertising orders** from four jurisdictions (Nación, CABA, Provincia de Buenos Aires and Santa Fe), covering 2003–2025, with amounts deflated by inflation so the figures are comparable across years.

**It is the only website that has ever done this.** No other site or media outlet has consolidated, normalized and published this data in a unified, queryable way. The stance is strictly informative: no accusation, no opinion.

---

## 🔍 The differentiator: data that did not exist anywhere else

**No other website unified Argentine official advertising data in a single place.** Until this project, the information was scattered across open data portals, spreadsheets and PDFs from each jurisdiction, in formats incompatible with one another and with no way to compare amounts across years or governments.

**In addition, PBA 2020–2024 is a dataset exclusive to this project.** Provincia de Buenos Aires does not publish its advertising orders in open datasets for that period: the information was buried in individual PDF resolutions. Through a scripted process I extracted the data **resolution by resolution — more than 500 resolutions processed** — to reconstruct the detail of each order (supplier, media outlet, amount, file number). No other website or media outlet has this data.

---

## 📊 Data coverage

| Jurisdicción | Period | Orders |
|---|---|---|
| Nación | 2009–2022 | 225.367 |
| CABA | 2003–2024 | 209.877 |
| Santa Fe | 2008–2023 | 61.187 |
| PBA | 2020–2025 | 43.982 |
| **Total** | **2003–2025** | **540.413** |

Coverage gaps are shown explicitly on the website: aggregates that could mislead due to incomplete coverage are never presented.

---

## 🏗️ Architecture

The project runs **100% without a backend or servers**: the full SQLite database (~173 MB) lives on Cloudflare R2 split into chunks, and the browser queries only the bytes it needs via HTTP Range Requests thanks to `sql.js-httpvfs`. Operating cost: practically zero.

```text
Fuentes oficiales (CSV / Excel / PDF por jurisdicción)
↓
Extractores Python (etl/extractores/extract_{caba,nacion,pba,santa_fe}.py)
↓
unificar.py → CSV canónico (8 columnas, 540.413 filas) → validar.py
↓
build_db.py → SQLite deflactada (IPC INDEC) + caches precomputados
(totals_cache, rankings_cache, groups_cache, home.json)
↓
Chunks de 20 MiB en Cloudflare R2 (db.datospautaoficial.com.ar)
↓
Astro + React islands → consultas SQL desde el navegador (sql.js-httpvfs)
↓
Cloudflare Pages (datospautaoficial.com.ar)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|------|------------|
| **ETL** | Python (modular extractors per jurisdiction, unification, validation) |
| **Database** | Static SQLite, queried from the browser with `sql.js-httpvfs` |
| **Framework** | Astro 6 (static output) + React 19 (islands) |
| **Language** | TypeScript |
| **Search** | MiniSearch (client-side index of suppliers and media outlets) |
| **Hosting** | Cloudflare Pages + Cloudflare R2 (DB chunks) |
| **Deflation** | IPC INDEC (+ Eco Go series 2007–2015), amounts in constant pesos |

---

## 🎯 Features

**Explorable table of 540 thousand orders**
- Cross filters by jurisdiction and year, grouping by supplier/media outlet with expandable rows and pagination of 25 records per page
- Instant first paint: the initial state is precomputed and inlined by Astro (`home.json`) — sql.js initializes only when the user interacts
- The displayed value is the **exact raw value from the official source**, without normalization

**"Cuánto recibió" — entity search**
- Ternary toggle Supplier / Media outlet / **Media group**: the group mode consolidates the corporate names of each holding according to the [Media Ownership Monitor Argentina](https://argentina.mom-gmr.org/), with a transparency panel and disclaimer
- Downloadable 1080×1080 PNG image for sharing on social media, generated with pure Canvas API, no dependencies
- Shareable deeplinks that restore entity, mode and year

**Rankings**
- Top suppliers, media outlets and media groups by jurisdiction and year, served from caches precomputed at build time (no scans over the main table)

**Share the website**
- Button in the navbar (desktop and integrated into the hamburger menu on mobile) with two options: share directly on X or copy the link to the clipboard

**Methodology page**
- Sources, deflation criteria and normalization criteria documented publicly

---

## 🧮 Data decisions

- **Deflated, not nominal amounts.** All amounts are expressed in constant pesos (IPC INDEC). Comparing 2009 advertising spending with 2024 in nominal pesos makes no sense in Argentina.
- **No normalization in the table, transparent normalization in aggregates.** The table shows the exact value from the source. Rankings and "Cuánto recibió" only apply unification of spelling variants of the same corporate name (`aliases.csv`, a conservative curation). Consolidation by ownership (media groups) is an optional, separate toggle with a cited source.
- **Honesty about the gaps.** Every source limitation (rows without a date, partial periods) is documented rather than hidden.

---

## 📝 Development Notes

Development relied heavily on AI throughout the whole cycle: as an engine to speed up production, as a second opinion on technical decisions and as a complement of knowledge in areas outside my expertise.

---

## 👤 Author

**Iván Gómez Dell'Osa**

- Email: [ivangomezdellosa@gmail.com](mailto:ivangomezdellosa@gmail.com)
- LinkedIn: [linkedin.com/in/ivangomezdellosa](https://www.linkedin.com/in/ivangomezdellosa/)
- GitHub: [IvanGomezDellOsa](https://github.com/IvanGomezDellOsa)
