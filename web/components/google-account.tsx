"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, UserRound } from "lucide-react";
import { GoogleButton } from "@/components/google-button";
import { api, ApiError } from "@/lib/api";

type GoogleAccountStatus = {
  available: boolean;
  connected: boolean;
  email: string | null;
};

export function GoogleAccount() {
  const [account, setAccount] = useState<GoogleAccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [callback, setCallback] = useState<string | null>(null);
  const [signInHref, setSignInHref] = useState("");
  const linkRequest = useRef<AbortController | null>(null);
  const submitting = useRef(false);

  useEffect(() => {
    setCallback(new URLSearchParams(window.location.search).get("google"));
    const returned = (event: PageTransitionEvent) => {
      if (event.persisted) {
        submitting.current = false;
        setBusy(false);
        setRevision((value) => value + 1);
      }
    };
    window.addEventListener("pageshow", returned);
    return () => {
      linkRequest.current?.abort();
      window.removeEventListener("pageshow", returned);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setAccount(null);
    setError("");
    setSignInHref("");
    void api<GoogleAccountStatus>("/auth/google/account", {
      signal: controller.signal,
    }).then(
      (status) => {
        if (!controller.signal.aborted) {
          setAccount(status);
          setLoading(false);
        }
      },
      (cause) => {
        if (controller.signal.aborted) return;
        setLoading(false);
        if (cause instanceof ApiError && cause.status === 401) {
          setError("Sign in again to manage your Google connection.");
          setSignInHref(
            `/login?next=${encodeURIComponent("/app?view=settings")}`,
          );
        } else {
          setError("Your Google connection couldn’t load. Please try again.");
        }
      },
    );
    return () => controller.abort();
  }, [revision]);

  async function connect() {
    if (submitting.current || !account?.available || account.connected) return;
    submitting.current = true;
    const controller = new AbortController();
    linkRequest.current = controller;
    const location = window.location.href;
    setBusy(true);
    setError("");
    setCallback(null);
    try {
      const response = await api<{ authorization_url: string }>(
        "/auth/google/link",
        {
          method: "POST",
          signal: controller.signal,
        },
      );
      if (controller.signal.aborted) return;
      if (window.location.href !== location) {
        submitting.current = false;
        setBusy(false);
        return;
      }
      const destination = new URL(response.authorization_url);
      if (
        destination.protocol !== "https:" ||
        destination.hostname !== "accounts.google.com" ||
        destination.username ||
        destination.password
      )
        throw new Error("Invalid Google destination");
      window.location.assign(destination.href);
    } catch (cause) {
      if (controller.signal.aborted) return;
      submitting.current = false;
      setBusy(false);
      if (cause instanceof ApiError && cause.status === 401) {
        setError("Sign in again to connect your Google account.");
        setSignInHref(
          `/login?next=${encodeURIComponent("/app?view=settings")}`,
        );
      } else {
        setError("Google couldn’t open. Please try again.");
      }
    }
  }

  return (
    <section
      className="settings-card google-account"
      aria-labelledby="google-account-heading"
    >
      <h2 id="google-account-heading">
        <UserRound size={21} /> Your sign-in
      </h2>
      <p className="muted small">
        Your personal account, across all workspaces.
      </p>
      {loading ? (
        <p className="muted small" role="status">
          Checking your Google connection…
        </p>
      ) : account?.connected ? (
        <>
          <p className="google-account-connected">
            <Check size={18} aria-hidden="true" /> Google connected
          </p>
          {account.email && (
            <p className="google-account-address muted small">
              {account.email}
            </p>
          )}
          <p className="muted small">
            {account.available
              ? "You can use Google to sign in to this RUSHES account."
              : "Google sign-in is temporarily unavailable."}
          </p>
          {callback === "linked" && (
            <p className="notice" role="status">
              Google is connected. Your footage and workspace access stay with
              this account.
            </p>
          )}
        </>
      ) : account?.available ? (
        <>
          <p className="muted small">
            Connect Google to sign in to this account with one click. Your
            password will still work.
          </p>
          <GoogleButton
            label="Connect Google"
            onClick={() => void connect()}
            busy={busy}
            disabled={Boolean(signInHref)}
          />
        </>
      ) : account ? (
        <p className="muted small">
          Google sign-in is unavailable right now. Your current sign-in method
          still works.
        </p>
      ) : null}
      {!loading && callback === "cancelled" && (
        <p className="notice" role="status">
          Connecting Google was canceled. Your sign-in details haven’t changed.
        </p>
      )}
      {!loading && callback === "link_failed" && (
        <p className="notice danger" role="alert">
          Google couldn’t connect. Try again, or use a different Google account.
        </p>
      )}
      {error && (
        <p className="notice danger" role="alert">
          {error}
        </p>
      )}
      {signInHref ? (
        <Link className="secondary google-account-retry" href={signInHref}>
          Sign in again
        </Link>
      ) : (
        !loading &&
        !account && (
          <button
            className="secondary google-account-retry"
            onClick={() => setRevision((value) => value + 1)}
          >
            Try again
          </button>
        )
      )}
    </section>
  );
}
