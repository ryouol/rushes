"use client";
import * as Dialog from "@radix-ui/react-dialog";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowDownToLine,
  Check,
  ChevronLeft,
  Clock3,
  FilePenLine,
  Film,
  Plus,
  X,
} from "lucide-react";
import { AssetTools, ObservationHistory } from "./asset-tools";
import {
  api,
  elapsed,
  type Asset,
  type Collection,
  type Observation,
  type Workspace,
} from "@/lib/api";

export function Player({
  assetId,
  seekUs,
  workspace,
  collections,
  onClose,
  onExport,
}: {
  assetId: string;
  seekUs?: number;
  workspace: Workspace;
  collections: Collection[];
  onClose: () => void;
  onExport: (body: object) => Promise<void>;
}) {
  const base = `/workspaces/${workspace.id}`;
  const [asset, setAsset] = useState<Asset | null>(null),
    [observations, setObservations] = useState<Observation[]>([]),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0);
  const [error, setError] = useState(""),
    [current, setCurrent] = useState(seekUs || 0);
  const [start, setStart] = useState(seekUs || 0),
    [end, setEnd] = useState(0),
    [collection, setCollection] = useState(collections[0]?.id || "");
  const [savedKey, setSavedKey] = useState<string | null>(null),
    [edit, setEdit] = useState<Observation | null>(null),
    [saving, setSaving] = useState(false),
    [kind, setKind] = useState("all");
  const [note, setNote] = useState("");
  const noteRequest = useRef(crypto.randomUUID());
  const [selectBusy, setSelectBusy] = useState(false);
  const selectPending = useRef(false);
  const selectionKey = JSON.stringify([assetId, collection, start, end]);
  const fullKey = JSON.stringify([assetId, collection, "full"]);
  const saved = savedKey === selectionKey;
  async function saveSelect(full = false) {
    if (selectPending.current) return;
    selectPending.current = true;
    setSelectBusy(true);
    const key = full ? fullKey : selectionKey;
    try {
      await api(`${base}/collections/${collection}/items`, {
        method: "POST",
        body: JSON.stringify({
          asset_id: assetId,
          ...(full ? {} : { start_us: start, end_us: end }),
        }),
      });
      setSavedKey(key);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      selectPending.current = false;
      setSelectBusy(false);
    }
  }
  const video = useRef<HTMLVideoElement>(null),
    reverse = useRef<ReturnType<typeof setInterval> | null>(null);
  const canEdit = workspace.role !== "viewer";
  const loadAbort = useRef<AbortController | null>(null);
  const anchor = useRef<number | undefined>(seekUs);
  const load = useCallback(async () => {
    loadAbort.current?.abort();
    const controller = new AbortController();
    loadAbort.current = controller;
    const near =
      anchor.current === undefined ? "" : `&near_us=${anchor.current}`;
    try {
      const [source, log] = await Promise.all([
        api<Asset>(`${base}/assets/${assetId}`, { signal: controller.signal }),
        api<{ items: Observation[]; total: number; offset: number }>(
          `${base}/assets/${assetId}/observations?offset=${offset}&kind=${kind}${near}`,
          { signal: controller.signal },
        ),
      ]);
      if (controller.signal.aborted) return;
      anchor.current = undefined;
      setOffset(log.offset);
      setAsset((previous) =>
        JSON.stringify(previous) === JSON.stringify(source) ? previous : source,
      );
      setObservations((previous) =>
        previous.length === log.items.length &&
        previous.every(
          (row, index) =>
            row.id === log.items[index].id &&
            row.version === log.items[index].version,
        )
          ? previous
          : log.items,
      );
      setTotal(log.total);
      setEnd((existing) => existing || source.duration_us || 0);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    }
  }, [base, assetId, offset, kind]);
  useEffect(() => {
    void load();
    return () => loadAbort.current?.abort();
  }, [load]);
  useEffect(() => {
    if (
      asset?.status &&
      ["queued", "processing", "preview_ready"].includes(asset.status)
    ) {
      const interval = setInterval(() => void load(), 4000);
      return () => clearInterval(interval);
    }
  }, [asset?.status, load]);
  function stopReverse() {
    if (reverse.current) {
      clearInterval(reverse.current);
      reverse.current = null;
    }
  }
  function seek(us: number) {
    stopReverse();
    if (video.current) video.current.currentTime = us / 1e6;
    setCurrent(us);
  }
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (
        (event.target as HTMLElement).closest(
          "input,textarea,select,[contenteditable=true]",
        ) ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      )
        return;
      const media = video.current;
      if (!media) return;
      if (["j", "k", "l", "i", "o", " "].includes(event.key.toLowerCase()))
        event.preventDefault();
      switch (event.key.toLowerCase()) {
        case "i":
          setStart(Math.round(media.currentTime * 1e6));

          break;
        case "o":
          setEnd(Math.round(media.currentTime * 1e6));

          break;
        case "k":
          stopReverse();
          media.pause();
          break;
        case "l":
          stopReverse();
          media.playbackRate = media.paused
            ? 1
            : Math.min(4, media.playbackRate * 2);
          void media.play().catch(() => {});
          break;
        case "j":
          stopReverse();
          media.pause();
          reverse.current = setInterval(() => {
            media.currentTime = Math.max(0, media.currentTime - 0.16);
          }, 80);
          break;
        case " ":
          stopReverse();
          if (media.paused) void media.play().catch(() => {});
          else media.pause();
          break;
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      stopReverse();
    };
  }, []);
  async function saveCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!edit) return;
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const updated = await api<Observation>(
        `${base}/observations/${edit.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            description: form.get("description"),
            start_us: Math.round(Number(form.get("start")) * 1e6),
            end_us: Math.round(Number(form.get("end")) * 1e6),
            version: edit.version,
          }),
        },
      );
      setObservations((rows) =>
        rows.map((row) => (row.id === updated.id ? updated : row)),
      );
      setEdit(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const valid = start >= 0 && end > start && end <= (asset?.duration_us || 0),
    timeline = asset?.timelines?.find((t) => t.kind === "source")?.details;
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="player-overlay" />
        <Dialog.Content className="player-dialog">
          <div className="player-header">
            <Dialog.Close className="icon-button" aria-label="Close player">
              <ChevronLeft size={22} />
            </Dialog.Close>
            <div>
              <Dialog.Title>{asset?.name || "Loading source…"}</Dialog.Title>
              <Dialog.Description>
                {timeline
                  ? `${timeline.width} × ${timeline.height} · ${timeline.average_rate} fps${timeline.constant_frame_rate ? " · CFR" : " · Variable presentation timing"}`
                  : "Source media and timestamped worklog"}
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="icon-button"
              aria-label="Close media review"
            >
              <X size={21} />
            </Dialog.Close>
          </div>
          {error && (
            <div className="notice danger" role="alert">
              {error}
              <button
                className="icon-button"
                aria-label="Dismiss player error"
                onClick={() => setError("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          <div className="player-layout">
            <div className="player-stage">
              <div className="video-well">
                {asset?.has_preview ? (
                  <video
                    ref={video}
                    src={`/api${base}/assets/${assetId}/media/proxy`}
                    controls
                    playsInline
                    preload="metadata"
                    onLoadedMetadata={() => {
                      if (seekUs && video.current)
                        video.current.currentTime = seekUs / 1e6;
                    }}
                    onTimeUpdate={(e) =>
                      setCurrent(Math.round(e.currentTarget.currentTime * 1e6))
                    }
                    aria-label={`Preview of ${asset.name}`}
                  />
                ) : (
                  <div className="video-pending">
                    <Film size={40} />
                    <h2>Preview is being prepared</h2>
                    <p>
                      {asset?.error ||
                        "Processing continues in the background. You can close this view and return later."}
                    </p>
                  </div>
                )}
              </div>
              <div className="transport-info">
                <span className="timecode">ELAPSED {elapsed(current)}</span>
                <span className="small muted">
                  {timeline?.source_timecode
                    ? `Source start TC ${timeline.source_timecode}`
                    : "No source timecode supplied"}
                </span>
              </div>
              <div className="keyboard-hints">
                <span>
                  <kbd>J</kbd> Reverse shuttle
                </span>
                <span>
                  <kbd>K</kbd> Pause
                </span>
                <span>
                  <kbd>L</kbd> Play / faster
                </span>
                <span>
                  <kbd>I</kbd> In
                </span>
                <span>
                  <kbd>O</kbd> Out
                </span>
              </div>
              {canEdit && asset?.has_preview && (
                <div className="selection-panel">
                  <div className="section-heading">
                    <h2>Make a select</h2>
                    <span className="timecode">
                      {valid
                        ? `${((end - start) / 1e6).toFixed(3)} sec`
                        : "Adjust in/out"}
                    </span>
                  </div>
                  <div className="inout">
                    <label className="field">
                      <span>
                        In{" "}
                        <button
                          className="text-button"
                          onClick={() => {
                            setStart(current);
                          }}
                        >
                          Set to playhead
                        </button>
                      </span>
                      <input
                        aria-label="Selection in seconds"
                        type="number"
                        min={0}
                        step={0.001}
                        value={start / 1e6}
                        onChange={(e) => {
                          setStart(Math.round(Number(e.target.value) * 1e6));
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>
                        Out{" "}
                        <button
                          className="text-button"
                          onClick={() => {
                            setEnd(current);
                          }}
                        >
                          Set to playhead
                        </button>
                      </span>
                      <input
                        aria-label="Selection out seconds"
                        type="number"
                        min={0}
                        max={(asset.duration_us || 0) / 1e6}
                        step={0.001}
                        value={end / 1e6}
                        onChange={(e) => {
                          setEnd(Math.round(Number(e.target.value) * 1e6));
                        }}
                      />
                    </label>
                  </div>
                  <p className="small muted">
                    In/out values are elapsed seconds. Browser seeking and
                    automatic event locations are approximate. Exports select
                    decoded source frames.
                  </p>
                  <div className="select-actions">
                    <label className="field">
                      <span>Save to collection</span>
                      <select
                        aria-label="Save to collection"
                        value={collection}
                        onChange={(e) => {
                          setCollection(e.target.value);
                        }}
                      >
                        <option value="">Choose a collection</option>
                        {collections.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="primary"
                      disabled={!valid || !collection || saved || selectBusy}
                      onClick={() => saveSelect()}
                    >
                      {saved ? (
                        <>
                          <Check size={17} />
                          Saved
                        </>
                      ) : (
                        <>
                          <Plus size={17} />
                          Add select
                        </>
                      )}
                    </button>
                  </div>
                  {!collections.length && (
                    <p className="small muted">
                      Create a collection from your project’s Collections tab to
                      save selects.
                    </p>
                  )}
                  <div className="button-row">
                    <button
                      className="secondary"
                      disabled={!valid}
                      onClick={() =>
                        onExport({
                          kind: "clips",
                          asset_id: assetId,
                          start_us: start,
                          end_us: end,
                        })
                      }
                    >
                      <ArrowDownToLine size={16} />
                      Export this range
                    </button>
                    <button className="text-button" onClick={() => seek(start)}>
                      Preview from in point
                    </button>
                    {collection && (
                      <button
                        className="text-button"
                        disabled={selectBusy || savedKey === fullKey}
                        onClick={() => saveSelect(true)}
                      >
                        Add full source
                      </button>
                    )}
                  </div>
                </div>
              )}
              {asset?.error && (
                <div className="notice small">{asset.error}</div>
              )}
              {asset && (
                <AssetTools
                  base={base}
                  asset={asset}
                  canEdit={canEdit}
                  onChanged={load}
                />
              )}
            </div>
            <aside className="worklog">
              <div className="worklog-heading">
                <h2>
                  Worklog <span className="heading-count">{total}</span>
                </h2>
                <Clock3 size={18} />
              </div>
              <div className="worklog-filter">
                <label className="field">
                  <span className="sr-only">Worklog type</span>
                  <select
                    aria-label="Worklog type"
                    value={kind}
                    onChange={(e) => {
                      anchor.current = current;
                      setOffset(0);
                      setKind(e.target.value);
                    }}
                  >
                    <option value="all">All observations</option>
                    <option value="speech">Transcript</option>
                    <option value="visual">Visual & other</option>
                  </select>
                </label>
                <span className="small muted">Click a timestamp to seek</span>
              </div>
              {canEdit && asset?.has_preview && (
                <details className="manual-note">
                  <summary>Add a worklog note</summary>
                  <form
                    className="stack"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      setSaving(true);
                      try {
                        await api(`${base}/assets/${assetId}/observations`, {
                          method: "POST",
                          body: JSON.stringify({
                            description: note,
                            start_us: start,
                            end_us: end,
                            request_id: noteRequest.current,
                          }),
                        });
                        setNote("");
                        noteRequest.current = crypto.randomUUID();
                        await load();
                      } catch (error) {
                        setError((error as Error).message);
                      } finally {
                        setSaving(false);
                      }
                    }}
                  >
                    <label className="field">
                      <span>Note for the selected range</span>
                      <textarea
                        aria-label="New worklog note"
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        required
                        maxLength={4000}
                        rows={3}
                      />
                    </label>
                    <p className="small muted">
                      Uses the current selection: {elapsed(start)}–
                      {elapsed(end)}. Adjust in/out before saving.
                    </p>
                    <button className="primary" disabled={!valid || saving}>
                      Save note
                    </button>
                  </form>
                </details>
              )}
              <div className="worklog-items">
                {observations.length ? (
                  observations.map((observation) => (
                    <article
                      className={`worklog-item ${observation.start_us <= current && observation.end_us > current ? "current" : ""}`}
                      key={observation.id}
                    >
                      <div className="worklog-meta">
                        <button
                          className="timecode"
                          onClick={() => seek(observation.start_us)}
                        >
                          {elapsed(observation.start_us)}
                        </button>
                        <span>{observation.kind.replaceAll("_", " ")}</span>
                        {canEdit && (
                          <button
                            className="icon-button"
                            aria-label={`Edit observation at ${elapsed(observation.start_us)}`}
                            onClick={() => {
                              setEdit(observation);
                              setError("");
                            }}
                          >
                            <FilePenLine size={16} />
                          </button>
                        )}
                      </div>
                      {edit?.id === observation.id ? (
                        <form
                          className="stack correction-form"
                          onSubmit={saveCorrection}
                        >
                          <label className="field">
                            <span>Description</span>
                            <textarea
                              name="description"
                              defaultValue={edit.description}
                              rows={4}
                              required
                              maxLength={4000}
                            />
                          </label>
                          <div className="inout">
                            <label className="field">
                              <span>Start seconds</span>
                              <input
                                name="start"
                                type="number"
                                step={0.001}
                                min={0}
                                defaultValue={edit.start_us / 1e6}
                                required
                              />
                            </label>
                            <label className="field">
                              <span>End seconds</span>
                              <input
                                name="end"
                                type="number"
                                step={0.001}
                                defaultValue={edit.end_us / 1e6}
                                required
                              />
                            </label>
                          </div>
                          <div className="button-row">
                            <button className="primary" disabled={saving}>
                              {saving ? "Saving…" : "Save correction"}
                            </button>
                            <button
                              type="button"
                              className="secondary"
                              onClick={() => setEdit(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : (
                        <p>{observation.description}</p>
                      )}
                      <div className="evidence-meta">
                        <span>
                          {observation.review_status === "corrected"
                            ? "Edited by user"
                            : `${observation.producer} · ${observation.uncertainty}`}
                        </span>
                        <span>v{observation.version}</span>
                      </div>
                      <ObservationHistory
                        base={base}
                        observation={observation}
                      />
                    </article>
                  ))
                ) : (
                  <div className="worklog-empty">
                    <FilePenLine size={30} />
                    <h2>No observations yet</h2>
                    <p>
                      {asset?.status === "partial"
                        ? "No speech was detected, or visual analysis needs configuration. Source previews remain available for manual review."
                        : "Transcripts and visual observations appear here as processing completes."}
                    </p>
                  </div>
                )}
              </div>
              {total > 100 && (
                <div className="pagination">
                  <button
                    className="secondary"
                    disabled={offset === 0}
                    onClick={() => setOffset((o) => o - 100)}
                  >
                    Previous
                  </button>
                  <span>
                    {offset + 1}–{Math.min(offset + 100, total)}
                  </span>
                  <button
                    className="secondary"
                    disabled={offset + 100 >= total}
                    onClick={() => setOffset((o) => o + 100)}
                  >
                    Next
                  </button>
                </div>
              )}
              <p className="worklog-footnote">
                Model locations are proposals. Human corrections are versioned
                and retained when processing is retried.
              </p>
            </aside>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
