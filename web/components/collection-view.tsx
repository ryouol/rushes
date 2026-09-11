"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Film, Search, X } from "lucide-react";
import {
  api,
  elapsed,
  type Collection,
  type CollectionItem,
  type SearchResult,
} from "@/lib/api";

export function CollectionView({
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
  ) => Promise<void>;
}) {
  const [items, setItems] = useState<CollectionItem[]>([]),
    [error, setError] = useState("");
  const [editing, setEditing] = useState<CollectionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [mutating, setMutating] = useState(false);
  const mutationPending = useRef(false);
  const [exporting, setExporting] = useState(false);
  async function previewExport(kind: Parameters<typeof onExport>[0]) {
    if (exporting) return;
    setExporting(true);
    setError("");
    try {
      await onExport(kind);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setExporting(false);
    }
  }
  async function mutate(run: () => Promise<void>, success: string) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    setMutating(true);
    setError("");
    setNotice("");
    try {
      await run();
      setNotice(success);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      mutationPending.current = false;
      setMutating(false);
    }
  }
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
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [base, collection.id]);
  useEffect(() => {
    setLoading(true);
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
              disabled={!items.length || exporting}
              onClick={() => void previewExport("copies")}
            >
              Organized copies
            </button>
            <button
              className="primary"
              disabled={!items.length || exporting}
              onClick={() => void previewExport("clips")}
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
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {exporting && (
        <p className="notice" role="status">
          Preparing your export preview…
        </p>
      )}
      {loading && (
        <p className="muted" role="status">
          Loading selects…
        </p>
      )}
      {canEdit && items.length > 0 && (
        <>
          <details className="xml-options">
            <summary>Selection data</summary>
            <div className="button-row">
              <button
                className="secondary"
                disabled={exporting}
                onClick={() => void previewExport("selections_json")}
              >
                Selection JSON
              </button>
              <button
                className="secondary"
                disabled={exporting}
                onClick={() => void previewExport("selections_csv")}
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
              <button
                className="secondary"
                disabled={exporting}
                onClick={() => void previewExport("fcp7xml")}
              >
                Preview FCP7 XML
              </button>
              <button
                className="secondary"
                disabled={exporting}
                onClick={() => void previewExport("fcpxml")}
              >
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
            await mutate(async () => {
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
            }, "Select updated.");
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
            <button className="primary" disabled={mutating}>
              {mutating ? "Saving…" : "Save range"}
            </button>
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
            <button
              className="text-button"
              disabled={mutating}
              onClick={() => setEditing(item)}
            >
              Adjust
            </button>
          )}
          {canEdit && (
            <button
              className="icon-button"
              aria-label={`Remove ${item.asset_name} from collection`}
              disabled={mutating}
              onClick={() =>
                void mutate(async () => {
                  await api(`${base}/collection-items/${item.id}`, {
                    method: "DELETE",
                  });
                  await refresh();
                }, "Select removed from collection.")
              }
            >
              <X size={18} />
            </button>
          )}
        </div>
      ))}
      {!loading && !items.length && (
        <p className="muted">
          No selects yet. Mark a range in the player, or find suggestions below.
        </p>
      )}
      {canEdit && (
        <form
          className="stack"
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            setBusy(true);
            setError("");
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
              setNotice(
                `${result.suggestions.length} suggested ${result.suggestions.length === 1 ? "range" : "ranges"} found.`,
              );
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
              setError("");
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
                setNotice("Suggested range saved to collection.");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                pendingSuggestions.current.delete(key);
                setAddingSuggestions(new Set(pendingSuggestions.current));
              }
            }}
          >
            {addingSuggestions.has(
              `${item.asset_id}:${item.start_us}:${item.end_us}`,
            )
              ? "Saving…"
              : "Add select"}
          </button>
        </div>
      ))}
    </div>
  );
}
