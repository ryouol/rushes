"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  Layers3,
  Loader2,
  LogOut,
  Menu,
  Plus,
  Settings2,
  X,
} from "lucide-react";
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
import { Dialog } from "@/components/dialog";
import { ProjectView } from "@/components/project";
import { SettingsView } from "@/components/settings";
import { GoogleAccount } from "@/components/google-account";
import { DeleteDialog, type DeleteTarget } from "@/components/delete-dialog";
import "./workspace.css";

const PAGE_SIZE = 40;
type ProjectPage = { items: Project[]; total: number };

export function workspaceHref(
  workspace: string,
  options: { project?: string; settings?: boolean; page?: number } = {},
) {
  const params = new URLSearchParams({ workspace });
  if (options.project) params.set("project", options.project);
  if (options.settings) params.set("view", "settings");
  if (options.page) params.set("page", String(options.page));
  return `/app?${params}`;
}

export function WorkspaceLoading() {
  return (
    <main id="main" className="workspace-opening">
      <Brand href="/app" label="RUSHES dashboard" />
      <div role="status">
        <Loader2 size={20} className="workspace-spinner" /> Opening your
        workspace…
      </div>
    </main>
  );
}

export function Rushes() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace") || "";
  const projectId = searchParams.get("project") || "";
  const settingsOpen = searchParams.get("view") === "settings";
  const googleResult = searchParams.get("google");
  const rawPage = Number(searchParams.get("page") || 0);
  const projectPage =
    Number.isSafeInteger(rawPage) && rawPage >= 0
      ? Math.min(rawPage, 1000000)
      : 0;
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const accountOnly = workspaces.length === 0;
  const [loading, setLoading] = useState(true);
  const [accountRetry, setAccountRetry] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pageData, setPageData] = useState<
    (ProjectPage & { key: string }) | null
  >(null);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsFailed, setProjectsFailed] = useState(false);
  const [project, setProject] = useState<
    (Project & { workspaceId: string }) | null
  >(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [dialog, setDialog] = useState<"project" | "workspace" | null>(null);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const submitLock = useRef(false);
  const mainRef = useRef<HTMLDivElement>(null);
  const workspace =
    workspaces.find((item) => item.id === workspaceId) ||
    (!workspaceId ? workspaces[0] : undefined);
  const pageKey = `${user?.id}:${workspace?.id}:${projectPage}:${revision}`;
  const projects = pageData?.key === pageKey ? pageData.items : [];
  const projectTotal = pageData?.key === pageKey ? pageData.total : 0;
  const activeProject =
    project && project.workspaceId === workspace?.id && project.id === projectId
      ? project
      : null;
  const hasRetainedProject = activeProject !== null;
  const locationKey = `${workspaceId}:${projectId}:${settingsOpen}:${projectPage}`;

  const handleFailure = useCallback(
    (failure: unknown) => {
      if (
        failure instanceof ApiError &&
        (failure.status === 401 || failure.status === 403)
      ) {
        setProject(null);
        setPageData(null);
        setProjectsFailed(true);
      }
      if (failure instanceof ApiError && failure.status === 401) {
        const next = `${window.location.pathname}${window.location.search}`;
        router.replace(`/login?next=${encodeURIComponent(next)}`);
        setUser(null);
        return;
      }
      setError(
        failure instanceof Error
          ? failure.message
          : "Something went wrong. Please try again.",
      );
    },
    [router],
  );

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
        if (request.signal.aborted) return;
        setUser(account);
        setWorkspaces(spaces);
      } catch (failure) {
        if (!request.signal.aborted) handleFailure(failure);
      } finally {
        if (!request.signal.aborted) setLoading(false);
      }
    })();
    return () => request.abort();
  }, [accountRetry, handleFailure, router]);

  useEffect(() => {
    if (!loading && user && accountOnly && !settingsOpen)
      router.replace("/onboarding");
  }, [loading, user, accountOnly, settingsOpen, router]);

  useEffect(() => {
    if (workspace && !workspaceId) {
      const destination = workspaceHref(workspace.id, {
        project: projectId || undefined,
        settings: settingsOpen,
        page: projectPage,
      });
      const result =
        settingsOpen &&
        ["linked", "cancelled", "link_failed"].includes(googleResult || "")
          ? `&google=${googleResult}`
          : "";
      router.replace(destination + result, { scroll: false });
    }
  }, [
    workspace,
    workspaceId,
    projectId,
    settingsOpen,
    projectPage,
    googleResult,
    router,
  ]);

  useEffect(() => {
    if (!user || !workspace) return;
    const request = new AbortController();
    setProjectsLoading(true);
    setProjectsFailed(false);
    void api<ProjectPage>(
      `/workspaces/${workspace.id}/projects?offset=${projectPage * PAGE_SIZE}&limit=${PAGE_SIZE}`,
      { signal: request.signal },
    )
      .then((data) => {
        if (request.signal.aborted) return;
        if (projectPage > 0 && projectPage * PAGE_SIZE >= data.total) {
          // Keep a destination selected while this library request was pending.
          const params = new URLSearchParams(window.location.search);
          const lastPage = Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1);
          if (lastPage) params.set("page", String(lastPage));
          else params.delete("page");
          router.replace(`/app?${params}`, { scroll: false });
          return;
        }
        setPageData({ ...data, key: pageKey });
      })
      .catch((failure) => {
        if (!request.signal.aborted) {
          setProjectsFailed(true);
          handleFailure(failure);
        }
      })
      .finally(() => {
        if (!request.signal.aborted) setProjectsLoading(false);
      });
    return () => request.abort();
    // A project or settings change uses the same library page; it must not reload the list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, workspace?.id, projectPage, revision, handleFailure, router]);

  useEffect(() => {
    if (!user || !workspace || !projectId || settingsOpen) return;
    // Every library refresh gets a new key. Wait for its result before scanning.
    if (pageData?.key !== pageKey || projectsFailed) {
      setProjectLoading(!projectsFailed);
      return;
    }
    const request = new AbortController();
    setProjectLoading(true);
    const workspaceAtStart = workspace.id;
    void (async () => {
      try {
        const cached = pageData.items.find((item) => item.id === projectId);
        if (cached) {
          setProject((current) =>
            current?.workspaceId === workspaceAtStart &&
            current.id === cached.id &&
            current.name === cached.name &&
            current.description === cached.description &&
            current.created_at === cached.created_at
              ? current
              : { ...cached, workspaceId: workspaceAtStart },
          );
          return;
        }
        const completeLibrary = pageData.items.length >= pageData.total;
        if (!completeLibrary && hasRetainedProject) return;
        // Deep links can outlive their page position when newer projects are added.
        let offset = 0;
        while (!completeLibrary && !request.signal.aborted) {
          const data = await api<ProjectPage>(
            `/workspaces/${workspaceAtStart}/projects?offset=${offset}&limit=100`,
            { signal: request.signal },
          );
          if (request.signal.aborted) return;
          const found = data.items.find((item) => item.id === projectId);
          if (found) {
            setProject({ ...found, workspaceId: workspaceAtStart });
            return;
          }
          offset += data.items.length;
          if (!data.items.length || offset >= data.total) break;
        }
        setProject(null);
        setError(
          "This project is no longer available in this workspace. Return to Projects to choose another.",
        );
      } catch (failure) {
        if (!request.signal.aborted) handleFailure(failure);
      } finally {
        if (!request.signal.aborted) setProjectLoading(false);
      }
    })();
    return () => request.abort();
  }, [
    user?.id,
    workspace?.id,
    projectId,
    settingsOpen,
    pageData,
    pageKey,
    projectsFailed,
    hasRetainedProject,
    handleFailure,
  ]);

  useEffect(() => {
    setMobileOpen(false);
    setDeleteTarget(null);
    setError("");
    mainRef.current?.focus({ preventScroll: true });
  }, [locationKey, user]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function signOut() {
    if (signingOut || submitLock.current) return;
    setSigningOut(true);
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login?signedOut=1");
      setUser(null);
    } catch (failure) {
      handleFailure(failure);
      setSigningOut(false);
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      submitLock.current ||
      !dialog ||
      (dialog === "project" && (!workspace || workspace.role === "viewer"))
    )
      return;
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    if (!name) {
      setFormError("Enter a name to continue.");
      return;
    }
    submitLock.current = true;
    setBusy(true);
    setFormError("");
    try {
      if (dialog === "workspace") {
        const created = await api<Workspace>("/workspaces", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        track("workspace_created");
        setWorkspaces((current) => [...current, created]);
        router.push(workspaceHref(created.id));
        setNotice("Workspace created. Add a project when you’re ready.");
      } else if (workspace) {
        const created = await api<Project>(
          `/workspaces/${workspace.id}/projects`,
          {
            method: "POST",
            body: JSON.stringify({
              name,
              description: String(form.get("description") || "").trim(),
            }),
          },
        );
        track("project_created");
        setProject({ ...created, workspaceId: workspace.id });
        setRevision((value) => value + 1);
        router.push(workspaceHref(workspace.id, { project: created.id }));
        setNotice("Project created. Add footage to get started.");
      }
      setDialog(null);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401)
        handleFailure(failure);
      else
        setFormError(
          failure instanceof Error
            ? failure.message
            : "Unable to create. Please try again.",
        );
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  if (loading || (!user && !error) || (user && accountOnly && !settingsOpen))
    return <WorkspaceLoading />;
  if (!user)
    return (
      <main id="main" className="workspace-opening">
        <Brand />
        <div role="alert">{error}</div>
        <button
          className="secondary"
          onClick={() => setAccountRetry((value) => value + 1)}
        >
          Try again
        </button>
        <Link href="/login">Sign in</Link>
      </main>
    );

  const homeHref = workspace
    ? workspaceHref(workspace.id)
    : accountOnly
      ? "/onboarding"
      : "/app";
  const navigation = (
    <>
      {!accountOnly && (
        <label className="field workspace-select">
          <span>Workspace</span>
          <select
            value={workspace?.id || ""}
            onChange={(event) => {
              router.push(workspaceHref(event.target.value));
              setMobileOpen(false);
            }}
            aria-label="Choose workspace"
          >
            {!workspace && <option value="">Choose workspace</option>}
            {workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <nav
        className="workspace-nav"
        aria-label={accountOnly ? "Account navigation" : "Workspace navigation"}
      >
        <Link
          href={homeHref}
          className={!projectId && !settingsOpen ? "active" : ""}
          aria-current={!projectId && !settingsOpen ? "page" : undefined}
          onClick={() => setMobileOpen(false)}
        >
          {accountOnly ? <Plus size={19} /> : <Layers3 size={19} />}
          {accountOnly ? "First project" : "Projects"}
        </Link>
        {(workspace || accountOnly) && (
          <Link
            href={
              workspace
                ? workspaceHref(workspace.id, { settings: true })
                : "/app?view=settings"
            }
            className={settingsOpen ? "active" : ""}
            aria-current={settingsOpen ? "page" : undefined}
            onClick={() => setMobileOpen(false)}
          >
            <Settings2 size={19} />
            {accountOnly ? "Account settings" : "Settings & usage"}
          </Link>
        )}
      </nav>
      <div className="workspace-nav-bottom">
        {!accountOnly && (
          <button
            className="workspace-quiet"
            onClick={() => {
              setMobileOpen(false);
              setFormError("");
              setDialog("workspace");
            }}
          >
            <Plus size={18} />
            New workspace
          </button>
        )}
        <div className="workspace-account">
          <span>{user.name}</span>
          <small>{user.email}</small>
        </div>
        <button
          className="workspace-quiet"
          disabled={signingOut || busy}
          onClick={() => void signOut()}
        >
          <LogOut size={18} />
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </>
  );

  return (
    <div className="premium-workspace">
      {deleteTarget && (
        <DeleteDialog
          key={deleteTarget.path}
          target={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            const remaining = workspaces.filter(
              (item) => `/workspaces/${item.id}` !== deleteTarget.path,
            );
            setDeleteTarget(null);
            setWorkspaces(remaining);
            setProject(null);
            setPageData(null);
            setNotice("Workspace deleted. Your account is still active.");
            router.replace(
              remaining.length ? workspaceHref(remaining[0].id) : "/onboarding",
            );
          }}
        />
      )}
      <header className="workspace-header">
        <Brand
          href={homeHref}
          label={accountOnly ? "RUSHES first project" : "RUSHES dashboard"}
        />
        <div className="workspace-header-context">
          {workspace?.name || (accountOnly ? "Your account" : "Your workspace")}
        </div>
        <AppearanceMenu />
        <DialogPrimitive.Root open={mobileOpen} onOpenChange={setMobileOpen}>
          <DialogPrimitive.Trigger asChild>
            <button
              className="workspace-menu icon-button"
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
          </DialogPrimitive.Trigger>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="dialog-overlay" />
            <DialogPrimitive.Content className="workspace-mobile-sheet">
              <DialogPrimitive.Title>
                {accountOnly ? "Your account" : "Workspace"}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="sr-only">
                {accountOnly
                  ? "Manage your sign-in or start your first project."
                  : "Choose your workspace or a destination."}
              </DialogPrimitive.Description>
              <DialogPrimitive.Close
                className="icon-button dialog-close"
                aria-label="Close navigation"
              >
                <X size={22} />
              </DialogPrimitive.Close>
              {navigation}
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      </header>
      <aside className="workspace-sidebar">{navigation}</aside>
      <main id="main" className="workspace-main">
        <div className="workspace-content" ref={mainRef} tabIndex={-1}>
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={18} />
              </button>
            </div>
          )}
          {notice && (
            <p className="workspace-notice" role="status">
              {notice}
            </p>
          )}
          {settingsOpen && accountOnly ? (
            <section className="settings-view workspace-settings">
              <div className="page-heading">
                <div>
                  <span className="eyebrow">YOUR ACCOUNT</span>
                  <h1>Account settings</h1>
                  <p>Manage how you sign in to RUSHES.</p>
                </div>
                <Link className="secondary" href="/onboarding">
                  Start your first project <ArrowRight size={18} />
                </Link>
              </div>
              <GoogleAccount />
            </section>
          ) : !workspace ? (
            <section className="workspace-empty">
              <h1>Choose a workspace</h1>
              <p>
                The workspace in this link is unavailable. Choose one from the
                workspace menu.
              </p>
            </section>
          ) : settingsOpen ? (
            <SettingsView
              key={workspace.id}
              workspace={workspace}
              onManageFootage={() => router.push(workspaceHref(workspace.id))}
              onDeleteWorkspace={() =>
                setDeleteTarget({
                  kind: "workspace",
                  name: workspace.name,
                  path: `/workspaces/${workspace.id}`,
                })
              }
            />
          ) : projectId ? (
            activeProject ? (
              <ProjectView
                key={activeProject.id}
                project={activeProject}
                workspace={workspace}
                onDeleted={() => {
                  setProject(null);
                  setRevision((value) => value + 1);
                  setNotice(
                    "Project deleted. Its uploaded footage and exports have been removed.",
                  );
                  router.replace(workspaceHref(workspace.id));
                }}
                onBack={() =>
                  router.push(
                    workspaceHref(workspace.id, { page: projectPage }),
                  )
                }
              />
            ) : (
              <section className="workspace-empty">
                {projectLoading ? (
                  <p role="status">Opening project…</p>
                ) : (
                  <>
                    <h1>Project unavailable</h1>
                    <Link
                      className="secondary"
                      href={workspaceHref(workspace.id)}
                    >
                      Back to Projects
                    </Link>
                  </>
                )}
              </section>
            )
          ) : (
            <>
              <div className="workspace-page-heading">
                <div>
                  <span className="workspace-eyebrow">Your library</span>
                  <h1>Projects</h1>
                  <p>Your footage, grouped into projects.</p>
                </div>
                {workspace.role !== "viewer" && (
                  <button
                    className="primary"
                    onClick={() => {
                      setFormError("");
                      setDialog("project");
                    }}
                  >
                    <Plus size={18} />
                    New project
                  </button>
                )}
              </div>
              {projectsLoading && !projects.length ? (
                <div className="workspace-list-loading" role="status">
                  <Loader2 size={20} className="workspace-spinner" />
                  Loading projects…
                </div>
              ) : projectsFailed && !projects.length ? (
                <section className="workspace-empty">
                  <h2>We couldn’t load your projects.</h2>
                  <p>Your library is still here. Try loading it again.</p>
                  <button
                    className="secondary"
                    onClick={() => {
                      setError("");
                      setRevision((value) => value + 1);
                    }}
                  >
                    Try again
                  </button>
                </section>
              ) : projects.length ? (
                <section
                  className="workspace-project-list"
                  aria-label="Projects"
                  aria-busy={projectsLoading}
                >
                  <div className="workspace-list-label">
                    <span>
                      {projectTotal}{" "}
                      {projectTotal === 1 ? "project" : "projects"}
                    </span>
                    <span>Created</span>
                  </div>
                  {projects.map((item) => (
                    <Link
                      className="workspace-project-row"
                      href={workspaceHref(workspace.id, {
                        project: item.id,
                        page: projectPage,
                      })}
                      key={item.id}
                    >
                      <span className="workspace-project-icon">
                        <FolderOpen size={25} strokeWidth={1.5} />
                      </span>
                      <div className="workspace-project-copy">
                        <h2>{item.name}</h2>
                        <p>{item.description || "Your organized footage"}</p>
                      </div>
                      <time dateTime={item.created_at}>
                        {new Date(item.created_at).toLocaleDateString(
                          undefined,
                          { month: "short", day: "numeric", year: "numeric" },
                        )}
                      </time>
                      <ArrowRight size={19} />
                    </Link>
                  ))}
                </section>
              ) : (
                <section className="workspace-empty">
                  <FolderOpen size={32} strokeWidth={1.3} />
                  <h2>A home for your next project.</h2>
                  <p>
                    {workspace.role === "viewer"
                      ? "Projects will appear here when a workspace editor adds them."
                      : "Create a project, then add the footage you want to explore."}
                  </p>
                </section>
              )}
              {projectTotal > PAGE_SIZE && (
                <nav
                  className="workspace-pagination"
                  aria-label="Project pages"
                >
                  <button
                    className="secondary"
                    disabled={projectPage === 0 || projectsLoading}
                    onClick={() =>
                      router.push(
                        workspaceHref(workspace.id, { page: projectPage - 1 }),
                      )
                    }
                  >
                    <ChevronLeft size={18} />
                    Previous
                  </button>
                  <span>
                    Page {projectPage + 1} of{" "}
                    {Math.ceil(projectTotal / PAGE_SIZE)}
                  </span>
                  <button
                    className="secondary"
                    disabled={
                      (projectPage + 1) * PAGE_SIZE >= projectTotal ||
                      projectsLoading
                    }
                    onClick={() =>
                      router.push(
                        workspaceHref(workspace.id, { page: projectPage + 1 }),
                      )
                    }
                  >
                    Next
                    <ChevronRight size={18} />
                  </button>
                </nav>
              )}
            </>
          )}
        </div>
        <footer className="workspace-footer">
          <span>© {new Date().getFullYear()} RUSHES</span>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
        </footer>
      </main>
      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open && !submitLock.current) setDialog(null);
        }}
        title={dialog === "project" ? "New project" : "New workspace"}
        description={
          dialog === "project"
            ? "Give this footage a home."
            : "Create a separate space for your projects."
        }
      >
        <form className="stack" onSubmit={create}>
          <label className="field">
            <span>
              {dialog === "project" ? "Project name" : "Workspace name"}
            </span>
            <input
              name="name"
              required
              maxLength={120}
              autoFocus
              disabled={busy}
              aria-invalid={Boolean(formError)}
              aria-describedby={formError ? "create-error" : undefined}
            />
          </label>
          {dialog === "project" && (
            <label className="field">
              <span>
                Description <span className="muted">(optional)</span>
              </span>
              <textarea
                name="description"
                rows={2}
                maxLength={2000}
                disabled={busy}
              />
            </label>
          )}
          {formError && (
            <p id="create-error" className="error-text" role="alert">
              {formError}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy
              ? "Creating…"
              : dialog === "project"
                ? "Create project"
                : "Create workspace"}
            <ArrowRight size={18} />
          </button>
        </form>
      </Dialog>
    </div>
  );
}
