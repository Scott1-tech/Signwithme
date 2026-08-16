import type { NextConfig } from "next";

/**
 * Proxying /api through Next keeps the browser on one origin, so there is
 * no CORS preflight and nothing to configure between the two.
 *
 * Locally the backend is on 127.0.0.1:8000 and never exposed to a network.
 * When the two are deployed as separate services, set BACKEND_URL to the
 * backend's address — without it this proxies to localhost inside the
 * frontend's own container, nothing answers, and every /api call fails
 * with a 500 that says nothing about why.
 */
const DEFAULT_BACKEND = "http://127.0.0.1:8000";

// A trailing slash here would produce "//api/..." and 404 everything.
const BACKEND = (process.env.BACKEND_URL ?? DEFAULT_BACKEND).replace(/\/+$/, "");

if (process.env.NODE_ENV === "production" && BACKEND === DEFAULT_BACKEND) {
  console.warn(
    "[contract-desk] BACKEND_URL is not set, so /api is proxying to " +
      `${DEFAULT_BACKEND}. That is correct only if the backend runs in this ` +
      "same container. On a split deployment, set BACKEND_URL to the " +
      "backend service's URL and restart.",
  );
} else {
  console.log(`[contract-desk] proxying /api to ${BACKEND}`);
}

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
