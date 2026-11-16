import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

// HTTPS is opt-in for local tenant login. The proxy preserves the browser Host.
const cert = process.env.FACE_MATCH_HTTPS_CERT;
const key = process.env.FACE_MATCH_HTTPS_KEY;
if (!!cert !== !!key) throw new Error("Set both FACE_MATCH_HTTPS_CERT and FACE_MATCH_HTTPS_KEY");
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: process.env.FACE_MATCH_DEV_HOST ? [process.env.FACE_MATCH_DEV_HOST] : [],
    https: cert && key ? { cert: fs.readFileSync(cert), key: fs.readFileSync(key) } : undefined,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
});
