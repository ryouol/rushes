import type { MetadataRoute } from "next";
import { applicationOrigin } from "@/lib/server-config";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/app", "/api", "/login", "/signup", "/onboarding"],
    },
    sitemap: new URL("/sitemap.xml", applicationOrigin()).href,
  };
}
