import { createServer } from "node:http";
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

// Next's default server ends request bodies after five minutes, even while data arrives.
const server = createServer(
  {
    requestTimeout: uploadSeconds * 1000,
    headersTimeout: Math.min(60000, uploadSeconds * 1000),
    connectionsCheckingInterval: 1000,
  },
  (request, response) => {
    handle(request, response).catch(() => {
      if (!response.headersSent) response.writeHead(500);
      response.end();
    });
  },
);
const app = next({
  dev: process.env.NODE_ENV !== "production",
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
