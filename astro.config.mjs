// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// Datos Pauta Oficial — sitio estatico (Astro + React islands + CSS propio).
// TODO(Fase 3): definir `site` con el dominio final; lo usan el sitemap
// y las URLs canonicas. Dejar comentado hasta tener el dominio.
export default defineConfig({
  // site: 'https://ejemplo.org',
  integrations: [react()],
  vite: {
    // Escape hatch para entornos (CI/sandbox) sin permiso de unlink en
    // node_modules/.vite. En local/Cloudflare se deja sin setear (default).
    cacheDir: process.env.VITE_CACHE_DIR || undefined,
  },
});
