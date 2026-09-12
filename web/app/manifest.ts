export const dynamic = "force-static";

import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "RUSHES",
    short_name: "RUSHES",
    description: "Your footage, organized by AI. Find it by what’s inside.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#faf9f6",
    theme_color: "#0866cf",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}
