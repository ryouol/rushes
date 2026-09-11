"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Upload } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { storageSize } from "@/lib/format";
import { Dialog } from "@/components/dialog";

export function ImportDialog({
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
  const disposed = useRef(false);
  const uploadPending = useRef(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null),
    directory = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<
      { name: string; percent: number; state: string }[]
    >([]),
    [busy, setBusy] = useState(false),
    [checkingStorage, setCheckingStorage] = useState(false),
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
    if (!open) return;
    const request = new AbortController();
    void api<typeof roots>(`${base}/source-roots`, { signal: request.signal })
      .then((items) => {
        if (!request.signal.aborted) setRoots(items);
      })
      .catch((error) => {
        if (!request.signal.aborted) setError(error.message);
      });
    return () => request.abort();
  }, [open, base]);
  useEffect(() => {
    disposed.current = false;
    return () => {
      disposed.current = true;
    };
  }, []);
  async function upload(files: File[]) {
    if (!files?.length || uploadPending.current) return;
    uploadPending.current = true;
    setBusy(true);
    setError("");
    const list = Array.from(files).filter((file) =>
      /\.(mp4|mov|mkv|mxf|avi|mts|m2ts|webm|m4v)$/i.test(file.name),
    );
    if (!list.length) {
      setError("No supported video files were selected.");
      setBusy(false);
      uploadPending.current = false;
      return;
    }
    setProgress([]);
    setCheckingStorage(true);
    // Refresh at selection time: another upload or export may have used the disk.
    // This estimate is advisory; every upload and processing step still checks space.
    const capacity = await api<{
      usable_storage_bytes?: number;
      minimum_free_bytes?: number;
    }>(`${base}/settings`, {
      signal: AbortSignal.timeout(4000),
      cache: "no-store",
    }).catch(() => null);
    if (disposed.current) {
      uploadPending.current = false;
      return;
    }
    setCheckingStorage(false);
    const available = capacity?.usable_storage_bytes;
    const estimated = 2 * list.reduce((total, file) => total + file.size, 0);
    if (
      typeof available === "number" &&
      Number.isFinite(available) &&
      available >= 0 &&
      (available === 0 || estimated > available)
    ) {
      const reserve = capacity?.minimum_free_bytes;
      const reserveLabel =
        typeof reserve === "number" && Number.isFinite(reserve) && reserve >= 0
          ? `the ${storageSize(reserve)} server reserve`
          : "the server reserve";
      setError(
        `Not enough server storage for this selection. About ${storageSize(estimated)} is needed for uploads and working copies; ${storageSize(available)} is available after ${reserveLabel}. Manage files and exports to free space, or select fewer files. Check available storage in Settings. This is an estimate; processing may need more space.`,
      );
      setBusy(false);
      uploadPending.current = false;
      return;
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
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
          const update = (percent: number, state: string) => {
            if (disposed.current) return;
            setProgress((rows) =>
              rows[index]?.percent === percent && rows[index]?.state === state
                ? rows
                : rows.map((row, i) =>
                    i === index ? { ...row, percent, state } : row,
                  ),
            );
          };
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
              request.status >= 200 && request.status < 300
                ? "Queued for processing"
                : detail,
            );
            resolve();
          };
          request.onerror = () => {
            update(0, "Disconnected; reselect this file");
            resolve();
          };
          request.onabort = () => {
            update(0, "Upload interrupted; reselect this file");
            resolve();
          };
          request.send(file);
        });
        if (!disposed.current) await onImported();
      }
    }
    try {
      await Promise.all([next(), next()]);
    } catch (error) {
      if (!disposed.current) setError((error as Error).message);
    } finally {
      window.removeEventListener("beforeunload", warn);
      if (!disposed.current) setBusy(false);
      uploadPending.current = false;
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Import footage"
      description="Select files or a folder. Originals stay in place; selected uploads are copied into private storage on the RUSHES server."
    >
      <div className="stack">
        <div
          className={`import-drop ${dragging ? "is-dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={(event) => {
            if (
              !(event.relatedTarget instanceof Node) ||
              !event.currentTarget.contains(event.relatedTarget)
            )
              setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (!busy) void upload(Array.from(event.dataTransfer.files));
          }}
        >
          <Upload size={30} />
          <h2>
            {dragging ? "Drop videos to upload" : "Bring your footage in"}
          </h2>
          <p className="small muted">
            Drop video files here, or choose files or a folder.
          </p>
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
        {checkingStorage && <p role="status">Checking server storage…</p>}
        <p className="small muted">
          Allow about twice the selected files’ size for uploads and working
          copies, in addition to the server’s free-space reserve. This is an
          estimate; processing may need more space.
        </p>
        <p className="small muted">
          Keep this tab open until uploads finish. Completed files process in
          the background. Interrupted uploads require file reselection.
          Configured Gemini analysis sends derived clips and transcript context
          to Google and uses processing credits. When enabled, Modal processes
          derived audio, worklog text and search queries. Settings shows the
          active processing services.
        </p>
        {progress.length > 0 && (
          <div className="upload-list">
            <p className="small" role="status">
              {busy ? "Uploading — keep this tab open." : "Uploads finished."}{" "}
              {
                progress.filter(
                  (file) => file.state === "Queued for processing",
                ).length
              }{" "}
              of {progress.length} files queued for processing.
            </p>
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
            <details className="advanced-import">
              <summary>Import from server folder</summary>
              <label className="field">
                <span>Configured source folder</span>
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
                      if (rootRequest.current === request)
                        setRootLoading(false);
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
              {rootLoading && (
                <p role="status">Loading selected source root…</p>
              )}
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
                          setError(
                            failures.map((file) => file.error).join(". "),
                          );
                        else onOpenChange(false);
                        if (!disposed.current) await onImported();
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {busy
                      ? "Indexing…"
                      : `Index ${checked.size} selected files`}
                  </button>
                </>
              )}
            </details>
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
