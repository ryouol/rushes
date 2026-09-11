# Decisions and accuracy boundary

## 2026-09-10 — initial architecture
- The user-requested Next.js + TypeScript + Tailwind / Python FastAPI + SQLAlchemy + Alembic / PostgreSQL + pgvector / Temporal stack is authoritative. Sites UI guidance applies; its hosted Vinext/D1 scaffold does not fit the explicit local stack, so it is not used. No hosted deployment or payment activation.
- Bind public-facing processes to loopback. Next proxies `/api` to the local backend; browser sessions use HTTP-only same-site cookies. Use FastAPI Users' database-token strategy for revocable established authentication; no homegrown password implementation.
- Host workers share the configured local artifact roots. A remote worker cannot use these references. PostgreSQL runs in an isolated Compose volume/port, leaving the existing host PostgreSQL untouched. Persistent Temporal CLI state belongs under `.local/`.
- Use faster-whisper CPU int8 with a small configurable model on this 16 GiB Apple silicon machine. This conservative portable baseline does not claim GPU acceleration. Use local ONNX embeddings through FastEmbed; discover dimensions from the selected model and store model identity with each vector.
- Core interval convention is half-open `[start_us, end_us)` on source presentation elapsed time. Store integer microseconds for UI/event intervals, rational time bases/rates, original frame PTS in a compressed sidecar, and an explicit source/proxy mapping. Do not derive VFR frame numbers from mean FPS.
- Preserve model proposed intervals separately from refined intervals. Shot detection and semantic timing are approximate; deterministic render selection uses decoded source presentation timestamps. Browser seek is a preview, not an accuracy guarantee.
- Begin with bounded physical derived chunks to make provider timestamps unambiguous. A live benchmark comparing full-proxy offsets is required before claiming a performance advantage. Upload no originals by default. Gemini requests can incur ambiguous outcomes after network/process failure; never promise exactly-once provider billing.
- Checkpoints require valid durable artifacts; failed render units restart, rather than append into a partial container. Transactional unique operation keys protect committed outputs and customer settlements, not external-provider side effects.
- Originals are indexed or copied into private ingest storage, never renamed or changed. Outputs live in a separate root. Local directory indexing requires explicit configured roots. Filenames/content/model responses never become executable commands or filesystem authority.
- Design: charcoal surfaces, amber primary actions, wide previews and monospace timing. Group player/worklog/select controls spatially to reduce attention switching; expose one main action in each empty state. No decorative imagery or animation package.

## Official references checked
- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [FastAPI releases](https://fastapi.tiangolo.com/release-notes/).
- [FastAPI Users database sessions](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/database/).
- [Temporal CLI persistence](https://docs.temporal.io/cli/command-reference/server), [Python SDK](https://github.com/temporalio/sdk-python).
- [Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding).
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [FastEmbed](https://github.com/qdrant/fastembed), [pgvector](https://github.com/pgvector/pgvector).

Package registries resolve actual available compatible releases; committed lockfiles record them. No copied pricing or throughput assumptions.


## 2026-09-10 — simplify and final-review corrections

- Immutable per-window transcript/version snapshots and pinned prompt/schema/preprocessing protect resumed analysis. Snapshots use local transcription only; earlier Gemini speech is not fed back as transcript.
- Provider envelopes and measured usage commit in a received state before parsing. Received checkpoints survive local failure and are reapplied without resending. Unknown in-flight outcomes stay explicit; late responses retain their actual measured usage.
- Analysis content is counted through the provider before generation and capped at 10,000 tokens including video/text. Serialized transcript has an 8,000-byte cap. The default physical window is 20 seconds; input rejection records no analyzed footage or generation attempts. This additional manual context review satisfies the review skill's size gate; live provider behavior remains unverified.
- Recovery re-reserves only the unused original credit exposure in an audited reservation cycle. Cumulative confirmed coverage is charged once. Job-first row locking serializes cancellation, request start, response application and settlement.
- Grouped exports pin a source descriptor and verify it before/after all selections. Export attempts resolve relinked matching assets while preserving reviewed intervals. Source-root authorization is checked at use time; original imported folder paths remain in portable exports.
- Coarse FFmpeg seeking retains keyframe preroll with explicit PTS trimming. A nonzero-source-PTS regression caught and corrected an empty-output failure; delayed-audio timing remains separately tested.
- Search uses bounded model work outside database connections, vector-query savepoints, and bounded HNSW iterative scanning. Player worklog filtering/pagination is server-side and anchored to the selected evidence; context always includes its citation target.
- Missing-workflow cancellation is finalized locally; dispatch errors are isolated by workspace. This was found during the final production workflow/browser run and is covered by an explicit regression.
- Cleanup recognizes generated temporary names instead of matching arbitrary source-name substrings. Completed exports containing `.partial` remain intact.
- The entire application exceeds small-change review guidance. No existing PR was available to split or label. REVIEW.md preserves every issue and a concrete dependency-ordered landing plan.

The provider count interface was checked against the installed SDK and [official combined-input token counting](https://ai.google.dev/gemini-api/docs/generate-content/tokens). No token-cost, semantic-accuracy or representative-throughput claim follows from that documentation check.

## 2026-09-11 — provider-offset comparison remains inconclusive

The bounded comparison used only a generated 12-second, muted red/blue fixture and its six-second physical excerpt. The full-proxy method uploaded 9,465 bytes and counted 204 input tokens. The first attempt failed SDK schema conversion; the second returned HTTP 400; the third returned HTTP 504 after about 32 seconds. None returned usable intervals or measured generation usage, and each uploaded file was deleted with absence verified. The three conservative $0.06 local reservations remain held; they are not measured provider charges and are separate from the production allowance.

Retain physical chunks as the provisional implementation. No timestamp convention or performance advantage for provider offsets is established. The diagnostic now uses the application's 120-second generation timeout while keeping file/count requests at 30 seconds; offline real-SDK tests confirm that configuration and single-dispatch behavior. The ambiguous 504 was not retried. See [the complete comparison review](PROVIDER-COMPARISON-REVIEW.md) for all findings, evidence and the bounded future procedure.
