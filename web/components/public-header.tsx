"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Brand } from "@/components/brand";
import { AppearanceMenu } from "@/components/appearance";
import { Dialog } from "@/components/dialog";
import { api } from "@/lib/api";

export function PublicHeader() {
  const [menu, setMenu] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const request = new AbortController();
    void api("/auth/me", { signal: request.signal }).then(
      () => {
        if (!request.signal.aborted) setSignedIn(true);
      },
      () => {},
    );
    return () => request.abort();
  }, []);
  return (
    <header className="public-header">
      <Brand href={signedIn ? "/app" : "/"} />
      <nav className="public-desktop-nav" aria-label="Main navigation">
        <Link href="/#workflow">How it works</Link>
        <Link href={signedIn ? "/app" : "/login"}>
          {signedIn ? "Your projects" : "Sign in"}
        </Link>
      </nav>
      <AppearanceMenu />
      <button
        ref={menuButton}
        className="icon-button public-menu-button"
        aria-label="Open navigation"
        aria-expanded={menu}
        onClick={() => setMenu(true)}
      >
        <Menu size={22} />
      </button>
      <Dialog
        open={menu}
        onOpenChange={setMenu}
        returnFocusRef={menuButton}
        title="Explore RUSHES"
        description="Find your next step."
      >
        <nav className="public-mobile-nav" aria-label="Mobile navigation">
          <Link href="/#workflow" onClick={() => setMenu(false)}>
            How it works
          </Link>
          <Link
            href={signedIn ? "/app" : "/login"}
            onClick={() => setMenu(false)}
          >
            {signedIn ? "Your projects" : "Sign in"}
          </Link>
          <Link
            href={signedIn ? "/app" : "/signup"}
            className="primary"
            onClick={() => setMenu(false)}
          >
            Start a project
          </Link>
        </nav>
      </Dialog>
    </header>
  );
}
