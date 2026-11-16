"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type OrganizationCategory } from "@/lib/api";

export function CategoryBrowser({
  base,
  projectId,
  value,
  onChange,
}: {
  base: string;
  projectId: string;
  value: string;
  onChange: (category: OrganizationCategory) => void;
}) {
  const [items, setItems] = useState<OrganizationCategory[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const attemptedAfter = useRef<string | null>(null);
  const results = useRef<HTMLDivElement>(null);
  const load = useCallback(
    async (after: string | null) => {
      request.current?.abort();
      const active = new AbortController();
      request.current = active;
      attemptedAfter.current = after;
      setLoading(true);
      setError("");
      try {
        const page = await api<{
          items: OrganizationCategory[];
          next_cursor: string | null;
        }>(
          `${base}/projects/${projectId}/categories${after ? `?after=${encodeURIComponent(after)}` : ""}`,
          {
            signal: active.signal,
          },
        );
        if (active.signal.aborted) return;
        setItems((current) =>
          after === null
            ? page.items
            : [
                ...(current ?? []),
                ...page.items.filter(
                  (item) => !current?.some((old) => old.id === item.id),
                ),
              ],
        );
        setNextCursor(page.next_cursor);
      } catch (failure) {
        if (!active.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Categories could not load.",
          );
      } finally {
        if (!active.signal.aborted) setLoading(false);
      }
    },
    [base, projectId],
  );
  useEffect(() => {
    void load(null);
    return () => request.current?.abort();
  }, [load]);

  function requestPage(after: string | null) {
    // Keep keyboard focus when a retry or final-page button disappears.
    results.current?.focus();
    void load(after);
  }

  return (
    <>
      <div
        ref={results}
        className="category-browser-results"
        role="group"
        aria-label="Browse all categories"
        tabIndex={-1}
      >
        {items?.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={value === item.id}
            onClick={() => onChange(item)}
          >
            {item.name} <span>{item.asset_count}</span>
          </button>
        ))}
      </div>
      <p role="status">
        {loading
          ? "Loading categories…"
          : items === null
            ? ""
            : `${items.length} categories loaded.`}
      </p>
      {error && (
        <p role="alert">
          Categories could not update.{" "}
          {items?.length
            ? "Previously loaded categories remain available. "
            : ""}
          {error}
        </p>
      )}
      <div className="button-row">
        {error ? (
          <button
            type="button"
            disabled={loading}
            onClick={() => requestPage(attemptedAfter.current)}
          >
            Retry categories
          </button>
        ) : (
          nextCursor && (
            <button
              type="button"
              disabled={loading}
              onClick={() => requestPage(nextCursor)}
            >
              Load more categories
            </button>
          )
        )}
        {items !== null && (
          <button
            type="button"
            disabled={loading}
            onClick={() => requestPage(null)}
          >
            Refresh categories
          </button>
        )}
      </div>
      <p>
        A file can appear in more than one category. Refresh this list to
        include recent changes.
      </p>
    </>
  );
}
