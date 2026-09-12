import { createServer, request as httpRequest } from "node:http";
import next from "next";

const port = Number(process.env.PORT ?? 3741);
const hostname = process.env.RUSHES_BIND_HOST ?? "127.0.0.1";
const uploadSeconds = Number(process.env.RUSHES_UPLOAD_TIMEOUT_SECONDS ?? 7200);
if (
  !Number.isInteger(port) ||
  port < 1 ||
  port > 65535 ||
  !Number.isInteger(uploadSeconds) ||
  uploadSeconds < 1 ||
  uploadSeconds > 86400
) {
  throw new Error(
    "Invalid PORT or RUSHES_UPLOAD_TIMEOUT_SECONDS configuration",
  );
}

// The Python boundary owns header filtering and trusted ingress identity in both modes.
function proxy(request, response) {
  const upstream = httpRequest({
    hostname: "127.0.0.1", port: 8741, path: request.url,
    method: request.method, headers: request.headers,
  }, (incoming) => {
    response.writeHead(incoming.statusCode, incoming.rawHeaders);
    incoming.pipe(response);
    incoming.on("error", () => response.destroy());
  });
  upstream.on("error", () => {
    if (response.headersSent) return response.destroy();
    response.writeHead(503, { "Content-Type": "application/json", "Cache-Control": "no-store" });
    response.end(JSON.stringify({ detail: "Processing services are disconnected. Retry shortly." }));
  });
  request.on("aborted", () => upstream.destroy());
  response.on("close", () => upstream.destroy());
  request.pipe(upstream);
}

// Next's default server ends request bodies after five minutes, even while data arrives.
const server = createServer(
  {
    requestTimeout: uploadSeconds * 1000,
    headersTimeout: Math.min(60000, uploadSeconds * 1000),
    connectionsCheckingInterval: 1000,
  },
  (request, response) => {
    const path = request.url.split("?", 1)[0];
    if (path === "/api" || path.startsWith("/api/")) {
      proxy(request, response);
      return;
    }
    handle(request, response).catch(() => {
      if (!response.headersSent) response.writeHead(500);
      response.end();
    });
  },
);
const app = next({
  dev: true,
  hostname,
  port,
  httpServer: server,
});
const handle = app.getRequestHandler();
await app.prepare();
server.listen(port, hostname, () =>
  console.log(
    `RUSHES web listening on ${hostname}:${port}; upload duration limit ${uploadSeconds}s`,
  ),
);

let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  const deadline = setTimeout(() => {
    server.closeAllConnections();
    process.exit(1);
  }, 15000).unref();
  const closed = new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
  server.closeIdleConnections();
  try {
    // Next closes development HMR sockets; those otherwise prevent HTTP shutdown.
    await Promise.all([closed, app.close()]);
    clearTimeout(deadline);
    process.exit(0);
  } catch {
    process.exit(1);
  }
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
