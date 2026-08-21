import { NextRequest, NextResponse } from "next/server";

const BACKEND = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  (process.env.BACKEND_PORT
    ? `http://${process.env.BACKEND_HOST || "127.0.0.1"}:${process.env.BACKEND_PORT}`
    : "http://127.0.0.1:8080")
).replace(/\/$/, "");

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

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers.set(key, value);
    }
  });

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
      // @ts-ignore
      signal: isStream ? undefined : AbortSignal.timeout(900_000),
    });

    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      const lowerKey = key.toLowerCase();
      if (!["transfer-encoding", "connection", "set-cookie"].includes(lowerKey)) {
        responseHeaders.set(key, value);
      }
    });

    if (typeof (response.headers as any).getSetCookie === "function") {
      const cookies: string[] = (response.headers as any).getSetCookie();
      for (const cookie of cookies) {
        responseHeaders.append("set-cookie", cookie);
      }
    }

    if (isStream) {
      responseHeaders.set("Content-Type", "text/event-stream");
      responseHeaders.set("Cache-Control", "no-cache, no-transform");
      responseHeaders.set("Connection", "keep-alive");
      responseHeaders.set("X-Accel-Buffering", "no");
    }

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[Serena Proxy] Failed to proxy ${targetUrl}:`, message);
    return NextResponse.json(
      { detail: `Proxy error: ${message}` },
      { status: 502 }
    );
  }
}
