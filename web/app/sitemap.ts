import type { MetadataRoute } from "next";
import { applicationOrigin } from "@/lib/server-config";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  // Draft legal/contact pages and all account/workspace routes are noindex.
  return [{ url: new URL("/", applicationOrigin()).href }];
}
