"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowRight,
  Film,
  FolderOpen,
  Layers3,
  LogOut,
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
import { Dialog } from "@/components/dialog";
import { ProjectView } from "@/components/project";
import { SettingsView } from "@/components/settings";

export function Rushes() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectPage, setProjectPage] = useState(0);
  const [projectTotal, setProjectTotal] = useState(0);
  const [dialog, setDialog] = useState<"project" | "workspace" | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refreshAccount = useCallback(async () => {
    setLoading(true);
    try {
      const account = await api<User>("/auth/me");
      setUser(account);
      const spaces = await api<Workspace[]>("/workspaces");
      setWorkspaces(spaces);
      setWorkspace(
        (current) =>
          spaces.find((s) => s.id === current?.id) || spaces[0] || null,
      );
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUser(null);
      else setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAccount();
  }, [refreshAccount]);
  const projectRequest = useRef<AbortController | null>(null);
  const refreshProjects = useCallback(async () => {
    projectRequest.current?.abort();
    const request = new AbortController();
    projectRequest.current = request;
    if (!workspace) return;
    try {
      const projects = await api<{ items: Project[]; total: number }>(
        `/workspaces/${workspace.id}/projects?offset=${projectPage * 40}`,
        { signal: request.signal },
      );
      if (!request.signal.aborted) {
        setProjects(projects.items);
        setProjectTotal(projects.total);
      }
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    }
  }, [workspace, projectPage]);
  useEffect(() => {
    void refreshProjects();
    setProjects([]);
    return () => projectRequest.current?.abort();
  }, [refreshProjects]);
  useEffect(() => {
    setProject(null);
    setProjectPage(0);
    setProjectTotal(0);
  }, [workspace?.id]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      if (dialog === "workspace" || !workspace) {
        const created = await api<Workspace>("/workspaces", {
          method: "POST",
          body: JSON.stringify({ name: form.get("name") }),
        });
        setWorkspaces((current) => [...current, created]);
        setWorkspace(created);
      } else {
        const created = await api<Project>(
          `/workspaces/${workspace.id}/projects`,
          {
            method: "POST",
            body: JSON.stringify({
              name: form.get("name"),
              description: form.get("description") || "",
            }),
          },
        );
        setProjectPage(0);
        setProjects((current) => [created, ...current].slice(0, 40));
        setProjectTotal((current) => current + 1);
        setProject(created);
      }
      setDialog(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading)
    return (
      <main id="main" className="auth-shell">
        <div className="loading" role="status">
          Opening your workspace…
        </div>
      </main>
    );
  if (!user) return <Auth onSuccess={refreshAccount} serviceError={error} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand" aria-label="RUSHES home">
          <span className="brand-mark">
            <Film size={20} />
          </span>{" "}
          RUSHES<span className="local-label">LIBRARY</span>
        </a>
        <label className="field workspace-picker">
          <span>WORKSPACE</span>
          <select
            value={workspace?.id || ""}
            onChange={(e) => {
              setWorkspace(
                workspaces.find((w) => w.id === e.target.value) || null,
              );
              setProjects([]);
            }}
          >
            {!workspace && <option value="">Create a workspace</option>}
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <nav aria-label="Main navigation">
          <button
            className={
              !project && !settingsOpen ? "nav-item active" : "nav-item"
            }
            onClick={() => {
              setProject(null);
              setSettingsOpen(false);
            }}
          >
            <Layers3 size={19} /> Projects <span>{projectTotal}</span>
          </button>
          {workspace && (
            <button
              className={settingsOpen ? "nav-item active" : "nav-item"}
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 size={19} /> Settings & usage
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setDialog("workspace")}>
            <Plus size={19} /> New workspace
          </button>
          <div className="local-note">
            <span className="status-dot" /> Private workspace
            <p>Gemini analysis sends derived video to Google.</p>
          </div>
          <div className="account">
            <span className="avatar">{user.name.charAt(0).toUpperCase()}</span>
            <div>
              <strong>{user.name}</strong>
              <span>{user.email}</span>
            </div>
            <button
              className="icon-button"
              title="Sign out"
              aria-label="Sign out"
              onClick={async () => {
                try {
                  await api("/auth/logout", { method: "POST" });
                  setUser(null);
                  setProjects([]);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      <main id="main" className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <span>{workspace?.name || "Getting started"}</span>
            <span>/</span>
            <strong>
              {settingsOpen ? "Settings & usage" : project?.name || "Projects"}
            </strong>
          </div>
          <span className="credits">
            {workspace
              ? `${(workspace.balance_milli / 1000).toLocaleString()} credits`
              : "Local setup"}
          </span>
        </header>
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
        <div className="page-content">
          {!workspace ? (
            <section className="welcome">
              <span className="eyebrow">YOUR EDIT STARTS HERE</span>
              <h1>A home for your footage.</h1>
              <p>
                Create a workspace to keep your projects, worklogs, and selects
                together.
              </p>
              <button
                className="primary"
                onClick={() => setDialog("workspace")}
              >
                Create workspace <ArrowRight size={18} />
              </button>
              <div className="setup-note">
                <Settings2 size={20} />
                <div>
                  <strong>Made for your footage library</strong>
                  <p>
                    Import selected files or connect an explicitly configured
                    source folder. Your originals stay intact.
                  </p>
                </div>
              </div>
            </section>
          ) : settingsOpen ? (
            <SettingsView key={workspace.id} workspace={workspace} />
          ) : project ? (
            <ProjectView
              key={project.id}
              project={project}
              workspace={workspace}
              onBack={() => setProject(null)}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">YOUR LIBRARY</span>
                  <h1>
                    Projects
                    <span className="heading-count">{projectTotal}</span>
                  </h1>
                  <p>From camera roll to the moments that matter.</p>
                </div>
                {workspace.role !== "viewer" && (
                  <button
                    className="primary"
                    onClick={() => setDialog("project")}
                  >
                    <Plus size={18} /> New project
                  </button>
                )}
              </div>
              {projectTotal > 40 && (
                <div className="button-row" aria-label="Project pages">
                  <button
                    className="secondary"
                    disabled={projectPage === 0}
                    onClick={() => setProjectPage((page) => page - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    Page {projectPage + 1} of {Math.ceil(projectTotal / 40)}
                  </span>
                  <button
                    className="secondary"
                    disabled={(projectPage + 1) * 40 >= projectTotal}
                    onClick={() => setProjectPage((page) => page + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
              {projects.length ? (
                <div className="project-grid">
                  {projects.map((p) => (
                    <button
                      className="project-card"
                      key={p.id}
                      onClick={() => setProject(p)}
                    >
                      <div className="project-cover">
                        <FolderOpen size={40} strokeWidth={1.1} />
                        <span>PROJECT</span>
                      </div>
                      <div className="project-info">
                        <h2>{p.name}</h2>
                        <p>{p.description || "Open footage library"}</p>
                        <div className="card-meta">
                          <span>
                            {new Date(p.created_at).toLocaleDateString(
                              undefined,
                              {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              },
                            )}
                          </span>
                          <ArrowRight size={17} />
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <Layers3 size={42} strokeWidth={1.2} />
                  <h2>Make room for your next story</h2>
                  <p>
                    A project brings a shoot’s footage, searchable worklog, and
                    selected moments into one place.
                  </p>
                  {workspace.role !== "viewer" && (
                    <button
                      className="primary"
                      onClick={() => setDialog("project")}
                    >
                      <Plus size={18} /> Create your first project
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
        <footer>
          RUSHES <span>© {new Date().getFullYear()} · Footage, organized</span>
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
        </footer>
      </main>
      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => !open && setDialog(null)}
        title={dialog === "project" ? "New project" : "Create a workspace"}
        description={
          dialog === "project"
            ? "Keep a shoot’s footage and selects together."
            : "Only workspace members can access its projects."
        }
      >
        <form onSubmit={create} className="stack">
          <label className="field">
            <span>
              {dialog === "project" ? "Project name" : "Workspace name"}
            </span>
            <input
              name="name"
              required
              maxLength={120}
              autoFocus
              placeholder={
                dialog === "project"
                  ? "e.g. September interviews"
                  : "e.g. My editing studio"
              }
            />
          </label>
          {dialog === "project" && (
            <label className="field">
              <span>
                Description <span className="muted">(optional)</span>
              </span>
              <textarea name="description" rows={3} maxLength={2000} />
            </label>
          )}
          {error && (
            <p className="error-text" role="alert">
              {error}
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

function Auth({
  onSuccess,
  serviceError,
}: {
  onSuccess: () => Promise<void>;
  serviceError: string;
}) {
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email")),
      password = String(data.get("password"));
    try {
      if (signup)
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ name: data.get("name"), email, password }),
        });
      await api("/auth/login", {
        method: "POST",
        body: new URLSearchParams({ username: email, password }),
      });
      await onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="auth-shell">
      <div className="auth-intro">
        <a href="/" className="brand">
          <span className="brand-mark">
            <Film size={22} />
          </span>{" "}
          RUSHES
        </a>
        <div>
          <span className="eyebrow">FOOTAGE, IN FOCUS</span>
          <h1>
            Find the moment.
            <br />
            Build the story.
          </h1>
          <p>
            Your footage library, with a timestamped worklog and room for every
            select.
          </p>
        </div>
        <span className="auth-footnote">
          Local storage · Private workspaces · Originals preserved
        </span>
      </div>
      <div className="auth-panel">
        <div className="auth-form">
          <span className="eyebrow">YOUR EDITING WORKSPACE</span>
          <h2>{signup ? "Create your account" : "Welcome back"}</h2>
          <p className="muted">
            {signup
              ? "Create an account to organize your footage."
              : "Sign in to your RUSHES library."}
          </p>
          <form className="stack" onSubmit={submit}>
            {signup && (
              <label className="field">
                <span>Name</span>
                <input
                  name="name"
                  autoComplete="name"
                  required
                  maxLength={120}
                />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input
                name="email"
                type="email"
                autoComplete="username"
                required
              />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                name="password"
                aria-label="Password"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={signup ? 12 : undefined}
                maxLength={256}
                required
              />
              {signup && <small>Use at least 12 characters.</small>}
            </label>
            {(error || serviceError) && (
              <div className="error-text" role="alert">
                {error || serviceError}
              </div>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
              <ArrowRight size={18} />
            </button>
          </form>
          <button
            className="auth-switch"
            onClick={() => {
              setSignup(!signup);
              setError("");
            }}
          >
            {signup
              ? "Already have an account? Sign in"
              : "New to RUSHES? Create an account"}
          </button>
          <p className="privacy-note">
            Video analysis with Gemini sends derived clips to Google. Local
            storage does not mean fully offline processing.
          </p>
        </div>
      </div>
    </main>
  );
}
