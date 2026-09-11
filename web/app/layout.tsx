import type { Metadata } from "next";
import { connection } from "next/server";
import { applicationOrigin } from "../lib/server-config";
import { AnalyticsProvider } from "@/components/analytics-consent";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  await connection();
  return {
    title: {
      default: "RUSHES — Your footage, in focus",
      template: "%s · RUSHES",
    },
    description:
      "A local footage library, timestamped worklog, and editing workspace.",
    robots: { index: false, follow: false },
    metadataBase: applicationOrigin(),
    openGraph: {
      type: "website",
      title: "RUSHES — Your footage, in focus",
      description:
        "A local footage library, timestamped worklog, and editing workspace.",
    },
    twitter: {
      card: "summary_large_image",
      title: "RUSHES — Your footage, in focus",
    },
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <AnalyticsProvider measurementId={process.env.RUSHES_GA_MEASUREMENT_ID}>{children}</AnalyticsProvider>
      </body>
    </html>
  );
}
