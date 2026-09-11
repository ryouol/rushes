import type { Metadata } from "next";
import { connection } from "next/server";
import { applicationOrigin } from "../lib/server-config";
import localFont from "next/font/local";
import { AppearanceProvider, appearanceScript } from "@/components/appearance";
import { AnalyticsProvider } from "@/components/analytics-consent";
import "./globals.css";

const inter = localFont({ src: "./fonts/InterVariable.woff2", display: "swap", variable: "--font-ui", weight: "100 900" });

export async function generateMetadata(): Promise<Metadata> {
  await connection();
  return {
    title: {
      default: "RUSHES — Your footage. Organized by AI.",
      template: "%s · RUSHES",
    },
    description:
      "Upload footage, let AI categorize what’s inside, and find what you need with natural-language search.",
    robots: { index: true, follow: true },
    metadataBase: applicationOrigin(),
    icons: {
      icon: [{ url: "/icon-16.png", sizes: "16x16", type: "image/png" }, { url: "/icon-32.png", sizes: "32x32", type: "image/png" }],
      apple: [{ url: "/icon-180.png", sizes: "180x180", type: "image/png" }],
    },
    openGraph: {
      type: "website",
      title: "RUSHES — Your footage. Organized by AI.",
      description:
        "Upload footage, let AI categorize what’s inside, and find what you need with natural-language search.",
    },
    twitter: {
      card: "summary_large_image",
      title: "RUSHES — Your footage. Organized by AI.",
      description: "Upload footage, let AI categorize what’s inside, and find what you need with natural-language search.",
    },
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: appearanceScript }} /></head>
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <AppearanceProvider><AnalyticsProvider measurementId={process.env.RUSHES_GA_MEASUREMENT_ID}>{children}</AnalyticsProvider></AppearanceProvider>
      </body>
    </html>
  );
}
