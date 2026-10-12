"use client";

import { useId, useRef, useState } from "react";
import { api, ApiError, type Asset, type CategoryReview } from "@/lib/api";

export function CategoryReviewTools({
  asset,
  base,
  canEdit,
  onChanged,
}: {
  asset: Asset;
  base: string;
  canEdit: boolean;
  onChanged: () => Promise<void>;
}) {
  const helpId = useId();
  const current = asset.organization?.category_review;
  const reviewed = current?.categories != null;
  const [draft, setDraft] = useState<{ text: string; version: number } | null>(
    null,
  );
  const [history, setHistory] = useState<CategoryReview[] | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && e.status === 409) await onChanged();
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  async function save(categories: string[] | null, version: number) {
    await api(`${base}/assets/${asset.id}/categories`, {
      method: "PUT",
      body: JSON.stringify({ categories, version }),
    });
    setDraft(null);
    setHistory(null);
    setStatus(
      categories === null
        ? "AI categories restored."
        : "Reviewed categories saved. They will survive new analysis.",
    );
    await onChanged();
  }
  return (
    <details className="asset-tools category-review">
      <summary>Review categories</summary>
      <div className="stack">
        <p className="small">
          {reviewed
            ? `Reviewed categories · version ${current.version}`
            : "AI categories"}
          :{" "}
          {asset.organization?.categories.map((c) => c.name).join(", ") ||
            "Uncategorized"}
        </p>
        <p id={helpId} className="small muted">
          Reviewed categories replace the full list for this file and remain
          after new analysis. Saving uses no analysis credits. Leave the list
          empty to mark it Uncategorized.
        </p>
        {canEdit && !draft && (
          <div className="button-row">
            <button
              className="secondary"
              disabled={busy || asset.organization?.has_more}
              onClick={() => {
                setError("");
                setStatus("");
                setDraft({
                  text: asset.organization.categories
                    .map((c) => c.name)
                    .join("\n"),
                  version: current?.version || 0,
                });
              }}
            >
              Edit categories
            </button>
            {reviewed && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void run(() => save(null, current.version))}
              >
                Use AI categories
              </button>
            )}
          </div>
        )}
        {canEdit && asset.organization?.has_more && (
          <p className="small">
            This file has more than 100 categories. Review supports up to 100;
            editing this truncated list is unavailable.
          </p>
        )}
        {!canEdit && (
          <p className="small muted">
            Workspace owners and editors can review categories.
          </p>
        )}
        {canEdit && draft && (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() =>
                save(
                  draft.text
                    .split("\n")
                    .map((s) => s.trim())
                    .filter(Boolean),
                  draft.version,
                ),
              );
            }}
          >
            <label className="field">
              <span>Categories, one per line</span>
              <textarea
                rows={4}
                maxLength={3700}
                aria-describedby={helpId}
                disabled={busy}
                value={draft.text}
                onChange={(e) => setDraft({ ...draft, text: e.target.value })}
              />
            </label>
            <p className="small muted">
              Up to 100 short English names, 36 characters each.
            </p>
            <div className="button-row">
              <button className="primary" disabled={busy}>
                {busy ? "Saving…" : "Save reviewed categories"}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setError("");
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
        <button
          className="text-button"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              setHistory(
                await api<CategoryReview[]>(
                  `${base}/assets/${asset.id}/category-history`,
                ),
              );
            })
          }
        >
          Category review history
        </button>
        {history && (
          <div className="stack small">
            <p>
              {history.length
                ? "Latest 20 reviews"
                : "No category reviews yet."}
            </p>
            {history.map((review) => (
              <p key={review.id}>
                v{review.version} ·{" "}
                {new Date(review.created_at).toLocaleString()} · Reviewer{" "}
                {review.user_name || "Workspace member"}
                <br />
                {review.categories === null
                  ? "Restored AI categories"
                  : review.categories.map((c) => c.name).join(", ") ||
                    "Uncategorized"}
              </p>
            ))}
          </div>
        )}
        {status && (
          <p className="notice small" role="status">
            {status}
          </p>
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
