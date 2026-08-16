import type { NextConfig } from "next";

/**
 * The backend runs on 127.0.0.1:8000 and is never exposed to a network.
 * Proxying /api through Next keeps the browser on one origin, so there is
 * no CORS preflight and nothing to configure between the two.
 */
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
