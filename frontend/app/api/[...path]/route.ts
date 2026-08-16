/**
 * Runtime proxy from /api/* to the backend.
 *
 * This replaces a `rewrites()` entry in next.config.ts. Rewrites are
 * resolved during `next build` and written into routes-manifest.json, so
 * the destination is frozen into the build artifact and `BACKEND_URL` has
 * to be present at build time — setting it and restarting silently keeps
 * the old target. Reading it here, per request, means the variable takes
 * effect on a restart like every other setting.
 *
 * Keeping the browser on one origin is still the point: no CORS preflight,
 * and no second hostname for the reviewer's machine to know about.
 *
 * Bodies are streamed rather than buffered, in both directions. Contracts
 * run to 50 MB and the responses include rendered page images and the
 * executed PDF.
 */

import type { NextRequest } from "next/server";

// Never cached, never statically analysed: every call hits the backend.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_BACKEND = "http://127.0.0.1:8000";

/** Hop-by-hop and length headers, which must not be forwarded as-is. */
const STRIP_FROM_REQUEST = [
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "content-length",
  // Ask upstream for an identity encoding so the streamed response cannot
  // disagree with a content-encoding header we pass along.
  "accept-encoding",
];

const STRIP_FROM_RESPONSE = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
];

function backendUrl(): string {
  return (process.env.BACKEND_URL ?? DEFAULT_BACKEND).replace(/\/+$/, "");
}

/** The host this request arrived on, as the browser addressed it. */
function ownHost(request: NextRequest): string {
  return (
    request.headers.get("x-forwarded-host") ??
    request.headers.get("host") ??
    ""
  ).toLowerCase();
}

/**
 * Catch a BACKEND_URL that cannot work, before using it.
 *
 * The dangerous one is a backend address pointing back at this same
 * service: /api/* would forward to /api/* on the same host and recurse
 * until the platform kills it with a 508. Cheap to detect, and impossible
 * to diagnose from the 508 alone.
 */
function configurationProblem(request: NextRequest, backend: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(backend);
  } catch {
    return (
      `BACKEND_URL is not a valid URL: “${backend}”. It should look like ` +
      "https://your-backend.example.com, with no path and no trailing slash."
    );
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return `BACKEND_URL must start with http:// or https://, but is “${backend}”.`;
  }

  const host = ownHost(request);
  if (host && parsed.host.toLowerCase() === host) {
    return (
      `BACKEND_URL points at ${parsed.host}, which is this same service. ` +
      "The frontend would forward /api to itself and loop. Set it to the " +
      "backend service's address instead."
    );
  }

  return null;
}

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const backend = backendUrl();

  const problem = configurationProblem(request, backend);
  if (problem) {
    console.error(`[contract-desk] ${problem}`);
    return Response.json({ detail: problem }, { status: 502 });
  }

  const target = `${backend}/api/${path.join("/")}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);
  for (const name of STRIP_FROM_REQUEST) headers.delete(name);

  const method = request.method.toUpperCase();
  const sendsBody = method !== "GET" && method !== "HEAD";

  // `duplex: "half"` is required by undici whenever the body is a stream.
  const init: RequestInit & { duplex?: "half" } = {
    method,
    headers,
    redirect: "manual",
    ...(sendsBody ? { body: request.body, duplex: "half" as const } : {}),
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error(`[contract-desk] proxy to ${target} failed: ${reason}`);

    const unset = process.env.BACKEND_URL === undefined;
    return Response.json(
      {
        detail: unset
          ? "Could not reach the backend. BACKEND_URL is not set, so this " +
            `is trying ${DEFAULT_BACKEND}, which is correct only when the ` +
            "backend runs alongside the frontend. On a split deployment, " +
            "set BACKEND_URL to the backend's address."
          : `Could not reach the backend at ${backend}. It may be starting ` +
            "up, or the address may be wrong.",
      },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers(upstream.headers);
  for (const name of STRIP_FROM_RESPONSE) responseHeaders.delete(name);

  // Streams straight through: PDF downloads and page previews are binary
  // and can be large.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  return proxy(request, path ?? []);
}

export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
  handle as HEAD,
  handle as OPTIONS,
};
