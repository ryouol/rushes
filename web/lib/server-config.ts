import "server-only";

export function applicationOrigin(): URL {
  const origin = new URL(process.env.RUSHES_ORIGIN ?? "http://localhost:3741");
  if (
    origin.href !== `${origin.origin}/` ||
    !["http:", "https:"].includes(origin.protocol) ||
    (origin.protocol !== "https:" &&
      !["localhost", "127.0.0.1"].includes(origin.hostname))
  ) {
    throw new Error(
      "RUSHES_ORIGIN must be a HTTPS origin or a loopback HTTP origin",
    );
  }
  return origin;
}
