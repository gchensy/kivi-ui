import type { NextConfig } from "next";

// The browser talks to Next only; /api/* is proxied to the FastAPI backend so
// the session cookie stays same-origin.
const apiOrigin = process.env.KIVI_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  turbopack: {
    root: import.meta.dirname,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
