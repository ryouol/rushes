"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  Check,
  Film,
  Folder,
  Loader2,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import {
  api,
  elapsed,
  type Asset,
  type Collection,
  type ExportPreview,
  type ExportRecord,
  type Job,
  type Project,
  type ProjectOrganization,
  type SearchResult,
  type SearchResponse,
  type Workspace,
} from "@/lib/api";
import { flushSync } from "react-dom";
import { useProjectSearchTool } from "@/lib/webmcp";
import { track } from "@/lib/analytics";
import { Dialog } from "@/components/dialog";
import { DeleteDialog, type DeleteTarget } from "@/components/delete-dialog";
import "./editor.css";
import { ImportDialog } from "./import-dialog";
import { CollectionView } from "./collection-view";
import { Player } from "@/components/player";
import {
  OrganizationCategories,
  OrganizationLibrary,
  OrganizationStatus,
} from "@/components/organization-library";
import "./organization-library.css";

const activeStates = new Set([
  "queued",
  "dispatched",
  "running",
  "cancel_requested",
]);
export function ProjectView({
  project,
  workspace,
  onBack,
  onDeleted,
}: {
  project: Project;
  workspace: Workspace;
  onBack: () => void;
  onDeleted: () => void;
}) {
  const base = `/workspaces/${workspace.id}`;
  const [tab, setTab] = useState<"footage" | "collections" | "exports">(
    "footage",
  );
  const [footage, setFootage] = useState<{
    items: Asset[];
    total: number;
    page: number;
    category: string;
  } | null>(null);
  const assets = footage?.items ?? [];
  const total = footage?.total ?? 0;
  const [page, setPage] = useState(0);
  const [category, setCategory] = useState("");
  const footageCurrent =
    footage?.page === page && footage.category === category;
  const [organization, setOrganization] = useState<ProjectOrganization | null>(
    null,
  );
  const [organizationError, setOrganizationError] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]),
    [connected, setConnected] = useState(true);
  const [collections, setCollections] = useState<Collection[]>([]),
    [exports, setExports] = useState<ExportRecord[]>([]);
  const [exportPage, setExportPage] = useState(0),
    [exportTotal, setExportTotal] = useState(0);
  const [selected, setSelected] = useState<{
    id: string;
    seek?: number;
  } | null>(null);
  const [importOpen, setImportOpen] = useState(false),
    [newCollection, setNewCollection] = useState(false);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(""),
    [searching, setSearching] = useState(false);
  const [resultQuery, setResultQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null),
    [searchNotice, setSearchNotice] = useState("");
  const [preview, setPreview] = useState<ExportPreview | null>(null),
    [startingExport, setStartingExport] = useState(false);
  const [openCollection, setOpenCollection] = useState<Collection | null>(null);
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const pendingActions = useRef(new Set<string>());
  async function action(
    key: string,
    run: () => Promise<void>,
    success: string,
  ) {
    if (pendingActions.current.has(key)) return;
    pendingActions.current.add(key);
    setPending([...pendingActions.current]);
    setError("");
    setNotice("");
    try {
      await run();
      setNotice(success);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      pendingActions.current.delete(key);
      setPending([...pendingActions.current]);
    }
  }

  const refreshRequest = useRef<AbortController | null>(null);
  const searchRequest = useRef<AbortController | null>(null);
  const applySearch = useCallback((value: string, response: SearchResponse) => {
    setQuery(value);
    setResultQuery(value);
    setTab("footage");
    setCategory("");
    setPage(0);
    setResults(response.results);
    setSearchNotice(
      [
        response.notice,
        response.incomplete_processing
          ? "Some footage is still incomplete. Results reflect the available worklog."
          : "",
      ]
        .filter(Boolean)
        .join(" "),
    );
  }, []);
  const refresh = useCallback(async () => {
    refreshRequest.current?.abort();
    const request = new AbortController();
    refreshRequest.current = request;
    const options = { signal: request.signal };
    try {
      const [footage, groups, rendered, organized] = await Promise.all([
        api<{ items: Asset[]; total: number }>(
          `${base}/projects/${project.id}/assets?offset=${page * 40}${category ? `&category=${encodeURIComponent(category)}` : ""}`,
          options,
        ),
        api<Collection[]>(
          `${base}/projects/${project.id}/collections`,
          options,
        ),
        api<{ items: ExportRecord[]; total: number }>(
          `${base}/projects/${project.id}/exports?offset=${exportPage * 100}`,
          options,
        ),
        api<ProjectOrganization>(
          `${base}/projects/${project.id}/organization`,
          options,
        ).then(
          (data) => ({ data, error: "" }),
          (failure: unknown) => ({
            data: null,
            error:
              failure instanceof Error
                ? failure.message
                : "AI organization could not load. Try again.",
          }),
        ),
      ]);
      if (request.signal.aborted) return;
      if (page > 0 && page * 40 >= footage.total) {
        setPage(Math.max(0, Math.ceil(footage.total / 40) - 1));
        return;
      }
      if (exportPage > 0 && exportPage * 100 >= rendered.total) {
        setExportPage(Math.max(0, Math.ceil(rendered.total / 100) - 1));
      }
      setFootage({ ...footage, page, category });
      setCollections(groups);
      setExports(rendered.items);
      setExportTotal(rendered.total);
      setOrganization(organized.data);
      setOrganizationError(organized.error);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }, [base, project.id, page, category, exportPage]);
  useEffect(() => {
    setLoading(true);
    void refresh();
    return () => refreshRequest.current?.abort();
  }, [refresh]);
  useEffect(() => () => searchRequest.current?.abort(), []);
  useEffect(() => {
    const events = new EventSource(
      `/api${base}/events?project_id=${project.id}`,
    );
    let previous = "";
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.addEventListener("session-expired", () => {
      events.close();
      setError(
        "Your session or workspace membership ended. Sign in again to continue.",
      );
      setConnected(false);
    });
    events.onmessage = (event) => {
      const all = JSON.parse(event.data) as Job[];
      const relevant = all.filter((job) => job.project_id === project.id);
      const serialized = JSON.stringify(relevant);
      if (serialized !== previous) {
        setJobs(relevant);
        previous = serialized;
        void refresh();
      }
    };
    return () => events.close();
  }, [base, project.id, refresh]);

  function clearSearch() {
    searchRequest.current?.abort();
    setSearching(false);
    setQuery("");
    setResultQuery("");
    setResults(null);
    setSearchNotice("");
  }
  async function search(event?: FormEvent, searchQuery = query) {
    event?.preventDefault();
    if (!searchQuery.trim()) {
      clearSearch();
      return;
    }
    searchRequest.current?.abort();
    const request = new AbortController();
    searchRequest.current = request;
    setSearching(true);
    setError("");
    try {
      const url = `${base}/projects/${project.id}/search?q=${encodeURIComponent(searchQuery)}`;
      const immediate = await api<SearchResponse>(`${url}&semantic=false`, {
        signal: request.signal,
      });
      if (request.signal.aborted) return;
      applySearch(searchQuery, immediate);
      const result = await api<SearchResponse>(url, { signal: request.signal });
      if (!request.signal.aborted) applySearch(searchQuery, result);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setSearching(false);
    }
  }
  async function exportPreview(body: object, rethrow = false) {
    if (pendingActions.current.has("preview")) return;
    pendingActions.current.add("preview");
    setPending([...pendingActions.current]);
    setError("");
    try {
      setPreview(
        await api<ExportPreview>(
          `${base}/projects/${project.id}/export-preview`,
          { method: "POST", body: JSON.stringify(body) },
        ),
      );
    } catch (e) {
      if (rethrow) throw e;
      setError((e as Error).message);
    } finally {
      pendingActions.current.delete("preview");
      setPending([...pendingActions.current]);
    }
  }
  async function createCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await action(
      "collection",
      async () => {
        await api(`${base}/projects/${project.id}/collections`, {
          method: "POST",
          body: JSON.stringify({
            name: String(form.get("name") || "").trim(),
            instructions: String(form.get("instructions") || "").trim(),
          }),
        });
        setNewCollection(false);
        await refresh();
      },
      "Collection created.",
    );
  }
  const showToolResults = useCallback(
    (value: string, response: SearchResponse) => {
      searchRequest.current?.abort();
      setSearching(false);
      flushSync(() => applySearch(value, response));
    },
    [applySearch],
  );
  useProjectSearchTool(base, project.id, showToolResults);
  const canEdit = workspace.role !== "viewer";
  const active = jobs.filter((job) => activeStates.has(job.state));
  const showFootageTools =
    (organization?.total_assets ?? total) > 0 ||
    category ||
    results !== null ||
    searching;
  const selectedCategory = organization?.categories.find(
    (item) => item.id === category,
  );

  return (
    <section className="project-view organizer-project">
      {deleteTarget && (
        <DeleteDialog
          key={deleteTarget.path}
          target={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            const kind = deleteTarget.kind;
            setDeleteTarget(null);
            if (kind === "project") {
              onDeleted();
              return;
            }
            clearSearch();
            setOpenCollection(null);
            setNotice(
              kind === "video"
                ? "Video deleted. RUSHES-managed files have been removed."
                : kind === "collection"
                  ? "Collection deleted. Your videos stay in the library."
                  : "Export deleted. Its downloadable files have been removed.",
            );
            void refresh();
          }}
        />
      )}
      <button className="text-button back-button" onClick={onBack}>
        <ArrowLeft size={16} /> All projects
      </button>
      <div className="page-heading">
        <div>
          <h1>{project.name}</h1>
          <p>
            {project.description || "Your footage, organized by what’s inside."}
          </p>
        </div>
        {canEdit && (
          <div className="management-actions">
            <button className="primary" onClick={() => setImportOpen(true)}>
              <Plus size={18} /> Import footage
            </button>
            <button
              className="icon-button"
              aria-label="Delete project"
              title="Delete project"
              onClick={() =>
                setDeleteTarget({
                  kind: "project",
                  name: project.name,
                  path: `${base}/projects/${project.id}`,
                })
              }
            >
              <Trash2 size={19} />
            </button>
          </div>
        )}
      </div>
      {!connected && (
        <div className="notice" role="status">
          Connection interrupted. Reconnecting to processing updates…
        </div>
      )}
      {error && (
        <div className="notice danger" role="alert">
          {error}
          <button
            className="icon-button"
            onClick={() => setError("")}
            aria-label="Dismiss project error"
          >
            <X size={18} />
          </button>
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          <Check size={17} />
          {notice}
        </p>
      )}
      {pending.includes("preview") && (
        <p className="notice" role="status">
          <Loader2 className="spin" size={17} />
          Preparing your export preview…
        </p>
      )}
      <OrganizationStatus
        organization={organization}
        error={organizationError}
        onRetry={() => void refresh()}
      />
      {active.length > 0 && (
        <div className="processing-strip" role="status">
          <Loader2 size={18} className="spin" />
          <div>
            <strong>{active[0].stage}</strong>
            <span>
              {active.length} {active.length === 1 ? "job" : "jobs"} in progress
              · Safe to leave after uploads finish
            </span>
          </div>
          <progress
            max={100}
            value={active[0].progress}
            aria-label="Current processing progress"
          />
          {canEdit && (
            <button
              className="text-button"
              disabled={
                pending.includes("cancel") ||
                active[0].state === "cancel_requested"
              }
              onClick={() =>
                void action(
                  "cancel",
                  async () => {
                    await api(`${base}/jobs/${active[0].id}/cancel`, {
                      method: "POST",
                    });
                    await refresh();
                  },
                  "Cancellation requested. Completed work is retained.",
                )
              }
            >
              {pending.includes("cancel") ||
              active[0].state === "cancel_requested"
                ? "Canceling…"
                : "Cancel"}
            </button>
          )}
        </div>
      )}
      <form className="search-bar" onSubmit={search} hidden={!showFootageTools}>
        <Search size={20} />
        <input
          aria-label="Search footage"
          placeholder="Find anything in your footage"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {results && (
          <button
            type="button"
            className="icon-button"
            aria-label="Clear search"
            onClick={clearSearch}
          >
            <X size={18} />
          </button>
        )}
        <button className="secondary" disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </button>
      </form>
      <div className="project-toolbar">
        <div className="tab-list" role="tablist" aria-label="Project views">
          {(
            [
              ["footage", "Library", Film],
              ["collections", "Collections", Folder],
              ["exports", "Exports", ArrowDownToLine],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              id={`tab-${id}`}
              role="tab"
              aria-selected={tab === id}
              aria-controls="project-panel"
              tabIndex={tab === id ? 0 : -1}
              onKeyDown={(event) => {
                const ids = ["footage", "collections", "exports"] as const;
                const index = ids.indexOf(id);
                const next =
                  event.key === "ArrowRight"
                    ? (index + 1) % 3
                    : event.key === "ArrowLeft"
                      ? (index + 2) % 3
                      : event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? 2
                          : -1;
                if (next >= 0) {
                  event.preventDefault();
                  setTab(ids[next]);
                  document.getElementById(`tab-${ids[next]}`)?.focus();
                }
              }}
              className={tab === id ? "tab active" : "tab"}
              onClick={() => setTab(id)}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </div>
        <span className="view-meta">
          {organization?.total_assets ?? total}{" "}
          {(organization?.total_assets ?? total) === 1 ? "file" : "files"}
        </span>
      </div>
      <div id="project-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "footage" && (
          <>
            <OrganizationCategories
              organization={organization}
              value={category}
              onChange={(value) => {
                setCategory(value);
                setPage(0);
                clearSearch();
              }}
            />
            <div
              className="organization-library-heading"
              hidden={!showFootageTools}
            >
              <p>
                {results
                  ? "Search across all footage"
                  : category === "uncategorized"
                    ? "No AI category yet"
                    : selectedCategory
                      ? `Grouped by AI · ${selectedCategory.name}`
                      : category
                        ? "Selected category"
                        : "All footage"}
              </p>
              {canEdit && selectedCategory && !results && (
                <button
                  className="text-button"
                  disabled={pending.includes("preview") || total === 0}
                  onClick={() =>
                    void exportPreview({ kind: "copies", category })
                  }
                >
                  <ArrowDownToLine size={16} /> Export category
                </button>
              )}
              {canEdit && results && resultQuery.trim() && (
                <button
                  className="text-button"
                  disabled={pending.includes("search")}
                  onClick={() =>
                    void action(
                      "search",
                      async () => {
                        await api(
                          `${base}/projects/${project.id}/collections`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              name: resultQuery.slice(0, 160),
                              saved_query: resultQuery,
                            }),
                          },
                        );
                        await refresh();
                      },
                      "Search saved. Open it again from Collections.",
                    )
                  }
                >
                  {pending.includes("search") ? "Saving…" : "Save this search"}
                </button>
              )}
            </div>
            {results ? (
              <div className="search-results">
                {searchNotice && <p className="notice">{searchNotice}</p>}
                <p className="section-label">
                  {results.length} matching{" "}
                  {results.length === 1 ? "range" : "ranges"}
                </p>
                {results.length ? (
                  results.map((result) => (
                    <button
                      key={`${result.asset_id}:${result.start_us}:${result.end_us}`}
                      className="search-result"
                      onClick={() =>
                        setSelected({
                          id: result.asset_id,
                          seek: result.start_us,
                        })
                      }
                    >
                      <div className="result-image">
                        {result.has_thumbnail ? (
                          <img
                            src={`/api${base}/assets/${result.asset_id}/media/thumbnail`}
                            alt=""
                            loading="lazy"
                          />
                        ) : (
                          <Film size={24} />
                        )}
                      </div>
                      <div>
                        <span className="timecode">
                          {elapsed(result.start_us)} — {elapsed(result.end_us)}
                        </span>
                        <h2>{result.asset_name}</h2>
                        <p>
                          {result.evidence.map((e) => e.description).join(" ")}
                        </p>
                        <span className="muted small">
                          {result.evidence.length} worklog{" "}
                          {result.evidence.length === 1
                            ? "reference"
                            : "references"}
                        </span>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="empty-state compact">
                    <Search size={30} />
                    <h2>No supporting footage found</h2>
                    <p>
                      Try a phrase from the transcript, a different visual
                      detail, or wait for processing to finish.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <OrganizationLibrary
                assets={assets}
                base={base}
                category={footage?.category ?? category}
                loading={loading}
                stale={!footageCurrent}
                total={total}
                page={footage?.page ?? page}
                canEdit={canEdit}
                pending={pending}
                onOpen={(id) => setSelected({ id })}
                onDelete={(asset) =>
                  setDeleteTarget({
                    kind: "video",
                    name: asset.name,
                    path: `${base}/assets/${asset.id}`,
                  })
                }
                onPageChange={setPage}
                onRefresh={() => {
                  setError("");
                  setLoading(true);
                  void refresh();
                }}
                onRetry={(id) =>
                  void action(
                    id,
                    async () => {
                      await api(`${base}/assets/${id}/retry`, {
                        method: "POST",
                      });
                      await refresh();
                    },
                    "Processing recovery queued.",
                  )
                }
              />
            )}
          </>
        )}
        {tab === "collections" && (
          <>
            <div className="section-heading">
              <div>
                <h2>Your collections</h2>
                <p className="muted small">
                  Groups you create and curate, separate from AI categories.
                </p>
              </div>
              {canEdit && (
                <button
                  className="secondary"
                  onClick={() => setNewCollection(true)}
                >
                  <Plus size={16} />
                  New collection
                </button>
              )}
            </div>
            {openCollection ? (
              <CollectionView
                key={openCollection.id}
                collection={openCollection}
                base={base}
                canEdit={canEdit}
                onBack={() => setOpenCollection(null)}
                onOpen={setSelected}
                onExport={(kind) =>
                  exportPreview(
                    { kind, collection_id: openCollection.id },
                    true,
                  )
                }
              />
            ) : collections.length ? (
              <div className="collection-grid">
                {collections.map((c) => (
                  <article className="collection-entry" key={c.id}>
                    <button
                      className="collection-card"
                      onClick={() =>
                        c.saved_query
                          ? void search(undefined, c.saved_query)
                          : setOpenCollection(c)
                      }
                    >
                      <Folder size={28} />
                      <h2>{c.name}</h2>
                      <p>
                        {c.saved_query
                          ? `Saved search · ${c.saved_query}`
                          : c.instructions ||
                            "Review your saved footage and selected ranges."}
                      </p>
                    </button>
                    {canEdit && (
                      <button
                        className="text-button delete-item"
                        aria-label={`Delete collection ${c.name}`}
                        onClick={() =>
                          setDeleteTarget({
                            kind: "collection",
                            name: c.name,
                            path: `${base}/collections/${c.id}`,
                          })
                        }
                      >
                        <Trash2 size={14} /> Delete collection
                      </button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state compact">
                <Folder size={32} />
                <h2>Create a collection for your project</h2>
                <p>
                  Group whole files or useful ranges around your own brief. AI
                  categories remain available in the Library.
                </p>
              </div>
            )}
          </>
        )}
        {tab === "exports" && (
          <>
            {exportTotal > 100 && (
              <div className="button-row" aria-label="Export pages">
                <button
                  className="secondary"
                  disabled={exportPage === 0}
                  onClick={() => setExportPage((page) => page - 1)}
                >
                  Newer exports
                </button>
                <span>
                  Page {exportPage + 1} of {Math.ceil(exportTotal / 100)}
                </span>
                <button
                  className="secondary"
                  disabled={(exportPage + 1) * 100 >= exportTotal}
                  onClick={() => setExportPage((page) => page + 1)}
                >
                  Older exports
                </button>
              </div>
            )}
            <div className="section-heading">
              <div>
                <h2>Export queue</h2>
                <p className="muted small">
                  Completed files remain in your separate output folder on the
                  RUSHES server.
                </p>
              </div>
              {canEdit && (
                <div className="button-row">
                  <button
                    className="secondary"
                    disabled={pending.includes("preview")}
                    onClick={() => void exportPreview({ kind: "json" })}
                  >
                    Worklog JSON
                  </button>
                  <button
                    className="secondary"
                    disabled={pending.includes("preview")}
                    onClick={() => void exportPreview({ kind: "csv" })}
                  >
                    Worklog CSV
                  </button>
                </div>
              )}
            </div>
            {exports.length ? (
              <div className="export-list">
                {exports.map((output) => (
                  <article key={output.id} className="export-row">
                    <ArrowDownToLine size={22} />
                    <div>
                      <h2>{output.name}</h2>
                      <p className="muted small">
                        {output.state} ·{" "}
                        {new Date(output.created_at).toLocaleString()}
                      </p>
                      {canEdit &&
                        ["failed", "canceled"].includes(output.state) && (
                          <button
                            className="secondary"
                            disabled={pending.includes(output.id)}
                            onClick={() =>
                              void action(
                                output.id,
                                async () => {
                                  await api(
                                    `${base}/exports/${output.id}/retry`,
                                    { method: "POST" },
                                  );
                                  await refresh();
                                },
                                "Export recovery queued.",
                              )
                            }
                          >
                            {pending.includes(output.id)
                              ? "Queuing…"
                              : "Retry export"}
                          </button>
                        )}
                      {output.output_path && (
                        <details className="export-location">
                          <summary>Output location</summary>
                          <p className="output-path">{output.output_path}</p>
                        </details>
                      )}
                      {canEdit && (
                        <button
                          className="text-button export-delete"
                          onClick={() =>
                            setDeleteTarget({
                              kind: "export",
                              name: output.name,
                              path: `${base}/exports/${output.id}`,
                            })
                          }
                        >
                          <Trash2 size={15} /> Delete export
                        </button>
                      )}
                      <div className="download-links">
                        {output.provenance.outputs?.map((file, index) => (
                          <a
                            key={file.output}
                            href={`/api${base}/exports/${output.id}/download/${index}`}
                            download
                          >
                            {file.output} <ArrowDownToLine size={14} />
                          </a>
                        ))}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state compact">
                <ArrowDownToLine size={32} />
                <h2>Your organized footage, ready to take with you</h2>
                <p>
                  Export an AI category from the Library, a collection, or your
                  project’s worklog.
                </p>
              </div>
            )}
          </>
        )}
      </div>
      {selected && (
        <Player
          key={selected.id}
          assetId={selected.id}
          seekUs={selected.seek}
          workspace={workspace}
          collections={collections}
          projectId={project.id}
          onCollectionCreated={(created) =>
            setCollections((current) =>
              current.some((item) => item.id === created.id)
                ? current
                : [...current, created],
            )
          }
          onClose={() => setSelected(null)}
          onExport={(body) => exportPreview(body, true)}
        />
      )}
      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        base={base}
        projectId={project.id}
        onImported={refresh}
      />
      <Dialog
        open={newCollection}
        onOpenChange={setNewCollection}
        title="New collection"
        description="A source can belong to several collections without being copied."
      >
        <form className="stack" onSubmit={createCollection}>
          <label className="field">
            <span>Name</span>
            <input name="name" required maxLength={160} autoFocus />
          </label>
          <label className="field">
            <span>
              What belongs here? <span className="muted">(optional)</span>
            </span>
            <textarea name="instructions" rows={3} maxLength={2000} />
          </label>
          {error && (
            <p className="error-text" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={pending.includes("collection")}>
            {pending.includes("collection") ? "Creating…" : "Create collection"}
          </button>
        </form>
      </Dialog>
      <Dialog
        open={!!preview}
        onOpenChange={(open) => !open && setPreview(null)}
        title="Review export"
        description="Check your selection before starting the export."
      >
        {preview && (
          <div className="stack">
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            <p className="small muted">{preview.notice}</p>
            {preview.entries.map((entry, index) => (
              <div key={index} className="preview-entry">
                <strong>{entry.filename}</strong>
                <span className="timecode">
                  {elapsed(entry.start_us)} — {elapsed(entry.end_us)} ·{" "}
                  {entry.mode}
                </span>
              </div>
            ))}
            <p className="small">
              Estimated output:{" "}
              {(preview.estimated_bytes / 1024 / 1024).toFixed(1)} MB
            </p>
            <details className="export-location">
              <summary>Output location</summary>
              <div className="output-path">{preview.output_folder}</div>
            </details>
            <button
              className="primary"
              disabled={startingExport}
              onClick={async () => {
                if (startingExport) return;
                setStartingExport(true);
                setError("");
                try {
                  await api(`${base}/exports/${preview.id}/start`, {
                    method: "POST",
                  });
                  track("export_started");
                  setNotice(
                    "Export started. Your download will appear here when it is ready.",
                  );
                  setPreview(null);
                  setSelected(null);
                  setTab("exports");
                  setExportPage(0);
                  await refresh();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setStartingExport(false);
                }
              }}
            >
              {startingExport ? "Starting…" : "Start export"}
              <ArrowDownToLine size={17} />
            </button>
          </div>
        )}
      </Dialog>
    </section>
  );
}
