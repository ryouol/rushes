"use client";

import { useEffect, useRef, useTransition } from "react";
import Link from "next/link";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "@/components/landing.css";
import "@/components/legal.css";

export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [error]);
  return (
    <div className="public-document">
      <title>Something went wrong · RUSHES</title>
      <meta
        name="description"
        content="Reload this RUSHES view or return to the home page."
      />
      <meta name="robots" content="noindex, nofollow" />
      <PublicHeader />
      <main id="main" className="recovery-main">
        <span className="document-eyebrow">Something went wrong</span>
        <h1 ref={heading} tabIndex={-1}>
          This view was interrupted.
        </h1>
        <p>Try loading it again, or return to the home page.</p>
        <div className="recovery-actions">
          <button
            className="primary"
            disabled={pending}
            aria-busy={pending}
            onClick={() => startTransition(() => retry())}
          >
            {pending ? "Trying again…" : "Try again"}
          </button>
          <Link href="/" className="secondary">
            Back to home
          </Link>
        </div>
        {pending && (
          <p role="status" className="recovery-status">
            Loading this view again…
          </p>
        )}
        {error.digest && (
          <p className="recovery-reference">Reference: {error.digest}</p>
        )}
      </main>
      <PublicFooter />
    </div>
  );
}
