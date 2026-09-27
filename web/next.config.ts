import type { NextConfig } from "next";

// EKALOG_EXPORT=1 -> static export served by the FastAPI container (single port, no Node in the SOC).
// Dev -> Next dev server on :3000 proxying /api to the API on :8000.
const isExport = process.env.EKALOG_EXPORT === "1";

const config: NextConfig = isExport
  ? { output: "export", trailingSlash: true, images: { unoptimized: true } }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
      },
    };

export default config;
