import { NextRequest, NextResponse } from "next/server";

const BACKEND = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000"
).replace(/\/$/, "");

// Use Node.js fetch with no timeout cap — the default Next.js rewrite proxy
// has a very short socket timeout (~5 s) that kills long promote operations
// before the backend finishes. This route handler proxies /api/* with the
// full Node.js fetch which respects the backend's own timeout.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

async function proxyRequest(
  request: NextRequest,
  params: { path: string[] }
) {
  const path = params.path?.join("/") ?? "";
  const url = new URL(request.url);
  const targetUrl = `${BACKEND}/api/${path}${url.search}`;

  // Forward all headers except host
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers.set(key, value);
    }
  });

  // Read body for methods that may have one
  let body: BodyInit | null = null;
  const method = request.method;
  if (!["GET", "HEAD"].includes(method)) {
    body = await request.arrayBuffer();
  }

  try {
    const isStream = path.endsWith("/events");
    const response = await fetch(targetUrl, {
      method,
      headers,
      body: body ?? undefined,
      // @ts-ignore — Allow unbounded streaming for SSE events; 15 mins for bulk operations
      signal: isStream ? undefined : AbortSignal.timeout(900_000),
    });

    // Stream the response back
    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      // Skip headers that Next.js manages itself
      if (!["transfer-encoding", "connection"].includes(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[API Proxy] Failed to proxy ${targetUrl}:`, message);
    return NextResponse.json(
      { detail: `Proxy error: ${message}` },
      { status: 502 }
    );
  }
}
