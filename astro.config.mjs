// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// Datos Pauta Oficial — sitio estatico (Astro + React islands + CSS propio).
export default defineConfig({
  site: 'https://datospautaoficial.com.ar',
  integrations: [react()],
  vite: {
    // Escape hatch para entornos (CI/sandbox) sin permiso de unlink en
    // node_modules/.vite. En local/Cloudflare se deja sin setear (default).
    cacheDir: process.env.VITE_CACHE_DIR || undefined,
  },
});
