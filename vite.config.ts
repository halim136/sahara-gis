import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'node:fs/promises';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  return {
    publicDir: false as const,
    plugins: [react(), tailwindcss(),{name:'static-map-assets',apply:'build' as const,async closeBundle(){for(const name of ['assets','fonts'])await fs.cp(path.resolve('public',name),path.resolve('dist',name),{recursive:true});}}],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname || '.', '.'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});
