import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Genuinely standalone from frontend/ (the main dashboard) - its own dev
// server/port, no /api proxy. It calls the FastAPI backend directly over
// the network (see src/lib/api.ts), so the backend has CORS configured for
// this app's origin (see backend/app.py).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 5174 was already taken by an unrelated process on the dev machine
    // this was built on - 5175 is what Vite actually landed on. Change
    // freely; just keep backend/app.py's CORS allow_origins in sync.
    port: 5175,
  },
})
