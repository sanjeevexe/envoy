import type { NextConfig } from "next";

// A static export served by Envoy's API (backend/api/app.py serves web/out), so the web app, its API and the live
// view share one origin and the session cookie.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
