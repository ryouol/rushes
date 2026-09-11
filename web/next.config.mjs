/** @type {import('next').NextConfig} */
const config = {
  poweredByHeader: false,
  logging: {
    incomingRequests: { ignore: [/^\/api\/auth\/google\/callback\/?(?:\?|$)/] },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default config;
