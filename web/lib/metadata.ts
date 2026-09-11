import type { Metadata } from "next";

export function pageMetadata(title: string, description: string, path: string, index = false): Metadata {
  return {
    title, description,
    alternates: { canonical: path },
    robots: { index, follow: index },
    openGraph: { title: `${title} · RUSHES`, description, url: path, images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RUSHES — Your footage. Organized by AI." }] },
    twitter: { card: "summary_large_image", title: `${title} · RUSHES`, description, images: ["/twitter-image"] },
  };
}
