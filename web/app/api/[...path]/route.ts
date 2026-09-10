import type { NextRequest } from "next/server";
import { isIP } from "node:net";
import { applicationOrigin } from "../../../lib/server-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (request.headers.get("host")?.toLowerCase() !== applicationOrigin().host) {
    return Response.json(
      { detail: "Request host is not allowed" },
      { status: 400 },
    );
  }
  const { path } = await context.params;
  const upstream = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}`,
    "http://127.0.0.1:8741",
  );
  upstream.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of [
    "cookie",
    "content-type",
    "content-length",
    "range",
    "origin",
    "last-event-id",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // The ingress must overwrite this header, and Node must only be reachable through that ingress.
  const clientHeader = process.env.RUSHES_CLIENT_IP_HEADER;
  if (clientHeader) {
    const address = request.headers.get(clientHeader);
    if (address && isIP(address)) headers.set("x-rushes-client-ip", address);
  }
  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      redirect: "manual",
      cache: "no-store",
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      duplex: "half",
      signal: request.signal,
    } as RequestInit & { duplex: "half" });
    const outgoing = new Headers(response.headers);
    outgoing.delete("content-encoding");
    outgoing.delete("transfer-encoding");
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        detail:
          "Processing services are disconnected. Retry shortly or contact the instance operator.",
      },
      { status: 503 },
    );
  }
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PATCH,
  proxy as PUT,
  proxy as DELETE,
  proxy as HEAD,
};
