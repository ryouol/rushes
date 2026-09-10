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
  FileVideo,
  Film,
  Folder,
  Loader2,
  Plus,
  Search,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  elapsed,
  type Asset,
  type Collection,
  type CollectionItem,
  type ExportPreview,
  type ExportRecord,
  type Job,
  type Project,
  type SearchResult,
  type SearchResponse,
  type Workspace,
} from "@/lib/api";
import { flushSync } from "react-dom";
import { useProjectSearchTool } from "@/lib/webmcp";
import { track } from "@/lib/analytics";
import { Dialog } from "@/components/dialog";
import { Player } from "@/components/player";

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
}: {
  project: Project;
  workspace: Workspace;
  onBack: () => void;
}) {
  const base = `/workspaces/${workspace.id}`;
  const [tab, setTab] = useState<"footage" | "collections" | "exports">(
    "footage",
  );
  const [assets, setAssets] = useState<Asset[]>([]),
    [total, setTotal] = useState(0),
    [page, setPage] = useState(0);
  const [uncategorized, setUncategorized] = useState(false);
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

  const refreshRequest = useRef<AbortController | null>(null);
  const searchRequest = useRef<AbortController | null>(null);
  const applySearch = useCallback((value: string, response: SearchResponse) => {
    setQuery(value);
    setResultQuery(value);
    setTab("footage");
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
      const [footage, groups, rendered] = await Promise.all([
        api<{ items: Asset[]; total: number }>(
          `${base}/projects/${project.id}/assets?offset=${page * 40}&uncategorized=${uncategorized}`,
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
      ]);
      if (request.signal.aborted) return;
      setAssets(footage.items);
      setTotal(footage.total);
      setCollections(groups);
      setExports(rendered.items);
      setExportTotal(rendered.total);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }, [base, project.id, page, uncategorized, exportPage]);
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
      const result = await api<SearchResponse>(
        `${base}/projects/${project.id}/search?q=${encodeURIComponent(searchQuery)}`,
        { signal: request.signal },
      );
      if (!request.signal.aborted) applySearch(searchQuery, result);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setSearching(false);
    }
  }
  async function exportPreview(body: object) {
    try {
      setPreview(
        await api<ExportPreview>(
          `${base}/projects/${project.id}/export-preview`,
          { method: "POST", body: JSON.stringify(body) },
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function createCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api(`${base}/projects/${project.id}/collections`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          instructions: form.get("instructions") || "",
        }),
      });
      setNewCollection(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
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

  return (
    <section className="project-view">
      <button className="text-button back-button" onClick={onBack}>
        <ArrowLeft size={16} /> All projects
      </button>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PROJECT LIBRARY</span>
          <h1>{project.name}</h1>
          <p>
            {project.description ||
              `${total} source ${total === 1 ? "file" : "files"} · Originals preserved`}
          </p>
        </div>
        {canEdit && (
          <button className="primary" onClick={() => setImportOpen(true)}>
            <Plus size={18} /> Import footage
          </button>
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
      <div className="project-toolbar">
        <div className="tab-list" role="tablist" aria-label="Project views">
          {(
            [
              ["footage", "Footage", Film],
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
        <span className="view-meta">{total} files</span>
      </div>
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
              onClick={async () => {
                try {
                  await api(`${base}/jobs/${active[0].id}/cancel`, {
                    method: "POST",
                  });
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Cancel
            </button>
          )}
        </div>
      )}
      <div id="project-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "footage" && (
          <>
            <form className="search-bar" onSubmit={search}>
              <Search size={20} />
              <input
                aria-label="Search footage"
                placeholder="Search a moment, a phrase, or a visual detail…"
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
            <div className="filter-row">
              <label>
                <input
                  type="checkbox"
                  checked={uncategorized}
                  onChange={(event) => {
                    setUncategorized(event.target.checked);
                    setPage(0);
                    clearSearch();
                  }}
                />
                Uncategorized sources
              </label>
              {canEdit && results && resultQuery.trim() && (
                <button
                  className="text-button"
                  onClick={async () => {
                    try {
                      await api(`${base}/projects/${project.id}/collections`, {
                        method: "POST",
                        body: JSON.stringify({
                          name: resultQuery.slice(0, 160),
                          saved_query: resultQuery,
                        }),
                      });
                      await refresh();
                      setSearchNotice(
                        "Search saved. Open it again from Collections.",
                      );
                    } catch (error) {
                      setError((error as Error).message);
                    }
                  }}
                >
                  Save this search
                </button>
              )}
            </div>
            {results ? (
              <div className="search-results">
                {searchNotice && <p className="notice">{searchNotice}</p>}
                <p className="section-label">
                  {results.length} matching ranges
                </p>
                {results.length ? (
                  results.map((result) => (
                    <button
                      key={`${result.asset_id}:${result.start_us}`}
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
            ) : loading ? (
              <div className="empty-state compact" role="status">
                Loading footage…
              </div>
            ) : assets.length ? (
              <>
                <div className="asset-grid">
                  {assets.map((asset) => (
                    <div key={asset.id} className="asset-card">
                      <button
                        className="asset-open"
                        onClick={() => setSelected({ id: asset.id })}
                      >
                        <div className="asset-image">
                          {asset.has_thumbnail ? (
                            <img
                              src={`/api${base}/assets/${asset.id}/media/thumbnail`}
                              alt={`Preview of ${asset.name}`}
                              loading="lazy"
                            />
                          ) : (
                            <FileVideo size={36} strokeWidth={1.2} />
                          )}
                          <span className="duration timecode">
                            {asset.duration_us
                              ? elapsed(asset.duration_us)
                              : "—"}
                          </span>
                        </div>
                        <div className="asset-info">
                          <h2 title={asset.name}>{asset.name}</h2>
                          <div>
                            <span className={`state ${asset.status}`}>
                              {asset.status.replaceAll("_", " ")}
                            </span>
                            <span className="small muted">
                              {(asset.source_size / 1024 / 1024).toFixed(1)} MB
                            </span>
                          </div>
                        </div>
                      </button>
                      {asset.error && (
                        <p className="asset-notice">{asset.error}</p>
                      )}
                      {canEdit && asset.can_retry && (
                        <button
                          className="text-button retry"
                          onClick={async () => {
                            try {
                              await api(`${base}/assets/${asset.id}/retry`, {
                                method: "POST",
                              });
                              await refresh();
                            } catch (e) {
                              setError((e as Error).message);
                            }
                          }}
                        >
                          Retry processing
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <div className="pagination">
                  <button
                    className="secondary"
                    disabled={page === 0}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    {page * 40 + 1}–{Math.min((page + 1) * 40, total)} of{" "}
                    {total}
                  </span>
                  <button
                    className="secondary"
                    disabled={(page + 1) * 40 >= total}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <Film size={42} strokeWidth={1.2} />
                <h2>Your footage starts here</h2>
                <p>
                  Import video files or a selected folder. RUSHES creates
                  previews and a timestamped worklog while keeping originals
                  intact.
                </p>
                {canEdit && (
                  <button
                    className="primary"
                    onClick={() => setImportOpen(true)}
                  >
                    <Upload size={18} />
                    Import footage
                  </button>
                )}
              </div>
            )}
          </>
        )}
        {tab === "collections" && (
          <>
            <div className="section-heading">
              <div>
                <h2>Collections & selects</h2>
                <p className="muted small">
                  Virtual groups of full files or selected ranges.
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
                collection={openCollection}
                base={base}
                canEdit={canEdit}
                onBack={() => setOpenCollection(null)}
                onOpen={setSelected}
                onExport={(kind) =>
                  exportPreview({ kind, collection_id: openCollection.id })
                }
              />
            ) : collections.length ? (
              <div className="collection-grid">
                {collections.map((c) => (
                  <button
                    className="collection-card"
                    key={c.id}
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
                ))}
              </div>
            ) : (
              <div className="empty-state compact">
                <Folder size={32} />
                <h2>Keep your selects together</h2>
                <p>
                  Create a collection, then add a full source or mark a range in
                  the player.
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
                    onClick={() => exportPreview({ kind: "json" })}
                  >
                    Worklog JSON
                  </button>
                  <button
                    className="secondary"
                    onClick={() => exportPreview({ kind: "csv" })}
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
                            onClick={async () => {
                              try {
                                await api(
                                  `${base}/exports/${output.id}/retry`,
                                  { method: "POST" },
                                );
                                await refresh();
                              } catch (error) {
                                setError((error as Error).message);
                              }
                            }}
                          >
                            Retry export
                          </button>
                        )}
                      {output.output_path && (
                        <p className="output-path">{output.output_path}</p>
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
                <h2>Ready when your selects are</h2>
                <p>
                  Export a range from the player, a collection, or your
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
          onClose={() => setSelected(null)}
          onExport={exportPreview}
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
          <button className="primary">Create collection</button>
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
            <div className="output-path">{preview.output_folder}</div>
            <button
              className="primary"
              disabled={startingExport}
              onClick={async () => {
                setStartingExport(true);
                try {
                  await api(`${base}/exports/${preview.id}/start`, {
                    method: "POST",
                  });
                  track("export_started");
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

function ImportDialog({
  open,
  onOpenChange,
  base,
  projectId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  base: string;
  projectId: string;
  onImported: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null),
    directory = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<
      { name: string; percent: number; state: string }[]
    >([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [roots, setRoots] = useState<
      { id: number; name: string; path: string }[]
    >([]),
    [root, setRoot] = useState("");
  const rootRequest = useRef(0);
  const [rootLoading, setRootLoading] = useState(false);
  const [files, setFiles] = useState<string[]>([]),
    [checked, setChecked] = useState<Set<string>>(new Set()),
    [truncated, setTruncated] = useState(false);
  useEffect(() => {
    if (open)
      api<typeof roots>(`${base}/source-roots`)
        .then(setRoots)
        .catch((e) => setError(e.message));
  }, [open, base]);
  async function upload(files: File[]) {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    const list = Array.from(files).filter((file) =>
      /\.(mp4|mov|mkv|mxf|avi|mts|m2ts|webm|m4v)$/i.test(file.name),
    );
    if (!list.length) {
      setError("No supported video files were selected.");
      setBusy(false);
      return;
    }
    setProgress(
      list.map((file) => ({ name: file.name, percent: 0, state: "Waiting" })),
    );
    let cursor = 0;
    async function next() {
      while (cursor < list.length) {
        const index = cursor++,
          file = list[index];
        await new Promise<void>((resolve) => {
          const request = new XMLHttpRequest();
          request.open(
            "POST",
            `/api${base}/projects/${projectId}/upload?filename=${encodeURIComponent(file.name)}&relative_path=${encodeURIComponent(file.webkitRelativePath || file.name)}`,
          );
          request.setRequestHeader("Content-Type", "application/octet-stream");
          const update = (percent: number, state: string) =>
            setProgress((rows) =>
              rows[index]?.percent === percent && rows[index]?.state === state
                ? rows
                : rows.map((row, i) =>
                    i === index ? { ...row, percent, state } : row,
                  ),
            );
          request.upload.onprogress = (event) =>
            update(
              event.lengthComputable
                ? Math.round((event.loaded / event.total) * 100)
                : 0,
              "Uploading",
            );
          request.onload = () => {
            let detail = "Upload failed; reselect this file";
            try {
              detail = apiErrorMessage(
                JSON.parse(request.responseText),
                detail,
              );
            } catch {}
            update(
              100,
              request.status < 300 ? "Queued for processing" : detail,
            );
            resolve();
          };
          request.onerror = () => {
            update(0, "Disconnected; reselect this file");
            resolve();
          };
          request.send(file);
        });
        await onImported();
      }
    }
    await Promise.all([next(), next()]);
    setBusy(false);
  }
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Import footage"
      description="Select files or a folder. Originals stay in place; selected uploads are copied into private storage on the RUSHES server."
    >
      <div className="stack">
        <div className="import-drop">
          <Upload size={30} />
          <h2>Bring your footage in</h2>
          <div className="button-row">
            <button
              className="primary"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              Choose videos
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => directory.current?.click()}
            >
              Choose folder
            </button>
          </div>
          <input
            ref={input}
            type="file"
            accept="video/*,.mxf,.mts,.m2ts"
            multiple
            hidden
            onChange={(e) => {
              const files = Array.from(e.currentTarget.files || []);
              e.currentTarget.value = "";
              void upload(files);
            }}
          />
          <input
            ref={directory}
            type="file"
            multiple
            hidden
            {...({
              webkitdirectory: "",
            } as React.InputHTMLAttributes<HTMLInputElement>)}
            onChange={(e) => {
              const files = Array.from(e.currentTarget.files || []);
              e.currentTarget.value = "";
              void upload(files);
            }}
          />
        </div>
        <p className="small muted">
          Keep this tab open until uploads finish. Completed files process in
          the background. Interrupted uploads require file reselection.
          Configured Gemini analysis sends derived clips and transcript context
          to Google and uses processing credits. When enabled, Modal processes
          derived audio, worklog text and search queries. Settings shows the
          active processing services.
        </p>
        {progress.length > 0 && (
          <div className="upload-list" aria-live="polite">
            {progress.map((file, index) => (
              <div key={index}>
                <strong>{file.name}</strong>
                <span>
                  {file.state}{" "}
                  {file.state === "Uploading" ? `${file.percent}%` : ""}
                </span>
                <progress
                  value={file.percent}
                  max={100}
                  aria-label={`${file.name} upload`}
                />
              </div>
            ))}
          </div>
        )}
        {roots.length > 0 && (
          <>
            <div className="divider" />
            <label className="field">
              <span>Index a configured source folder</span>
              <select
                value={root}
                disabled={busy}
                onChange={async (e) => {
                  const selected = e.target.value,
                    request = ++rootRequest.current;
                  setRoot(selected);
                  setFiles([]);
                  setChecked(new Set());
                  setTruncated(false);
                  setRootLoading(Boolean(selected));
                  if (!selected) return;
                  try {
                    const result = await api<{
                      files: string[];
                      truncated: boolean;
                    }>(`${base}/source-roots/${selected}/files`);
                    if (rootRequest.current !== request) return;
                    setFiles(result.files);
                    setTruncated(result.truncated);
                  } catch (error) {
                    if (rootRequest.current === request)
                      setError((error as Error).message);
                  } finally {
                    if (rootRequest.current === request) setRootLoading(false);
                  }
                }}
              >
                <option value="">Choose a source root</option>
                {roots.map((root) => (
                  <option key={root.id} value={root.id}>
                    {root.path}
                  </option>
                ))}
              </select>
            </label>
            {rootLoading && <p role="status">Loading selected source root…</p>}
            {files.length > 0 && (
              <>
                <div className="source-files">
                  {files.map((file) => (
                    <label key={file}>
                      <input
                        type="checkbox"
                        checked={checked.has(file)}
                        onChange={(e) =>
                          setChecked((current) => {
                            const next = new Set(current);
                            if (e.target.checked) next.add(file);
                            else next.delete(file);
                            return next;
                          })
                        }
                      />
                      {file}
                    </label>
                  ))}
                </div>
                {truncated && (
                  <p className="small muted">
                    This root has more files than this selection view can
                    display. Import a selected folder through the file picker
                    for the remaining files.
                  </p>
                )}
                <button
                  className="secondary"
                  disabled={!checked.size || busy || rootLoading}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const result = await api<{
                        files: { state: string; error?: string }[];
                      }>(`${base}/projects/${projectId}/index`, {
                        method: "POST",
                        body: JSON.stringify({
                          root: Number(root),
                          paths: [...checked],
                        }),
                      });
                      const failures = result.files.filter(
                        (file) => file.state === "failed",
                      );
                      if (failures.length)
                        setError(failures.map((file) => file.error).join(". "));
                      else onOpenChange(false);
                      await onImported();
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Index {checked.size} selected files
                </button>
              </>
            )}
          </>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        {progress.length > 0 && !busy && (
          <button className="primary" onClick={() => onOpenChange(false)}>
            Return to footage <Check size={17} />
          </button>
        )}
      </div>
    </Dialog>
  );
}

function CollectionView({
  collection,
  base,
  canEdit,
  onBack,
  onOpen,
  onExport,
}: {
  collection: Collection;
  base: string;
  canEdit: boolean;
  onBack: () => void;
  onOpen: (value: { id: string; seek?: number }) => void;
  onExport: (
    kind:
      | "clips"
      | "copies"
      | "fcp7xml"
      | "fcpxml"
      | "selections_json"
      | "selections_csv",
  ) => void;
}) {
  const [items, setItems] = useState<CollectionItem[]>([]),
    [error, setError] = useState("");
  const [editing, setEditing] = useState<CollectionItem | null>(null);
  const pendingSuggestions = useRef(new Set<string>());
  const [addingSuggestions, setAddingSuggestions] = useState<Set<string>>(
    new Set(),
  );
  const [prompt, setPrompt] = useState(collection.instructions),
    [suggestions, setSuggestions] = useState<SearchResult[]>([]),
    [suggestionNotice, setSuggestionNotice] = useState<string | null>(null),
    [suggestionsIncomplete, setSuggestionsIncomplete] = useState(false),
    [busy, setBusy] = useState(false);
  const refreshAbort = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    refreshAbort.current?.abort();
    const controller = new AbortController();
    refreshAbort.current = controller;
    try {
      const rows = await api<CollectionItem[]>(
        `${base}/collections/${collection.id}/items`,
        {
          signal: controller.signal,
        },
      );
      if (!controller.signal.aborted) setItems(rows);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    }
  }, [base, collection.id]);
  useEffect(() => {
    void refresh();
    return () => refreshAbort.current?.abort();
  }, [refresh]);
  return (
    <div className="collection-detail">
      <button className="text-button" onClick={onBack}>
        ← All collections
      </button>
      <div className="section-heading">
        <h2>{collection.name}</h2>
        {canEdit && (
          <div className="button-row">
            <button
              className="secondary"
              disabled={!items.length}
              onClick={() => onExport("copies")}
            >
              Organized copies
            </button>
            <button
              className="primary"
              disabled={!items.length}
              onClick={() => onExport("clips")}
            >
              Export clips
            </button>
          </div>
        )}
      </div>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {canEdit && items.length > 0 && (
        <>
          <details className="xml-options">
            <summary>Selection data</summary>
            <div className="button-row">
              <button
                className="secondary"
                onClick={() => onExport("selections_json")}
              >
                Selection JSON
              </button>
              <button
                className="secondary"
                onClick={() => onExport("selections_csv")}
              >
                Selection CSV
              </button>
            </div>
          </details>
          <details className="xml-options">
            <summary>Experimental editor interchange</summary>
            <p className="small muted">
              Straight cuts from constant-rate, unrotated footage at one shared
              frame rate. References originals on the RUSHES server.
              Target-editor round trips have not been verified.
            </p>
            <div className="button-row">
              <button className="secondary" onClick={() => onExport("fcp7xml")}>
                Preview FCP7 XML
              </button>
              <button className="secondary" onClick={() => onExport("fcpxml")}>
                Preview FCPXML
              </button>
            </div>
          </details>
        </>
      )}
      {editing && (
        <form
          key={editing.id}
          className="stack select-edit"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const full = form.get("full") === "on";
            try {
              await api(`${base}/collection-items/${editing.id}`, {
                method: "PATCH",
                body: JSON.stringify({
                  start_us: full
                    ? null
                    : Math.round(Number(form.get("start")) * 1e6),
                  end_us: full
                    ? null
                    : Math.round(Number(form.get("end")) * 1e6),
                  note: form.get("note"),
                }),
              });
              setEditing(null);
              await refresh();
            } catch (error) {
              setError((error as Error).message);
            }
          }}
        >
          <strong>Adjust {editing.asset_name}</strong>
          <label>
            <input
              type="checkbox"
              name="full"
              defaultChecked={editing.start_us === null}
            />{" "}
            Use full source file
          </label>
          <div className="inout">
            <label className="field">
              <span>Collection in seconds</span>
              <input
                name="start"
                type="number"
                step={0.001}
                min={0}
                defaultValue={(editing.start_us || 0) / 1e6}
              />
            </label>
            <label className="field">
              <span>Collection out seconds</span>
              <input
                name="end"
                type="number"
                step={0.001}
                min={0}
                defaultValue={(editing.end_us || 0) / 1e6}
              />
            </label>
          </div>
          <label className="field">
            <span>Select note</span>
            <input name="note" maxLength={1000} defaultValue={editing.note} />
          </label>
          <div className="button-row">
            <button className="primary">Save range</button>
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(null)}
            >
              Cancel adjustment
            </button>
          </div>
        </form>
      )}
      {items.map((item) => (
        <div className="select-row" key={item.id}>
          <button
            onClick={() =>
              onOpen({ id: item.asset_id, seek: item.start_us || 0 })
            }
          >
            <Film size={19} />
            <div>
              <strong>{item.asset_name}</strong>
              <span className="timecode">
                {item.start_us === null
                  ? "Full source file"
                  : `${elapsed(item.start_us)} — ${elapsed(item.end_us!)}`}
              </span>
            </div>
          </button>
          {canEdit && (
            <button className="text-button" onClick={() => setEditing(item)}>
              Adjust
            </button>
          )}
          {canEdit && (
            <button
              className="icon-button"
              aria-label={`Remove ${item.asset_name} from collection`}
              onClick={async () => {
                try {
                  await api(`${base}/collection-items/${item.id}`, {
                    method: "DELETE",
                  });
                  await refresh();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <X size={18} />
            </button>
          )}
        </div>
      ))}
      {!items.length && (
        <p className="muted">
          No selects yet. Mark a range in the player, or find suggestions below.
        </p>
      )}
      {canEdit && (
        <form
          className="stack"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setSuggestionNotice(null);
            setSuggestionsIncomplete(false);
            try {
              const result = await api<{
                suggestions: SearchResult[];
                notice: string | null;
                incomplete_processing: boolean;
              }>(`${base}/collections/${collection.id}/suggest`, {
                method: "POST",
                body: JSON.stringify({ instructions: prompt }),
              });
              setSuggestions(result.suggestions);
              setSuggestionNotice(result.notice);
              setSuggestionsIncomplete(result.incomplete_processing);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            <span>Find selects from an instruction</span>
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
              maxLength={500}
              placeholder="e.g. Close-ups of hands at work"
            />
          </label>
          <button className="secondary" disabled={busy}>
            {busy ? "Finding evidence…" : "Suggest ranges"}
            <Search size={16} />
          </button>
        </form>
      )}
      {suggestionNotice && (
        <p className="small muted" role="status">
          {suggestionNotice}
        </p>
      )}
      {suggestionsIncomplete && (
        <p className="small muted" role="status">
          Some footage is still unprocessed. Suggestions use the evidence
          currently available.
        </p>
      )}
      {suggestions.map((item) => (
        <div
          key={`${item.asset_id}:${item.start_us}:${item.end_us}`}
          className="suggestion"
        >
          <div>
            <strong>{item.asset_name}</strong>
            <p className="small muted">
              {item.evidence.map((e) => e.description).join(" ")}
            </p>
            <span className="timecode">
              {elapsed(item.start_us)} — {elapsed(item.end_us)}
            </span>
          </div>
          <button
            className="secondary"
            disabled={addingSuggestions.has(
              `${item.asset_id}:${item.start_us}:${item.end_us}`,
            )}
            onClick={async () => {
              const key = `${item.asset_id}:${item.start_us}:${item.end_us}`;
              if (pendingSuggestions.current.has(key)) return;
              pendingSuggestions.current.add(key);
              setAddingSuggestions(new Set(pendingSuggestions.current));
              try {
                await api(`${base}/collections/${collection.id}/items`, {
                  method: "POST",
                  body: JSON.stringify({
                    asset_id: item.asset_id,
                    start_us: item.start_us,
                    end_us: item.end_us,
                  }),
                });
                setSuggestions((rows) =>
                  rows.filter(
                    (row) =>
                      row.asset_id !== item.asset_id ||
                      row.start_us !== item.start_us ||
                      row.end_us !== item.end_us,
                  ),
                );
                await refresh();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                pendingSuggestions.current.delete(key);
                setAddingSuggestions(new Set(pendingSuggestions.current));
              }
            }}
          >
            Add select
          </button>
        </div>
      ))}
    </div>
  );
}
