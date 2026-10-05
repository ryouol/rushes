import type { Asset } from "@/lib/api";

export function ProcessingNotice({
  asset,
  canEdit,
  compact = false,
}: {
  asset: Asset;
  canEdit: boolean;
  compact?: boolean;
}) {
  if (
    !asset.error &&
    !asset.can_retry &&
    !["partial", "failed", "canceled"].includes(asset.status)
  )
    return null;

  const availability = asset.has_preview
    ? "Your preview is available. You can review any completed worklog entries."
    : "No preview is available yet. Any completed worklog entries are retained.";

  return (
    <section
      className={`processing-notice${compact ? " processing-notice-compact" : ""}`}
      aria-label="Processing status"
    >
      {!compact && (
        <p>
          <strong>
            {asset.status === "partial"
              ? "Processing is incomplete"
              : asset.status === "canceled"
                ? "Processing was canceled"
                : asset.status === "failed"
                  ? "Processing stopped before it finished"
                  : "Some processing steps need attention"}
          </strong>
        </p>
      )}
      <p>{availability}</p>
      <p>
        {compact ? (
          canEdit && asset.can_retry ? (
            "Resume from saved progress; unfinished steps may use credits."
          ) : (
            "Open footage for details and recovery options."
          )
        ) : !canEdit ? (
          "Ask a workspace owner or editor to review the processing details and recovery options."
        ) : asset.can_retry ? (
          <>
            Use <strong>Resume processing</strong> in Footage details &amp;
            analysis to continue from saved progress. Unfinished steps may use
            credits; requests with uncertain outcomes are not repeated
            automatically.
          </>
        ) : (
          <>
            For new analysis, open Footage details &amp; analysis and review the
            estimate. It starts only after confirmation and may use credits.
          </>
        )}
      </p>
      {!compact && (
        <details className="processing-diagnostics">
          <summary>Processing details</summary>
          <p>{asset.error || "No further details were recorded."}</p>
          <p>Footage ID: {asset.id}</p>
        </details>
      )}
    </section>
  );
}
