import Link from "next/link";
import { pageMetadata } from "@/lib/metadata";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "@/components/landing.css";
import "@/components/legal.css";

export const metadata = pageMetadata(
  "Page not found",
  "This RUSHES page is unavailable. Return home or open your workspace.",
  "/",
);

export default function NotFound() {
  return (
    <div className="public-document">
      <PublicHeader />
      <main id="main" className="recovery-main">
        <span className="document-eyebrow">404 · Page not found</span>
        <h1>This page is out of frame.</h1>
        <p>The link may be incomplete, or the page may have moved.</p>
        <div className="recovery-actions">
          <Link href="/" className="primary">
            Back to home
          </Link>
          <Link href="/app" className="secondary">
            Open workspace
          </Link>
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}
