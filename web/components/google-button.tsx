"use client";

import { LoaderCircle } from "lucide-react";
import "./google-auth.css";

export function googleAuthError(code: string | null): string {
  switch (code) {
    case "google_cancelled":
      return "Google sign-in was canceled. You can try again or use email.";
    case "google_unavailable":
      return "Google sign-in is unavailable right now. You can continue with email.";
    case "google_invalid":
      return "Your Google sign-in session expired. Please try again.";
    case "google_failed":
      return "Google sign-in didn’t finish. Please try again or use email.";
    case "google_link_required":
      return "An account already uses this email. Sign in with your password, then connect Google in Settings.";
    default:
      return "";
  }
}

export function GoogleButton({
  onClick,
  busy = false,
  disabled = false,
  label = "Continue with Google",
}: {
  onClick: () => void;
  busy?: boolean;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="google-button"
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy}
    >
      <img src="/brand/google-g.png" width={20} height={20} alt="" />
      <span>{busy ? "Opening Google…" : label}</span>
      {busy && (
        <LoaderCircle className="google-spinner" size={18} aria-hidden="true" />
      )}
    </button>
  );
}
