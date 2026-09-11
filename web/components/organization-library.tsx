"use client";

import { useState } from "react";
import {
  ChevronDown,
  FileVideo,
  Film,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  elapsed,
  type Asset,
  type OrganizationCategory,
  type ProjectOrganization,
} from "@/lib/api";

export function OrganizationStatus({
  organization,
  error,
  onRetry,
}: {
  organization: ProjectOrganization | null;
  error: string;
  onRetry: () => void;
}) {
  if (error)
    return (
      <div
        className="organization-status organization-unavailable"
        role="status"
      >
        <p>AI organization could not load. Your footage is still available.</p>
        <button className="text-button" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  if (!organization) return null;
  const {
    analysis_configured,
    total_assets,
    categorized_assets,
    processing_assets,
    partial_assets,
    not_analyzed_assets,
  } = organization;
  return (
    <div className="organization-status">
      <div className="organization-status-line" role="status">
        <Sparkles size={17} />
        <p>
          {!analysis_configured
            ? "AI organization isn’t configured"
            : processing_assets > 0
              ? `${processing_assets} ${processing_assets === 1 ? "file is" : "files are"} processing`
              : total_assets === 0
                ? "AI groups your footage as it’s analyzed"
                : `${categorized_assets} of ${total_assets} files have AI categories`}
        </p>
      </div>
      {!analysis_configured ? (
        <p className="organization-guidance">
          You can import and inspect footage. Ask the workspace operator to
          enable visual analysis.
        </p>
      ) : not_analyzed_assets > 0 || partial_assets > 0 ? (
        <details className="organization-analysis-details">
          <summary>
            {not_analyzed_assets > 0
              ? `${not_analyzed_assets} ${not_analyzed_assets === 1 ? "file needs" : "files need"} organization analysis`
              : `${partial_assets} ${partial_assets === 1 ? "file has" : "files have"} partial analysis`}
          </summary>
          <p>
            {partial_assets > 0 &&
              "Partial analysis shows only the categories found so far. "}
            Open a file, then use Review analysis estimate in Footage details
            &amp; analysis. New analysis starts only after confirmation.
          </p>
        </details>
      ) : total_assets > 0 && categorized_assets === 0 ? (
        <p className="organization-guidance">
          No categories were identified. Browse all footage or search the
          available evidence.
        </p>
      ) : null}
    </div>
  );
}

export function OrganizationCategories({
  organization,
  value,
  onChange,
}: {
  organization: ProjectOrganization | null;
  value: string;
  onChange: (value: string) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  if (!organization || !organization.total_assets) return null;
  const visible = organization.categories.slice(0, 3);
  const remaining = organization.categories.slice(3);
  const categoryButton = (category: OrganizationCategory) => (
    <button
      key={category.id}
      type="button"
      aria-pressed={value === category.id}
      onClick={() => onChange(category.id)}
    >
      {category.name} <span>{category.asset_count}</span>
    </button>
  );
  return (
    <div className="organization-categories">
      <div
        className="organization-category-strip"
        role="group"
        aria-label="AI categories"
      >
        {categoryButton({
          id: "",
          name: "All footage",
          asset_count: organization.total_assets,
        })}
        {visible.map(categoryButton)}
        {categoryButton({
          id: "uncategorized",
          name: "Uncategorized",
          asset_count: organization.uncategorized_assets,
        })}
        {(remaining.length > 0 || organization.has_more) && (
          <button
            type="button"
            aria-expanded={moreOpen}
            aria-controls="organization-more-categories"
            onClick={() => setMoreOpen((open) => !open)}
          >
            More <ChevronDown size={15} />
          </button>
        )}
      </div>
      {moreOpen && (
        <div
          id="organization-more-categories"
          className="organization-more-categories"
        >
          <div role="group" aria-label="More AI categories">
            {remaining.map(categoryButton)}
          </div>
          <p>
            A file can appear in more than one category.
            {organization.has_more &&
              ` Showing ${organization.categories.length} of ${organization.category_total} categories.`}
          </p>
        </div>
      )}
    </div>
  );
}

export function OrganizationLibrary({
  assets,
  base,
  category,
  loading,
  stale,
  total,
  page,
  canEdit,
  pending,
  onOpen,
  onRetry,
  onDelete,
  onPageChange,
  onRefresh,
}: {
  assets: Asset[];
  base: string;
  category: string;
  loading: boolean;
  stale: boolean;
  total: number;
  page: number;
  canEdit: boolean;
  pending: string[];
  onOpen: (id: string) => void;
  onRetry: (id: string) => void;
  onDelete: (asset: Asset) => void;
  onPageChange: (page: number) => void;
  onRefresh: () => void;
}) {
  const unavailable = loading || stale;
  if (loading && !assets.length)
    return (
      <div className="organization-loading" role="status">
        <Loader2 className="spin" size={20} /> Loading footage…
      </div>
    );
  if (!assets.length && !stale)
    return (
      <div className="empty-state organization-empty">
        <Film size={38} strokeWidth={1.2} />
        <h2>
          {category
            ? "No footage in this category"
            : "Bring your footage together"}
        </h2>
        <p>
          {category
            ? "Categories update as analysis finishes. Choose All footage to see every file."
            : canEdit
              ? "Import files or a folder to bring your footage into one searchable library. Originals stay intact."
              : "An owner or editor can import footage for this project."}
        </p>
      </div>
    );
  return (
    <>
      <p className="sr-only" role="status">
        {loading ? "Loading footage…" : ""}
      </p>
      {!loading && stale && (
        <div className="organization-unavailable" role="status">
          <p>This footage view could not load.</p>
          <button className="text-button" onClick={onRefresh}>
            Try again
          </button>
        </div>
      )}
      <div
        className="asset-grid organization-asset-grid"
        aria-busy={loading}
        inert={unavailable}
      >
        {assets.map((asset) => {
          const organization = asset.organization;
          const state = organization?.state ?? "not_analyzed";
          const labels = organization?.categories ?? [];
          const categoryTotal = organization?.category_total ?? labels.length;
          const status =
            state === "processing"
              ? "Processing"
              : state === "partial"
                ? "Partial analysis"
                : state === "not_analyzed"
                  ? "Needs analysis"
                  : labels.length === 0
                    ? "No category identified"
                    : "";
          return (
            <article
              key={asset.id}
              className="asset-card"
              data-processing-state={asset.status}
              data-organization-state={state}
            >
              <button className="asset-open" onClick={() => onOpen(asset.id)}>
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
                    {asset.duration_us ? elapsed(asset.duration_us) : "—"}
                  </span>
                </div>
                <div className="asset-info">
                  <h2 title={asset.name}>{asset.name}</h2>
                  {status && (
                    <p className="organization-asset-status">
                      {state === "processing" && (
                        <Loader2 size={13} className="spin" />
                      )}
                      {status}
                    </p>
                  )}
                  {!category && labels.length > 0 && (
                    <p className="organization-asset-labels">
                      {labels
                        .slice(0, 2)
                        .map((label) => label.name)
                        .join(" · ")}
                      {categoryTotal > 2 && ` · +${categoryTotal - 2}`}
                    </p>
                  )}
                </div>
              </button>
              {asset.error && <p className="asset-notice">{asset.error}</p>}
              {canEdit && (
                <div className="asset-management">
                  {asset.can_retry && (
                    <button
                      className="text-button retry"
                      disabled={pending.includes(asset.id)}
                      onClick={() => onRetry(asset.id)}
                    >
                      {pending.includes(asset.id)
                        ? "Queuing…"
                        : "Resume processing"}
                    </button>
                  )}
                  <button
                    className="text-button delete-item"
                    aria-label={`Delete ${asset.name}`}
                    onClick={() => onDelete(asset)}
                  >
                    <Trash2 size={14} /> Delete
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
      {total > 40 && (
        <div className="pagination">
          <button
            className="secondary"
            aria-disabled={unavailable || page === 0}
            onClick={() => {
              if (!unavailable && page > 0) onPageChange(page - 1);
            }}
          >
            Previous
          </button>
          <span>
            {page * 40 + 1}–{Math.min((page + 1) * 40, total)} of {total}
          </span>
          <button
            className="secondary"
            aria-disabled={unavailable || (page + 1) * 40 >= total}
            onClick={() => {
              if (!unavailable && (page + 1) * 40 < total)
                onPageChange(page + 1);
            }}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
