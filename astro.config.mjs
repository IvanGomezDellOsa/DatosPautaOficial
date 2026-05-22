// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

// Datos Pauta Oficial — sitio estatico (Astro + React islands + Tailwind).
// TODO(Fase 3): definir `site` con el dominio final; lo usan el sitemap
// y las URLs canonicas. Dejar comentado hasta tener el dominio.
export default defineConfig({
  // site: 'https://ejemplo.org',
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
});
