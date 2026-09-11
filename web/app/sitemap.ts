import type { MetadataRoute } from "next";
import { applicationOrigin } from "@/lib/server-config";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  // Draft legal/contact pages and all account/workspace routes are noindex.
  return [{ url: new URL("/", applicationOrigin()).href }];
}
