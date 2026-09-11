"use client";

import { useEffect, useRef, useTransition } from "react";
import { Brand } from "@/components/brand";
import {
  AppearanceMenu,
  AppearanceProvider,
  appearanceScript,
} from "@/components/appearance";
import "@/components/legal.css";

export default function GlobalError({
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>Something went wrong · RUSHES</title>
        <meta
          name="description"
          content="RUSHES could not open this page. Try again or return home."
        />
        <meta name="robots" content="noindex, nofollow" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script dangerouslySetInnerHTML={{ __html: appearanceScript }} />
      </head>
      <body className="global-recovery">
        <AppearanceProvider>
          <header className="global-recovery-header">
            <Brand />
            <AppearanceMenu />
          </header>
          <main id="main" className="recovery-main">
            <span className="document-eyebrow">Something went wrong</span>
            <h1 ref={heading} tabIndex={-1}>
              Let’s get you back.
            </h1>
            <p>RUSHES couldn’t open this page. Try again or return home.</p>
            <div className="recovery-actions">
              <button
                className="primary"
                disabled={pending}
                aria-busy={pending}
                onClick={() => startTransition(() => retry())}
              >
                {pending ? "Trying again…" : "Try again"}
              </button>
              <a className="secondary" href="/">
                Back to home
              </a>
            </div>
            {pending && (
              <p className="recovery-status" role="status">
                Loading RUSHES again…
              </p>
            )}
            {error.digest && (
              <p className="recovery-reference">Reference: {error.digest}</p>
            )}
          </main>
        </AppearanceProvider>
      </body>
    </html>
  );
}
