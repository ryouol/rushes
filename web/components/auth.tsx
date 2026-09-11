"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { AppearanceMenu } from "@/components/appearance";
import { Brand } from "@/components/brand";
import { api, ApiError } from "@/lib/api";
import "./auth.css";

type Field = "name" | "email" | "password";
type FieldErrors = Partial<Record<Field, string>>;

function loginDestination() {
  const fallback = "/onboarding";
  const next = new URLSearchParams(window.location.search).get("next");
  if (
    !next ||
    !next.startsWith("/") ||
    next.startsWith("//") ||
    next.includes("\\")
  )
    return fallback;
  try {
    const destination = new URL(next, window.location.origin);
    if (
      destination.origin !== window.location.origin ||
      destination.pathname !== "/app"
    )
      return fallback;
    return `${destination.pathname}${destination.search}`;
  } catch {
    return fallback;
  }
}

function fieldError(field: Field, value: string, signup: boolean) {
  if (field === "name") {
    if (!value.trim()) return "Enter your name.";
    if (Array.from(value.trim()).length > 120)
      return "Use 120 characters or fewer for your name.";
  }
  if (field === "email") {
    if (!value.trim()) return "Enter your email address.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()))
      return "Enter a valid email address.";
  }
  if (field === "password") {
    if (!value) return "Enter your password.";
    const length = Array.from(value).length;
    if (signup && (length < 12 || length > 256))
      return "Use a password between 12 and 256 characters.";
  }
  return undefined;
}

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup";
  const router = useRouter();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const submitting = useRef(false);

  useEffect(() => () => request.current?.abort(), []);

  function validateOnBlur(field: Field, input: HTMLInputElement) {
    if (field !== "password") {
      input.value = input.value.trim();
      if (field === "email") input.value = input.value.toLowerCase();
    }
    setErrors((current) => ({
      ...current,
      [field]: fieldError(field, input.value, signup && !registeredEmail),
    }));
  }

  function validateChangedField(field: Field, value: string) {
    if (errors[field]) {
      setErrors((current) => ({ ...current, [field]: fieldError(field, value, signup && !registeredEmail) }));
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || success) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    const email = String(data.get("email") || "")
      .trim()
      .toLowerCase();
    // Password whitespace is significant and must reach the API unchanged.
    const password = String(data.get("password") || "");
    const values = { name, email, password };
    const fields: Field[] =
      signup && !registeredEmail
        ? ["name", "email", "password"]
        : ["email", "password"];
    const nextErrors: FieldErrors = {};
    for (const field of fields) {
      const message = fieldError(
        field,
        values[field],
        signup && !registeredEmail,
      );
      if (message) nextErrors[field] = message;
    }
    setErrors(nextErrors);
    setError("");
    const firstInvalid = fields.find((field) => nextErrors[field]);
    if (firstInvalid) {
      (form.elements.namedItem(firstInvalid) as HTMLInputElement)?.focus();
      return;
    }

    const controller = new AbortController();
    request.current = controller;
    submitting.current = true;
    setBusy(true);
    let accountCreated = Boolean(registeredEmail);
    let creatingAccount = false;
    try {
      if (signup && !accountCreated) {
        creatingAccount = true;
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ name, email, password }),
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        accountCreated = true;
        creatingAccount = false;
        setRegisteredEmail(email);
      }
      await api("/auth/login", {
        method: "POST",
        body: new URLSearchParams({ username: email, password }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      form.reset();
      setShowPassword(false);
      setSuccess(true);
      router.replace(signup ? "/onboarding" : loginDestination());
    } catch (cause) {
      if (controller.signal.aborted) return;
      const message =
        cause instanceof ApiError
          ? cause.status === 429
            ? "Too many attempts. Wait a moment, then try again."
            : cause.message
          : "We couldn’t connect. Check your connection and try again.";
      if (
        creatingAccount &&
        (!(cause instanceof ApiError) || cause.status >= 500)
      ) {
        setError(
          "We couldn’t confirm whether your account was created. Try signing in before submitting again.",
        );
      } else if (accountCreated) {
        setError(
          `Your account was created, but sign-in didn’t finish. ${message}`,
        );
      } else {
        setError(message);
      }
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <div className={`account-page account-page--${mode}`}>
      <header className="account-header">
        <Brand />
        <AppearanceMenu />
      </header>
      <main id="main" className="account-main">
        <div className="account-content">
          <div className="account-intro">
            <h1>{signup ? "A home for all your footage." : "Welcome back."}</h1>
            <p>
              {signup
                ? "Create your account. Let AI do the organizing."
                : "Sign in to your footage."}
            </p>
          </div>
          <form
            className="account-form"
            onSubmit={submit}
            noValidate
            aria-busy={busy}
          >
            {signup && (
              <div className="account-field">
                <label htmlFor="account-name">Name</label>
                <input
                  id="account-name"
                  name="name"
                  autoComplete="name"
                  required
                  disabled={busy}
                  readOnly={Boolean(registeredEmail)}
                  onChange={(event) => validateChangedField("name", event.currentTarget.value)}
                  onBlur={(event) =>
                    validateOnBlur("name", event.currentTarget)
                  }
                  aria-invalid={Boolean(errors.name)}
                  aria-describedby={
                    errors.name ? "account-name-error" : undefined
                  }
                />
                {errors.name && (
                  <p className="account-field-error" id="account-name-error">
                    {errors.name}
                  </p>
                )}
              </div>
            )}
            <div className="account-field">
              <label htmlFor="account-email">Email</label>
              <input
                id="account-email"
                name="email"
                type="email"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                disabled={busy}
                readOnly={Boolean(registeredEmail)}
                onChange={(event) => validateChangedField("email", event.currentTarget.value)}
                onBlur={(event) => validateOnBlur("email", event.currentTarget)}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={
                  errors.email ? "account-email-error" : undefined
                }
              />
              {errors.email && (
                <p className="account-field-error" id="account-email-error">
                  {errors.email}
                </p>
              )}
            </div>
            <div className="account-field">
              <label htmlFor="account-password">Password</label>
              <div className="account-password">
                <input
                  id="account-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={
                    signup && !registeredEmail
                      ? "new-password"
                      : "current-password"
                  }
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  disabled={busy}
                  onChange={(event) => validateChangedField("password", event.currentTarget.value)}
                  onBlur={(event) =>
                    validateOnBlur("password", event.currentTarget)
                  }
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={
                    [
                      signup ? "account-password-help" : "",
                      errors.password ? "account-password-error" : "",
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                />
                <button
                  type="button"
                  className="account-password-toggle"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  disabled={busy}
                >
                  {showPassword ? (
                    <EyeOff size={21} aria-hidden="true" />
                  ) : (
                    <Eye size={21} aria-hidden="true" />
                  )}
                </button>
              </div>
              {signup && (
                <p className="account-help" id="account-password-help">
                  Use 12–256 characters.
                </p>
              )}
              {errors.password && (
                <p className="account-field-error" id="account-password-error">
                  {errors.password}
                </p>
              )}
            </div>
            {error && (
              <p className="account-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="account-submit"
              type="submit"
              disabled={busy || success}
            >
              {success
                ? "Signed in"
                : busy
                  ? signup && !registeredEmail
                    ? "Creating your account…"
                    : "Signing in…"
                  : signup && !registeredEmail
                    ? "Create account"
                    : "Sign in"}
              {success ? (
                <Check size={20} aria-hidden="true" />
              ) : busy ? (
                <LoaderCircle
                  className="account-spinner"
                  size={20}
                  aria-hidden="true"
                />
              ) : (
                <ArrowRight size={20} aria-hidden="true" />
              )}
            </button>
            <p
              className="account-status"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {success
                ? signup
                  ? "Your account is ready. Opening your projects…"
                  : "Signed in. Opening your projects…"
                : registeredEmail && !busy
                  ? "Your account is ready. Sign in to continue."
                  : ""}
            </p>
          </form>
          <p className="account-switch">
            {signup ? "Already have an account? " : "New to RUSHES? "}
            <Link href={signup ? "/login" : "/signup"}>
              {signup ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </div>
      </main>
      <footer className="account-footer" aria-label="Legal">
        <Link href="/privacy">Privacy</Link>
        <Link href="/terms">Terms</Link>
      </footer>
    </div>
  );
}
