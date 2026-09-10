"use client";

import { useState } from "react";
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
  const [relink, setRelink] = useState(false);
  const [quote, setQuote] = useState<Quote | null>(null);
  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await run();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="asset-tools">
      <summary>Source & analysis</summary>
      <div className="stack">
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
            <div className="button-row">
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    setRoots(await api(`${base}/source-roots`));
                    setRelink(true);
                  })
                }
              >
                Relink source
              </button>
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
                  Retry failed processing
                </button>
              )}
            </div>
            {relink &&
              (roots.length ? (
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
              ) : (
                <p className="notice small">
                  Add an explicit source root in the local .env configuration
                  and restart the API before relinking.
                </p>
              ))}
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
                    Configure RUSHES_GEMINI_API_KEY in the server’s .env and
                    restart the API and worker.
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
  return (
    <details
      className="observation-history"
      onToggle={(event) => {
        if (event.currentTarget.open)
          void api<Revision[]>(`${base}/observations/${observation.id}/history`)
            .then(setHistory)
            .catch((error) => setError(error.message));
      }}
    >
      <summary>Provenance & edit history</summary>
      <p className="small muted">
        {observation.producer} · {observation.model}. Original proposed range:{" "}
        {(observation.proposed_start_us / 1e6).toFixed(3)}–
        {(observation.proposed_end_us / 1e6).toFixed(3)} elapsed seconds.
      </p>
      {history === null ? (
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
      {error && <p className="error-text">{error}</p>}
    </details>
  );
}
