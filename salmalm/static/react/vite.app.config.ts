import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, 'src/app/index.ts'),
      name: 'SalmAlmApp',
      formats: ['iife'],
      fileName: () => 'app.js',
    },
    outDir: resolve(__dirname, '..'),
    emptyOutDir: false,
    minify: false,
  },
});
