import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Chemins relatifs : le site fonctionne à la racine d'un domaine comme sous
  // un sous-chemin GitLab Pages (https://utilisateur.gitlab.io/nom-du-projet/).
  base: './',
  // `public/` est réservé au dossier publié par GitLab Pages : les fichiers
  // statiques (Pyodide, service worker, icône) vivent donc dans `static/`.
  publicDir: 'static',
  build: {
    outDir: 'dist',
    target: 'es2022',
    chunkSizeWarningLimit: 600,
  },
  worker: {
    format: 'es',
  },
  test: {
    include: ['tests/unit/**/*.test.ts'],
    environment: 'node',
  },
});
