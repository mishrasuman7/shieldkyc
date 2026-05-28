import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'   // ← the Tailwind v4 plugin

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),   // ← registers Tailwind so it scans your files for classes
  ],
})