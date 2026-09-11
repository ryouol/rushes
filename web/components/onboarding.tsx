"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, LockKeyhole } from "lucide-react";
import {
  api,
  ApiError,
  type Project,
  type User,
  type Workspace,
} from "@/lib/api";
import { track } from "@/lib/analytics";
import { Brand } from "@/components/brand";
import { AppearanceMenu } from "@/components/appearance";
import "./workspace.css";

type ProjectPage = { items: Project[]; total: number };
type CreationAttempt = {
  name: string;
  workspaceName: string;
  previousWorkspaceIds: string[];
  workspaceId?: string;
};

function projectUrl(workspaceId: string, projectId: string) {
  return `/app?${new URLSearchParams({ workspace: workspaceId, project: projectId })}`;
}

function readAttempt(userId: string): CreationAttempt | null {
  try {
    const value = JSON.parse(
      sessionStorage.getItem(`rushes:onboarding:${userId}`) || "null",
    );
    if (
      value &&
      typeof value.name === "string" &&
      typeof value.workspaceName === "string" &&
      Array.isArray(value.previousWorkspaceIds) &&
      value.previousWorkspaceIds.every(
        (id: unknown) => typeof id === "string",
      ) &&
      (value.workspaceId === undefined || typeof value.workspaceId === "string")
    )
      return value;
  } catch {
    /* Setup remains usable when session storage is unavailable. */
  }
  return null;
}

export function Onboarding() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [stage, setStage] = useState("");
  const attemptRef = useRef<CreationAttempt | null>(null);
  const submitLock = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  function saveAttempt(attempt: CreationAttempt | null, accountId = user?.id) {
    attemptRef.current = attempt;
    if (!accountId) return;
    try {
      if (attempt)
        sessionStorage.setItem(
          `rushes:onboarding:${accountId}`,
          JSON.stringify(attempt),
        );
      else sessionStorage.removeItem(`rushes:onboarding:${accountId}`);
    } catch {
      /* The in-memory attempt still prevents duplicate retries. */
    }
  }

  useEffect(() => {
    const request = new AbortController();
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const account = await api<User>("/auth/me", { signal: request.signal });
        const spaces = await api<Workspace[]>("/workspaces", {
          signal: request.signal,
        });
        const projects = await Promise.all(
          spaces.map(async (space) => ({
            space,
            page: await api<ProjectPage>(
              `/workspaces/${space.id}/projects?limit=1`,
              { signal: request.signal },
            ),
          })),
        );
        if (request.signal.aborted) return;
        const existing = projects.find((entry) => entry.page.total > 0);
        if (existing) {
          saveAttempt(null, account.id);
          router.replace(
            `/app?${new URLSearchParams({ workspace: existing.space.id })}`,
          );
          return;
        }
        const saved = readAttempt(account.id);
        attemptRef.current = saved;
        const destination =
          spaces.find(
            (space) =>
              space.id === saved?.workspaceId && space.role !== "viewer",
          ) ||
          spaces.find((space) => space.role !== "viewer") ||
          null;
        setUser(account);
        setWorkspaces(spaces);
        setWorkspace(destination);
        if (saved?.name) setName(saved.name);
      } catch (failure) {
        if (request.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401)
          router.replace("/login?next=%2Fonboarding");
        else
          setError(
            failure instanceof Error
              ? failure.message
              : "Unable to open setup. Please try again.",
          );
      } finally {
        if (!request.signal.aborted) setLoading(false);
      }
    })();
    return () => request.abort();
  }, [retry, router]);

  useEffect(() => {
    if (!loading && user) headingRef.current?.focus({ preventScroll: true });
  }, [loading, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitLock.current || !user) return;
    const projectName = name.trim();
    if (!projectName) {
      setFieldError("Enter a project name to continue.");
      nameRef.current?.focus();
      return;
    }
    submitLock.current = true;
    setBusy(true);
    setError("");
    setFieldError("");
    setStage("Preparing your project…");
    let attempt = attemptRef.current || {
      name: projectName,
      workspaceName: `${user.name.trim() || "My"} workspace`.slice(0, 120),
      previousWorkspaceIds: workspaces.map((item) => item.id),
      workspaceId: workspace?.id,
    };
    saveAttempt(attempt);
    try {
      // Reconcile before every explicit retry in case a successful response was lost.
      const spaces = await api<Workspace[]>("/workspaces");
      let destination =
        spaces.find(
          (space) =>
            space.id === attempt.workspaceId && space.role !== "viewer",
        ) ||
        spaces.find(
          (space) =>
            !attempt.previousWorkspaceIds.includes(space.id) &&
            space.name === attempt.workspaceName &&
            space.role === "owner",
        ) ||
        spaces.find(
          (space) => space.id === workspace?.id && space.role !== "viewer",
        );
      if (!destination) {
        setStage("Creating your private workspace…");
        destination = await api<Workspace>("/workspaces", {
          method: "POST",
          body: JSON.stringify({ name: attempt.workspaceName }),
        });
        track("workspace_created");
      }
      setWorkspace(destination);
      attempt = { ...attempt, workspaceId: destination.id };
      saveAttempt(attempt);
      const existing = await api<ProjectPage>(
        `/workspaces/${destination.id}/projects?limit=1`,
      );
      if (existing.items.length) {
        saveAttempt(null);
        setStage("Your project is ready. Opening footage…");
        router.replace(projectUrl(destination.id, existing.items[0].id));
        return;
      }
      attempt = { ...attempt, name: projectName };
      saveAttempt(attempt);
      setStage("Creating your project…");
      const created = await api<Project>(
        `/workspaces/${destination.id}/projects`,
        {
          method: "POST",
          body: JSON.stringify({ name: projectName, description: "" }),
        },
      );
      track("project_created");
      saveAttempt(null);
      setStage("Project created. Opening footage…");
      router.replace(projectUrl(destination.id, created.id));
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401)
        router.replace("/login?next=%2Fonboarding");
      else {
        setError(
          `${failure instanceof Error ? failure.message : "We couldn’t create the project."}${attemptRef.current?.workspaceId ? " Your workspace is ready; try again to finish the project." : " Try again to continue setup."}`,
        );
        setStage("");
      }
      submitLock.current = false;
      setBusy(false);
    }
  }

  async function signOut() {
    if (signingOut || submitLock.current) return;
    setSigningOut(true);
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login?signedOut=1");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401)
        router.replace("/login?signedOut=1");
      else
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to sign out. Please try again.",
        );
      setSigningOut(false);
    }
  }

  return (
    <div className="onboarding-shell">
      <header className="onboarding-header">
        <Brand href={user ? "/app" : "/"} />
        <div>
          {user && (
            <button
              className="workspace-quiet"
              disabled={signingOut || busy}
              onClick={() => void signOut()}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          )}
          <AppearanceMenu />
        </div>
      </header>
      <main id="main" className="onboarding-main">
        {loading || (!user && !error) ? (
          <p className="onboarding-loading" role="status">
            <Loader2 size={20} className="workspace-spinner" />
            Preparing your workspace…
          </p>
        ) : !user ? (
          <section className="onboarding-form">
            <h1>Let’s try that again.</h1>
            <p className="error-text" role="alert">
              {error}
            </p>
            <button
              className="secondary"
              onClick={() => setRetry((value) => value + 1)}
            >
              Try again
            </button>
            <Link href="/login">Back to sign in</Link>
          </section>
        ) : (
          <section className="onboarding-form">
            <span className="workspace-eyebrow">Your first project</span>
            <h1 ref={headingRef} tabIndex={-1}>
              What are you working on?
            </h1>
            <p>Name your project. Next, drop in footage for AI to organize.</p>
            <form onSubmit={submit} noValidate>
              <label className="field" htmlFor="first-project-name">
                <span>Project name</span>
                <input
                  id="first-project-name"
                  ref={nameRef}
                  name="name"
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value);
                    if (fieldError) setFieldError("");
                  }}
                  maxLength={120}
                  required
                  disabled={busy || signingOut}
                  autoComplete="off"
                  aria-invalid={Boolean(fieldError)}
                  aria-describedby={
                    fieldError ? "project-name-error" : undefined
                  }
                />
              </label>
              {fieldError && (
                <p id="project-name-error" className="error-text" role="alert">
                  {fieldError}
                </p>
              )}
              {error && (
                <p className="error-text" role="alert">
                  {error}
                </p>
              )}
              <div className="onboarding-action">
                <button className="primary" disabled={busy || signingOut}>
                  {busy ? "Creating project…" : "Create project"}
                  {busy ? (
                    <Loader2 size={20} className="workspace-spinner" />
                  ) : (
                    <ArrowRight size={20} />
                  )}
                </button>
              </div>
              <p className="onboarding-privacy">
                <LockKeyhole size={18} />
                {workspace
                  ? `In ${workspace.name}. Only workspace members have access.`
                  : "Your workspace is private."}
              </p>
              <p className="onboarding-status" role="status" aria-live="polite">
                {stage}
              </p>
            </form>
          </section>
        )}
      </main>
      <footer className="onboarding-footer">
        <span>© {new Date().getFullYear()} RUSHES</span>
        <Link href="/privacy">Privacy</Link>
        <Link href="/terms">Terms</Link>
      </footer>
    </div>
  );
}
