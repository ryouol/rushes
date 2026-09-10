import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "RUSHES",
    short_name: "RUSHES",
    description: "Local footage library and worklog",
    start_url: "/",
    display: "standalone",
    background_color: "#111315",
    theme_color: "#efb35c",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
