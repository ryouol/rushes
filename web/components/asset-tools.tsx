"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Asset, type Observation } from "@/lib/api";

type Quote = {
  amount_milli: number;
  model: string;
  fingerprint: string;
  available: boolean;
  notice: string;
};
export function AssetTools({
  base,
  asset,
  canEdit,
  onChanged,
}: {
  base: string;
  asset: Asset;
  canEdit: boolean;
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [roots, setRoots] = useState<{ id: number; path: string }[]>([]);
  const [rootsRequested, setRootsRequested] = useState(false);
  const [rootsLoading, setRootsLoading] = useState(false);
  const [rootsError, setRootsError] = useState("");
  const [rootsAttempt, setRootsAttempt] = useState(0);
  const [relink, setRelink] = useState(false);
  const [quote, setQuote] = useState<Quote | null>(null);
  const pending = useRef(false);
  useEffect(() => {
    if (!canEdit || !rootsRequested) return;
    const request = new AbortController();
    setRoots([]);
    setRootsError("");
    setRootsLoading(true);
    void api<{ id: number; path: string }[]>(`${base}/source-roots`, {
      signal: request.signal,
    })
      .then((items) => {
        if (!request.signal.aborted) setRoots(items);
      })
      .catch((error) => {
        if (!request.signal.aborted) setRootsError(error.message);
      })
      .finally(() => {
        if (!request.signal.aborted) setRootsLoading(false);
      });
    return () => request.abort();
  }, [base, canEdit, rootsRequested, rootsAttempt]);
  async function action(run: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await run();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <details
      className="asset-tools"
      onToggle={(event) => {
        if (event.currentTarget.open) setRootsRequested(true);
      }}
    >
      <summary>Footage details & analysis</summary>
      <div className="stack">
        {busy && (
          <p className="small muted" role="status">
            Working…
          </p>
        )}
        <p className="output-path">
          Imported as {asset.import_relative_path || asset.relative_path}
        </p>
        {asset.duplicate_of_id && (
          <p className="small muted">
            Identical source content already exists in this workspace.
            Collections can reuse a source without copying it.
          </p>
        )}
        <button
          className="secondary"
          disabled={busy}
          onClick={() =>
            action(async () => {
              const result = await api<{
                state: string;
                verification?: string;
              }>(`${base}/assets/${asset.id}/source-status`);
              setStatus(
                `Source ${result.state}${result.verification ? ` · checked by ${result.verification}` : ""}. Exports verify the full content hash.`,
              );
            })
          }
        >
          Check source availability
        </button>
        {status && (
          <p className="notice small" role="status">
            {status}
          </p>
        )}
        {canEdit && (
          <>
            {rootsLoading && (
              <p className="small muted" role="status">
                Checking source-folder availability…
              </p>
            )}
            {rootsError && (
              <div className="stack">
                <p className="error-text" role="alert">
                  {rootsError}
                </p>
                <button
                  className="secondary"
                  disabled={rootsLoading}
                  onClick={() => setRootsAttempt((attempt) => attempt + 1)}
                >
                  Retry source-folder check
                </button>
              </div>
            )}
            <div className="button-row">
              {roots.length > 0 && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => setRelink((open) => !open)}
                  aria-expanded={relink}
                >
                  Relink source
                </button>
              )}
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    setQuote(
                      await api(`${base}/assets/${asset.id}/analysis-estimate`),
                    );
                  })
                }
              >
                Review analysis estimate
              </button>
              {asset.can_retry && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api(`${base}/assets/${asset.id}/retry`, {
                        method: "POST",
                      });
                      setStatus(
                        "Recovery queued using the original operation. Completed checkpoints and existing settlements are retained.",
                      );
                      await onChanged();
                    })
                  }
                >
                  Resume processing
                </button>
              )}
            </div>
            {relink && roots.length > 0 && (
              <form
                className="stack"
                onSubmit={(event) => {
                  event.preventDefault();
                  const data = new FormData(event.currentTarget);
                  void action(async () => {
                    await api(`${base}/assets/${asset.id}/relink`, {
                      method: "POST",
                      body: JSON.stringify({
                        root: Number(data.get("root")),
                        relative_path: data.get("path"),
                      }),
                    });
                    setRelink(false);
                    setStatus(
                      "Source relinked after a matching SHA-256 content check.",
                    );
                    await onChanged();
                  });
                }}
              >
                <label className="field">
                  <span>Configured source root</span>
                  <select name="root">
                    {roots.map((root) => (
                      <option key={root.id} value={root.id}>
                        {root.path}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Relative replacement path</span>
                  <input
                    name="path"
                    required
                    maxLength={2000}
                    placeholder="Day 1/Camera A/clip.mov"
                  />
                </label>
                <p className="small muted">
                  Only identical source bytes can be relinked. Import changed
                  footage as a new source.
                </p>
                <button className="primary" disabled={busy}>
                  Verify and relink
                </button>
              </form>
            )}
            {quote && (
              <div className="stack notice">
                <strong>
                  {(quote.amount_milli / 1000).toFixed(2)} estimated credits ·{" "}
                  {quote.model}
                </strong>
                <p className="small">
                  {quote.notice} Derived footage is sent to Gemini. Requests
                  with uncertain outcomes are recorded and are not automatically
                  repeated.
                </p>
                {!quote.available && (
                  <p className="small">
                    Analysis is unavailable on this instance. Ask the workspace
                    operator to configure the processing service.
                  </p>
                )}
                <div className="button-row">
                  <button
                    className="primary"
                    disabled={busy || !quote.available}
                    onClick={() =>
                      action(async () => {
                        await api(`${base}/assets/${asset.id}/reanalyze`, {
                          method: "POST",
                          body: JSON.stringify({
                            amount_milli: quote.amount_milli,
                            model: quote.model,
                            fingerprint: quote.fingerprint,
                          }),
                        });
                        setQuote(null);
                        setStatus(
                          "New analysis queued. Corrections remain in the worklog.",
                        );
                        await onChanged();
                      })
                    }
                  >
                    Start new analysis
                  </button>
                  <button className="secondary" onClick={() => setQuote(null)}>
                    Dismiss estimate
                  </button>
                </div>
              </div>
            )}
          </>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}

type Revision = {
  id: string;
  version: number;
  created_at: string;
  before: { description: string; start_us: number; end_us: number };
  after: { description: string; start_us: number; end_us: number };
};
export function ObservationHistory({
  base,
  observation,
}: {
  base: string;
  observation: Observation;
}) {
  const [history, setHistory] = useState<Revision[] | null>(null),
    [error, setError] = useState("");
  const historyRequest = useRef<AbortController | null>(null);
  useEffect(() => () => historyRequest.current?.abort(), []);
  return (
    <details
      className="observation-history"
      onToggle={(event) => {
        historyRequest.current?.abort();
        if (!event.currentTarget.open) return;
        const request = new AbortController();
        historyRequest.current = request;
        setError("");
        void api<Revision[]>(`${base}/observations/${observation.id}/history`, {
          signal: request.signal,
        })
          .then((items) => {
            if (!request.signal.aborted) setHistory(items);
          })
          .catch((error) => {
            if (!request.signal.aborted) setError(error.message);
          });
      }}
    >
      <summary>Provenance & edit history</summary>
      <p className="small muted">
        {observation.producer} · {observation.model}. Original proposed range:{" "}
        {(observation.proposed_start_us / 1e6).toFixed(3)}–
        {(observation.proposed_end_us / 1e6).toFixed(3)} elapsed seconds.
      </p>
      {error ? null : history === null ? (
        <p className="small">Loading history…</p>
      ) : history.length ? (
        history.map((revision) => (
          <div key={revision.id} className="history-entry">
            <strong>
              Version {revision.version} → {revision.version + 1}
            </strong>
            <p>{revision.before.description}</p>
            <span className="timecode">
              {(revision.before.start_us / 1e6).toFixed(3)}–
              {(revision.before.end_us / 1e6).toFixed(3)} s
            </span>
            <p className="small muted">
              Saved {new Date(revision.created_at).toLocaleString()}
            </p>
          </div>
        ))
      ) : (
        <p className="small muted">No corrections recorded.</p>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
