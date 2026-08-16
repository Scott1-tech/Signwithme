import type { NextConfig } from "next";

/**
 * No rewrites here on purpose.
 *
 * /api/* is proxied to the backend by a route handler at
 * app/api/[...path]/route.ts, which reads BACKEND_URL per request. A
 * `rewrites()` entry would be resolved at build time and baked into the
 * build artifact instead, which makes BACKEND_URL a build-time variable
 * and means changing it appears to do nothing until the next rebuild.
 */
const nextConfig: NextConfig = {};

export default nextConfig;
