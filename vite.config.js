import { defineConfig } from 'vite';

// Static consumer app. `base: './'` keeps every asset URL relative, so the same build
// runs on the web and inside the Android WebView shell (file:///android_asset/).
// The app calls the backend directly at VITE_API_BASE (the backend's CORS allow-list
// must include this origin), so the dev server needs no proxy.
export default defineConfig({
  base: './',
  server: { host: true, port: 5180, strictPort: true },
  preview: { port: 5180, strictPort: true },
  build: { target: 'es2019', sourcemap: true },
});
