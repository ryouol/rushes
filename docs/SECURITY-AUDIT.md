# RUSHES security audit

The original Phase 1 review ran on 2026-09-11 at 01:07 UTC against commit `ad8a9ce` and its worktree. It found one request-size issue, repaired and tested locally. No exposed credential, missing endpoint authorization, anonymous table grant, authentication bypass, or public object bucket was found within that inspected scope. The organizer and deletion addenda below record subsequent local category, export and management changes, with historical results distinguished from current verification. This is a bounded review, not a penetration-test certification. These local changes have not been deployed.

The application uses Next.js 16.3.4, React 19.3, Tailwind CSS 4 and custom CSS. Its backend is FastAPI/Python with PostgreSQL and pgvector. Render hosts the web/API, durable media disk and database; Modal provides private speech/embedding functions. The review followed the Python/FastAPI, general browser, React and Next.js references in the `security-best-practices` skill.

## Numbered findings

1. **Medium — Ordinary request bodies were unbounded before parsing.** In the audited base, `backend/rushes/security.py:15` passed the receive stream unchanged and `web/app/api/[...path]/route.ts:48` forwarded it unchanged. Only the media upload handler enforced a streaming byte limit. A safe, in-process invalid signup probe consumed all 1,048,652 bytes across 65 chunks, then returned HTTP 422 with a 1,048,926-byte validation response. Invalid email and name prevented account creation. An unauthenticated caller could therefore force allocation/parsing and error serialization proportional to arbitrary JSON/form input; the ten-attempt auth throttle did not bound bytes per attempt. **Repair:** `backend/rushes/security.py:17` now bounds ordinary bodies at 64 KiB and folder-index bodies at 8 MiB, while the exact POST media-upload route retains its independent streaming limit. It checks declared Content-Length and actual received bytes, returning a short HTTP 413 without reflecting the body. `backend/rushes/api.py:27` installs the boundary inside the existing Host/Origin guards. **Status:** fixed and regression-tested locally; release review and deployment pending. The repro used the app in process; no oversized request was sent to production. No external ingress body cap was independently established.

## Exposed keys

The latest local invocation of `scripts/audit_local.py` on 2026-09-11 scanned **356 source/client-bundle files with zero findings**. The refreshed [security inventory](validation/security-inventory.json) records this current local snapshot. It checked these variable names: `RUSHES_DATABASE_URL`, `RUSHES_ADMIN_DATABASE_URL`, `POSTGRES_PASSWORD`, `RUSHES_APP_PASSWORD`, `RUSHES_SECRET`, and `RUSHES_GEMINI_API_KEY`.

The original Phase 1 scan covered 167 source/client-bundle files with zero findings; the subsequent organizer build scan covered 339 files with zero findings. The separate Phase 1 Git-history scan inspected all 247 then-existing blobs for Google, AWS, GitHub, Render and private-key credential shapes and found zero matches. Those counts remain historical evidence; the latest scan did not repeat the history audit. Only `.env.example` is tracked; private configuration remains ignored.

No key was found requiring relocation or rotation. Runtime secrets belong in server environment variables; local development uses ignored `.env`. Deployment records describe private Render environment configuration, and Modal credentials are consumed by server code. There are no `NEXT_PUBLIC_` credentials or client-side environment reads. The scan reports names/locations only and does not print secret values. It does not prove absence of arbitrary secret formats, verify every provider credential against every history blob, or establish the current hosted JavaScript bytes; the latest client scan used the freshly built local production output.

## Complete API inventory

The current router inventory contains **53 operations**, verified on 2026-09-11 by enumerating the locally generated FastAPI OpenAPI paths. This includes the organization member-read endpoint and four new DELETE operations for workspaces, projects, assets and exports. The table below and the refreshed [security inventory](validation/security-inventory.json) both include all 53 operations. The original Phase 1 count of 48 and subsequent organizer count of 49 are historical. Next's catch-all proxy forwards only to loopback FastAPI, checks the configured Host, allowlists forwarded headers, and disables shared caching. There are no separate Next server actions or additional serverless handlers.

All operations pass Host and exact-Origin middleware. Unsafe methods require an Origin; foreign origins are rejected. Login/signup also have a bounded per-client attempt counter. HTTPS session cookies are Secure, HttpOnly and SameSite=Strict. CORS is not enabled. Normal data routes use active sessions; workspace routes check membership before setting transaction-local tenant context. Mutations require owner/editor unless specifically owner-only. Ownership checks or forced RLS also constrain resource IDs. These controls remain necessary even for a public landing page.

In the table, **W** means `/api/workspaces/{workspace_id}`. All ID parameters are typed UUIDs unless stated otherwise. **Member** means active session plus workspace membership; **Editor** includes workspace owner. Request-size repair in finding 1 applies across the applicable body endpoints.

| Method and endpoint | Protection and input validation |
|---|---|
| POST `/api/auth/login` | Deliberately public; library OAuth2 form parsing, password verification, Origin and client throttle. |
| POST `/api/auth/register` | Deliberately public; email/schema validation, 1–120 character name, 12–256 character password, safe library creation strips privilege fields; Origin and client throttle. |
| POST `/api/auth/logout` | Session token required and revoked in the database. |
| GET `/api/health` | Deliberately public; returns only static application/status labels. |
| GET `/api/auth/me` | Active session; explicit UserRead schema excludes password hash/token. |
| GET `/api/workspaces` | Active session; query joins only that user's memberships. |
| POST `/api/workspaces` | Active session; stripped 1–120 character name; owner comes from session. |
| DELETE W | Current owner membership and matching workspace owner; tenant context and exclusive workspace locks; active work, pending AI cleanup and unsettled analysis credits block deletion. Removes app-owned workspace data; account remains active. |
| GET W`/projects` | Member; bounded offset/limit, tenant query. |
| POST W`/projects` | Editor; bounded name/description and forbidden extra fields. |
| DELETE W`/projects/{project_id}` | Current Editor and owned project, rechecked under exclusive workspace locks; active work/cleanup/settlement guards; tenant-scoped record deletion and computed app-owned storage paths. |
| GET W`/source-roots` | Editor; returns only operator-configured roots. |
| GET W`/source-roots/{root_id}/files` | Editor; integer root allowlist index, bounded scan/limit; skips symlinks. |
| POST W`/projects/{project_id}/index` | Editor and owned project; nonnegative root, 1–200 paths; extension and safe directory-FD path checks. |
| POST W`/projects/{project_id}/upload` | Editor and owned project, checked again at completion; bounded filename/path, extension allowlist, streamed byte/timeout/disk limits. |
| GET W`/projects/{project_id}/assets` | Member and owned project; bounded pagination; optional category slug is 1–36 lowercase alphanumeric/hyphen characters. Category membership is scoped to the workspace/project and filters distinct assets before pagination. Manual uncollected filtering remains separate. |
| GET W`/projects/{project_id}/organization` | Member and owned project; latest organization-capable run and completed-window evidence only; distinct full-asset counts; category results bounded at 100 with total/has-more fields. Configuration is a boolean without secret values. |
| GET W`/assets/{asset_id}` | Member and owned asset; private absolute storage paths excluded; per-asset organization categories bounded at 100 with total/has-more fields. |
| DELETE W`/assets/{asset_id}` | Current Editor and owned asset, rechecked under exclusive workspace locks; processing, unfinished dependent exports and pending cleanup/settlement block deletion. Linked external originals and completed exports remain. |
| GET W`/assets/{asset_id}/media/{kind}` | Member and owned asset; only proxy/thumbnail kinds; resolved path stays inside private storage. |
| GET W`/assets/{asset_id}/observations` | Member and owned asset; bounded pagination/time query and kind enum. |
| PATCH W`/observations/{observation_id}` | Editor and owned observation; bounded description, in/out range and optimistic version checks. |
| GET W`/observations/{observation_id}/history` | Member and owned observation. |
| GET W`/jobs` | Member; optional owned project filter; bounded results. |
| GET W`/events` | Session and membership checked at start and each event poll; optional owned project; tenant queries. |
| POST W`/jobs/{job_id}/cancel` | Editor and owned job; allowed-state checks. |
| POST W`/assets/{asset_id}/retry` | Editor and owned asset; allowed-state/checkpoint checks. |
| POST W`/assets/{asset_id}/observations` | Editor and owned asset; bounded note, interval and idempotency key. |
| GET W`/projects/{project_id}/search` | Member and owned project; 1–500 character query, 1–40 results, tenant search. |
| GET W`/observations/{observation_id}/context` | Member and owned observation. |
| GET W`/projects/{project_id}/collections` | Member and owned project; bounded results. |
| POST W`/projects/{project_id}/collections` | Editor and owned project; bounded name/instructions/query and collection count. |
| GET W`/collections/{collection_id}/items` | Member and owned collection; bounded results. |
| POST W`/collections/{collection_id}/items` | Editor; tenant collection and owned asset, same-project check; bounded interval/note/count. |
| DELETE W`/collection-items/{item_id}` | Editor and owned item. |
| DELETE W`/collections/{collection_id}` | Editor and owned collection. |
| POST W`/collections/{collection_id}/suggest` | Editor and owned collection; 1–500 character instructions. |
| PATCH W`/collection-items/{item_id}` | Editor; tenant item and owned asset; merged interval validation, bounded note. |
| POST W`/projects/{project_id}/export-preview` | Editor and owned project; kind enum/UUID or validated category slug, mutually exclusive selection; category exports permit full original copies only. Same-project source and range checks, up to 500 files and bounded frozen category evidence. |
| POST W`/exports/{export_id}/start` | Editor and owned export; draft-state check. |
| GET W`/projects/{project_id}/exports` | Member and owned project; bounded pagination; render plan and full provenance excluded. SQL constructs compact output filename/byte metadata in original output order for download-by-index links. |
| GET W`/exports/{export_id}/download/{index}` | Member and owned completed export; integer index bounds and resolved export-folder containment. |
| POST W`/exports/{export_id}/retry` | Editor and owned export; only failed/canceled jobs. |
| DELETE W`/exports/{export_id}` | Current Editor and owned export, rechecked under exclusive workspace locks; active jobs/exports block deletion; removes only the computed app-owned export directory and related records. |
| GET W`/settings` | Member; operator configuration/status without secret values, shared server free space and reserve, separate export-volume capacity, and workspace-scoped counts/recorded uploaded-source sizes. |
| GET W`/usage` | Member; workspace-scoped aggregates and ledger. |
| GET W`/members` | Owner only; bounded members, explicit safe user fields. |
| POST W`/members` | Owner only; email and editor/viewer role validation; member count and owner-role protections. |
| DELETE W`/members/{member_id}` | Owner only; owned membership; cannot remove owner. |
| GET W`/assets/{asset_id}/source-status` | Member and owned asset; allowlisted, symlink-safe source open. |
| POST W`/assets/{asset_id}/relink` | Editor and owned asset; root/path validation and exact source-content hash. |
| GET W`/assets/{asset_id}/analysis-estimate` | Editor and owned asset; no arbitrary provider/model selection. |
| POST W`/assets/{asset_id}/reanalyze` | Editor and tenant asset; amount/model/fingerprint compared with fresh server estimate, active-job check. |

## Organizer and category-export addendum — 2026-09-11

AI organization adds labels to the existing bounded Gemini analysis request. Each observation accepts up to three category names of at most 36 characters and six words, with English letters, numbers, spaces, apostrophes, hyphens or ampersands. Normalization produces deterministic lowercase slugs. Markup, path separators, traversal strings and the reserved Uncategorized name are rejected. The prompt asks for supported content categories and treats footage/transcript text as evidence, not instructions; syntactic validation does not prove a label's semantic accuracy.

Assignments are persisted in versioned `Observation.attributes`, using the existing observation/run/window tables and tenant policies. The query layer checks workspace, project, asset and run/window relationships, uses the latest organization-capable run, and includes only completed windows with the expected attribute version. Category counts use distinct full assets, so repeated observations do not inflate file totals. Category slugs are database filters, not source filesystem paths. `category=uncategorized` means no current AI membership; `uncollected=true` and the original `uncategorized=true` flag mean no manual collection membership.

An active asset retry takes precedence over its preserved failed/canceled run status, so resumed processing is visible while completed categories remain available. Legacy analysis receives no invented categories or automatic paid reanalysis. Missing AI configuration, partial analysis, completed analysis with no labels and not-yet-analyzed footage remain distinguishable. Member-read endpoints do not dispatch inference or modify source media.

Category export resolves at most 501 matching IDs and rejects more than 500 before creating a draft. A valid preview freezes full-file selection, source identity, category metadata and up to 20 supporting observations per file, with the complete evidence count and an explicit truncation flag. Later category changes do not silently change the approved export. The category slug forms one validated output subfolder; numbered filenames avoid collisions, and output/receipt paths reject traversal and symlinks. Rendering rechecks project membership of the planned assets and source fingerprints. Originals are copied byte for byte into a separate output folder, then exposed through authenticated download routes.

The export-list endpoint uses a compact SQL projection: it omits the full render plan and provenance, and returns only each output's filename and bytes in stable order. Detailed frozen evidence stays in server-side export records and generated provenance. This bounds routine list payloads while preserving download-by-index identity.

The deliberately public landing samples are generated illustrative assets under `web/public/demo`, with three declared local metadata entries. The current landing is a static illustration: its example categories do not search, play media, call an AI provider or read private workspaces. This public example is separate from authenticated user footage, which remains behind media/download authorization.

Historical organizer verification: `RUSHES_GEMINI_API_KEY= .venv/bin/python -m pytest -q --tb=short` completed with **156 passed, 1 skipped in 38.02 seconds** and one `hf_xet` deprecation warning. The skip is the opt-in Temporal integration check. Local PostgreSQL permission escalation was approved; paid AI was disabled for this suite. Coverage includes category validation/persistence, distinct counts, pagination, category-list bounds, tenant/project isolation, legacy/latest-run behavior, failed/canceled retry states, frozen category copies, export limits, path/receipt/download handling and compact export projection.

Subsequent focused organizer/inference/export checks passed 53 tests, and later category normalization checks passed 27 tests; these were not repeated full-suite runs. The organizer-stage local production Next build passed: compilation took 791 ms, TypeScript took 2.2 seconds, and 14 pages were generated. The historical 339-file secret scan followed that build. These results predate the deletion and storage-management changes below and cover local source/build output, not hosted assets, ingress, database configuration or deployment readiness.

A separate, bounded live smoke check is recorded in [live-ai-category-smoke.json](design/2026-09-premium/qa/live-ai-category-smoke.json). One generation analyzed the 16-second generated waves sample with prompt `footage-evidence-v7` and schema `observations-v2`, returning Coastline and Waves. It recorded 1,394 input tokens, 186 output tokens and no pending provider-file cleanup. Its $0.06 conservative reservation was a cap, not a measured invoice. This check did not change application key configuration or persist results into a user library. It verifies one real response path, not general classification quality or a production import-to-library deployment. No organizer deployment occurred.

After QA, the local production-mode launcher, API and worker were restarted with the normal key inherited from the unchanged ignored `.env`; the temporary blank-key test override was removed. The environment-only `RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD=2000000` override preserves the authorized $2 testing allowance. Health returned HTTP 200, no local jobs were pending or running at restoration, and no new inference was requested. The monthly ledger held a conservative reservation of 60,000 micro-USD ($0.06), not a measured provider invoice. Paid AI was disabled for the test runs; it is restored in the local handoff configuration. This is a local process change, not a hosted deployment.

## Deletion and storage-management addendum — 2026-09-11

Four authenticated DELETE routes add workspace, project, asset and export management. Each operation rechecks current membership inside its deletion transaction. Workspace deletion requires both the owner role and matching `Workspace.owner_id`; the other operations require an owner/editor and a record in that workspace. Explicit tenant predicates and the existing foreign keys/RLS constrain the record cascade. Workspace deletion removes its memberships and tenant accounting but preserves the user account and deployment-wide provider-spending ledger. Asset deletion preserves completed exports, clears duplicate references, and retains usage/accounting without the deleted asset reference.

Deletion holds exclusive workspace filesystem and database locks. Uploads hold a shared filesystem lease through streaming and publication; file/provider activities hold one through their actual work. Canceling an async activity drains its underlying thread before releasing the lease. This closes the reviewed race where a canceled job could already look terminal while its thread still wrote output. Late activity retries check for a deleted job before recreating storage. Active jobs, active or dependent unfinished exports, outstanding provider files/in-flight requests, and reserved analysis credits block the relevant deletion. The Temporal workflow cancellation commands were not changed; the lease covers activity work that outlives workflow cancellation.

Filesystem targets are computed from configured app roots and workspace/asset/export UUIDs, never from stored source or export path fields. Anchored directory descriptors, no-follow opens and symlink-resistant `rmtree` constrain traversal. External indexed originals are not deletion targets. All target trees and database constraints are checked before bytes are removed. Cleanup is not an atomic filesystem transaction: if removal fails after some files are gone, database records roll back and the HTTP 409 explicitly reports that some files may already be removed; deletion can be retried. Successful responses follow database commit. Deletion queries project only required export/job identifiers and states, avoiding hydration of full frozen plans and provenance across workspace history.

Settings now distinguishes shared disk free space, the unchanged configured reserve, and usable capacity, with separate export-volume figures when applicable. Workspace uploaded-source totals are recorded original sizes, not measured physical storage use. Import preflight requests fresh capacity with a four-second timeout and estimates twice the selected video bytes for upload and working copies; unavailable settings fall through to existing server checks. The server retains its upload-byte, duration and per-step disk-space checks. These changes do not lower the reserve or schedule automatic deletion; removal requires an explicit authenticated request.

The deletion regression suite covers owner/editor/viewer/outsider access, tenant isolation, active jobs/uploads/database transactions, cancellation while a real preparation thread remains blocked, late retries, provider cleanup/credit settlement, computed paths, symlinks, permission failures, completed-export preservation and retry after partial disk removal. Final local full-suite verification completed with **194 passed, 1 skipped and 1 dependency warning in 33.53 seconds**, after the deletion projection fix and correction of the prior run's fixture assertion. The skip remains the opt-in Temporal integration check. This passing suite includes the regression proving that deletion stays blocked until a canceled preparation thread actually stops.

The final local Next production build passed: compilation took **1,101 ms**, TypeScript took **2.2 seconds**, and **14 pages** were generated. All **six analytics tests** passed, and the final TypeScript check included the authored deletion browser regressions. Those browser test files were typechecked; this does not claim a CLI Playwright execution. The latest bounded source/build scan reports **356 files and zero findings**, and the API inventory contains **53 operations**. No hosted deployment or fresh hosted security verification is claimed.

## Complete table inventory and RLS exceptions

The **original Phase 1 read-only local PostgreSQL catalog query** confirmed `rushes_app` is not a table owner and has no superuser, RLS-bypass, create-database or create-role capability. Every public-schema table had **zero PUBLIC table grants**. No table or migration was added for organization. There is no browser-facing database credential or anonymous database API in this application. Database PUBLIC grants and unauthenticated HTTP access are distinct concepts.

| Tables | RLS and access |
|---|---|
| `analysis_run`, `analysis_window`, `asset`, `collection`, `collection_item`, `embedding`, `export`, `job`, `ledger_entry`, `media_timeline`, `observation`, `observation_revision`, `processing_event`, `project`, `reservation`, `shot`, `usage` | All 17 have ENABLE + FORCE RLS, with workspace equality in USING and WITH CHECK. Runtime CRUD is subject to these policies. No PUBLIC grants. |
| `user`, `accesstoken` | No tenant RLS: authentication must run before workspace selection. Private runtime role has CRUD; established auth handlers and explicit response schemas mediate browser access. No PUBLIC grants. |
| `workspace`, `membership` | No tenant RLS: workspace creation/listing and membership authorization establish the tenant context. Private runtime CRUD; session-scoped listing, membership checks and owner-only membership changes mediate browser access. No PUBLIC grants. |
| `provider_spend_reservation` | No tenant RLS: deployment-wide spending ledger contains provider/month/amount, not tenant content. Runtime SELECT/INSERT only, no UPDATE/DELETE. No PUBLIC grants. |
| `alembic_version` | No RLS: migration metadata; runtime has no SELECT/INSERT/UPDATE/DELETE privileges. No PUBLIC grants. |

These six non-tenant-RLS tables are explicit architectural exceptions, rather than claims that RLS covers every table. `docs/BRIEF.md:265` already calls for separate authentication/system-table access. The Phase 1 review found no anonymous-readable/writable table; it did not introduce a blanket policy that would break login/bootstrap. The local catalog was collected during that audit. The recorded production schema version 0005, excluded migration credentials, private database network and disabled external access in `docs/deployment-inventory.json` and `docs/PRODUCTION.md` are historical deployment evidence, not a new live database audit. Temporal's separate server-owned workflow/visibility databases likewise use network/role isolation, not the application's tenant-RLS policy; no fresh catalog of those databases was queried.

## Broken gates and storage

The original Phase 1 source searches found no hardcoded `if true`, disabled/commented authentication guard, signature-verification bypass or public-auth feature flag. Library registration uses `safe=True`; accepting library privilege fields in its schema does not grant those privileges. The original protected route dependencies and per-mutation role checks were traced; the organizer additions are described separately above. Production ingress header anti-spoofing is recorded in `docs/validation/render-ingress.json` at 00:08 UTC; it was not rerun during this documentation update.

There are no S3/Supabase/Firebase object buckets configured in this repository. User media lives outside Next `public/`, in private disk directories. The explicitly public generated landing samples are the separate exception described above. Private media access uses authenticated API media/download routes and tenant ownership, not guessable static URLs. Source opens reject absolute/traversal paths, symlinks and non-regular files; exports enforce folder containment. Hosted source roots are recorded as empty. Modal source defines private functions only, temporary derived audio and no application volumes/public web endpoints; the deployment inventory's no-volume/no-public-endpoint result is historical, not a fresh Modal control-plane query. Public-bucket policy changes are therefore N/A for this architecture; the private-disk access checks are applicable and present.

## Request-size contract and verification

Every current body model was checked before choosing the caps. The ordinary 64 KiB allowance fits the largest legitimate text input even when JSON encodes each astral Unicode character as twelve ASCII bytes. It also leaves framing space. A cap is an explicit aggregate input contract; numeric fields, ignored OAuth form fields and whitespace are not permitted to create unbounded bodies merely because a schema does not assign each one a byte limit.

| Request models | Existing input size and selected allowance |
|---|---|
| `UserCreate`, OAuth2 login form | Name 120 characters, valid email, 12–256 character registration password; 64 KiB. Unused OAuth form fields receive the same aggregate cap. |
| `NamedInput`, `ProjectInput` | Name 120 and description 2,000 characters; 64 KiB. |
| `Correction`, `NoteInput` | Description 4,000 characters plus interval/version/UUID fields; under 49 KiB with worst-case astral JSON escaping; 64 KiB. |
| `CollectionInput`, `SuggestInput` | Name 160, instructions 2,000, saved query 500; suggestion instructions 500; 64 KiB. |
| `ItemAdjustment`, `ItemInput` | Note 1,000 characters, UUID and interval fields; 64 KiB. |
| `ExportInput` | Kind enum, optional UUIDs or category slug up to 36 characters, and interval; 64 KiB. The up-to-500-item export plan and bounded evidence are generated on the server, not submitted in the body. |
| `MemberInput`, `RelinkInput` | Valid email/role, or root index and relative path up to 2,000 characters; 64 KiB. |
| `AnalysisConfirmation` | Amount, model and fingerprint must match server values; 64 KiB. |
| `IndexInput` | Up to 200 path strings; no existing individual string maximum. An explicit 8 MiB aggregate cap allows 200 long filesystem paths including unusually expensive JSON escaping. |
| Streaming upload | Filename/path remain bounded query fields. Existing configured media-byte, timeout, free-space and authorization checks remain responsible for its streamed body. |

The original request-size repair changed `backend/rushes/security.py`, `backend/rushes/api.py`, `tests/test_security.py`, and this report; that repair had no frontend changes. Its tests verify declared oversize rejection before any receive, early stopping for chunked and falsely underreported JSON/form bodies, short non-echoing errors, an exact-64-KiB valid maximal Unicode correction, a valid 200-path batch above 4 MiB, the batch's own streamed upper bound, and actual upload size/role/cleanup behavior.

Historical focused repair verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest tests/test_security.py tests/test_routes.py tests/test_hosting.py -p no:cacheprovider -q` — **26 passed in 1.92 seconds**, including eight new regression cases. Existing route/hosting coverage includes active-session/tenant/media authorization, source revocation, Host/Origin controls and trusted-client rate limiting. `ruff check --no-cache` passed for the changed Python files. Those integration cases used synthetic local PostgreSQL and media fixtures; no production or provider call was made. Later verification is recorded in the organizer and deletion addenda above.

## Historical Phase 1 disposition and limits

Final local verification at 2026-09-11 01:22 UTC: `RUSHES_GEMINI_API_KEY= .venv/bin/python -m pytest -q --tb=short` — **110 passed, 1 skipped in 28.64 seconds**. The skipped case is the opt-in Temporal integration check. One dependency deprecation warning remains. The first full-suite attempt could not connect to localhost PostgreSQL because the execution sandbox denied sockets; a direct probe confirmed `PermissionError: Operation not permitted`. The same suite passed after allowing the local test-database connection. This was an environment failure, not a repaired application regression. Paid Gemini calls were disabled.

The Phase 1 simplify review covered reuse, code quality and efficiency, with no actionable findings. Its four final code-review perspectives completed with no actionable findings: breaking changes, testing, model-visible context and change size. The size reviewer counted 323 authored lines for the coherent security implementation, regression tests and audit report before subsequent addenda. Design artifacts had no runtime dependency on that repair and could be committed separately. At that historical checkpoint, no merge, commit, PR or deployment of the repair had occurred; this paragraph does not describe later Git activity. Hosted release verification remains pending.

| Checklist item | Disposition |
|---|---|
| Exposed keys | ✅ The original bounded source/build/history scans found no exposures; no relocation required. The current local source/build scan is recorded above; the history scan remains historical. |
| Endpoint authentication/input validation | ✅ The original 48-operation audit covered the body-size repair. The current 53-operation inventory includes organization and four new DELETE operations, with their safeguards and passing local verification recorded above. Public auth/health endpoints are justified exceptions to session requirements. ⚠️ Hosted release verification/deployment pending. |
| RLS/security rules | ✅ Seventeen forced tenant policies; all 23 application-schema tables inventoried with six explicit auth/system exceptions and no PUBLIC grants. Fresh local catalog only. |
| Broken authentication gates | ✅ No bypass found in current inspected source. |
| Public storage | ✅ Private disk/API access inspected; ➖ object-bucket policy changes are N/A because no object buckets are used. |

No credential, production resource, Git state or user data was changed for the original Phase 1 audit. Its request probe was an invalid in-process signup that could not create an account. Subsequent synthetic tests and the separate bounded live AI smoke are recorded in the organizer addendum. Live production SQL/Modal configuration and a rebuilt hosted-client secret scan must be reverified when releasing changed code; the current local inventory and historical hosted validation records are not substitutes for that release evidence.
