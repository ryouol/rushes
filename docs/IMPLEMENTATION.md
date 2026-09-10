# RUSHES phase checklist

The production request supersedes the original hosting boundary. Current status, budget constraints and provider resources are in [PRODUCTION.md](PRODUCTION.md); the later simplify/review pass and current validation are in [PRODUCTION-REVIEW.md](PRODUCTION-REVIEW.md). Historical test totals below describe the earlier local snapshot. All seven user uploads now complete local preview/transcription processing; visual analysis and hosted deployment remain incomplete.

Status: **implemented** means working code with the evidence stated here; **needs input** marks inaccessible external verification; **deferred** is not complete; **N/A** records a specific scope reason. **Overall release remains incomplete** while essential Gemini/representative-media verification is missing.

| Phase | Delivered files and behavior | Actual validation | Outstanding |
| --- | --- | --- | --- |
| 0 — foundation | **implemented:** `config.py`, `models.py`, `db.py`, `auth.py`, `security.py`, migrations, Compose; source inspection, PTS mapping, proxy, scene candidates, real local speech, persisted worklog, seek/export | Rational/DF/long-duration/VFR/rotation/no-audio tests; original hashes; real tiny Whisper; signup/login/logout; runtime RLS; fresh empty-database migrations | **needs input:** live Gemini part of the slice; representative footage semantic accuracy |
| 1 — durable ingestion | **implemented:** Temporal batch/asset/index/export workflows, media/inference queues (2/1 activities), database outbox, explicit roots and bounded uploads, duplicates, relink, per-file failures, edits/history, versioned caches, uncertain provider outcomes, temporary cleanup | 50-file synthetic load; browser-close persistence; actual worker kill and persistent Temporal restart; selected-root batch with good/corrupt files; note/retry integration tests | **needs input:** provider full-proxy offsets versus physical chunks, actual expiry/cleanup and ambiguous remote outcomes. Physical chunks are provisional. |
| 2 — retrieval | **implemented:** tenant-filtered full text and local vector retrieval, ranking fusion, range grouping, bounded neighbor context, record-validated citations, replaceable interfaces, model-specific HNSW setup/reindex command | Browser search on persisted and corrected evidence; authorization tests; actual local embedding model execution | **needs input:** human-labeled retrieval precision/recall and content-type breakdown. Similarity threshold remains a heuristic. |
| 3 — experience | **implemented:** accounts, workspaces/projects, owner/editor/viewer roles, file/folder import, player, synchronized worklog, notes/history, search, collections, exports, settings/storage/usage, SSE reconnect/session revocation, I/O and J/K/L | Production browser journey; authenticated ranged media; viewer denial; cross-workspace access denial; mobile screenshots; keyboard tab focus; 200% zoom | **needs input:** representative footage usability feedback; additional assistive-technology testing beyond the exercised browser paths |
| 4 — organization/export | **implemented:** virtual collections, evidence-based suggestions, adjustable ranges/assignments, uncategorized filter, saved searches, previewed clip/copy plans, worklog and selection JSON/CSV, experimental FCP7 XML/FCPXML | Real decoded-frame subclip tests, downloaded 48-frame/two-second browser clip; selected-range edits; XML source-ordinal/rational-time tests and real browser generation | **needs input:** actual editor round trips; no supported editor installed. **N/A:** EDL without a justified narrower workflow. Selection JSON/CSV passed real activity integration and production browser download checks. |
| 5 — usage | **implemented:** unique source duration, analysis/transcription/render/export duration and bytes, provider tokens/model/attempts, transactional credits, reserve/settle/release audit, local grant/caps, reviewed new-analysis quote, original operation on recovery | Concurrent reservations; duplicate settlement; failed-job retry identity; load/restart reports show no duplicate source usage or provider debit | **needs input:** live provider token/cost reconciliation. **deferred by explicit scope:** Stripe/live payments. No checkout exists. |
| 6 — hardening | **implemented:** 17 FORCE-RLS tenant tables; non-owner/NOBYPASSRLS runtime; composite tenant references; origin/host controls; protected streams/SSE/search/exports; safe directory-FD source opens; private storage; no-shell commands; endpoint inventory and source/client secret scan | Fresh migrations: version 0004 / 17 forced-RLS tables. Read/mutate denial tests, traversal/symlink tests, ranged media checks, source/bundle audit | Final source/client scan: 118 files, zero findings; this is not a proof of every possible secret pattern. |
| 7 — UX/performance | **implemented:** responsive layouts, local feedback/partial/error states, 44px controls where practical, focus/keyboard tabs, reduced motion, lazy thumbnails, library/worklog pagination, production build, reproducible launcher/README | Final backend suite: 54 passed, one opt-in Temporal test skipped, one upstream Hugging Face warning (24.09s). Separate real Temporal batch: 1 passed (13.87s). Production E2E including selection JSON/CSV and actual L/K playback plus I marking: 1 passed (31.6s). Build/typecheck passed; production npm audit: zero vulnerabilities. | **needs input:** representative ten-hour/fifty-file evaluation and human-labeled query set. Requested simplify and code-review passes completed; all 48 findings/dispositions are in REVIEW.md. Initial change size remains an explicit review-process limitation. |

## Website hardening disposition

- **implemented:** custom 404/application error pages; clear primary actions; titles/descriptions; public generic Open Graph/Twitter image; favicon SVG/manifest; robots disallow all; meaningful/decorative image alternatives; privacy/terms drafts; submission feedback; clickable logo, navigation/footer and dynamic year.
- **implemented:** typed analytics adapter with no configured service and no network calls by default; consent gate required for any future adapter. No invented identifiers or business claims.
- **N/A:** public sitemap of private local projects; marketing/contact pages when no such content or real contact details were supplied; analytics cookie banner while no nonessential cookies/analytics are active.
- **needs input before hosted commercial release:** TODO: provide reviewed legal/operator/support details, retention policy and provider disclosures.
- **implemented, live verification unavailable:** optional feature-detected WebMCP project search. **needs input:** supported WebMCP browser registry for a live contract check; it is not a requested local-release blocker.

## Measured evidence

The load and destructive-interruption measurements below were captured before the final review fixes. Their stored reports remain historical evidence; current throughput was not re-benchmarked after those fixes. Final workflow and browser tests were rerun.

- [Synthetic load](validation/synthetic-load.json): fifty files, ten source hours, 160×90/24fps, muted repeated colors; 168.03 seconds; 50 partial; originals unchanged. M1 Pro, 16 GiB RAM. This is not camera-footage throughput or semantic evaluation.
- [Recovery](validation/recovery.json): active temporary media unit interrupted by killing the owned worker process group; Temporal stopped/reopened the same SQLite state; five-minute 1080p24 synthetic source recovered in 140.5 seconds; corrupt file failed independently; one source usage record; no provider settlement.
- [Fresh migrations](validation/fresh-migrations.json): disposable empty database upgraded successfully; 17 forced-RLS tables; schema version 0004.
- [Endpoint/security inventory](validation/security-inventory.json): 48 API operations inventoried after lazy included routers were expanded. Only health/register/login are deliberately public; logout and `/auth/me` require sessions; workspace routes require membership, with role checks on mutations.
- Screenshots and generated outputs remain under `.local/qa`; source fixtures and model caches are ignored by Git. Test accounts are synthetic and have no published passwords.

## Concrete UX decisions

- Import remains the library’s primary action; exports require a visible review of the actual plan.
- Source/timecode information is separate from elapsed selection controls to prevent confusing model seconds with camera timecode.
- Human notes and corrections appear beside the footage and keep their original proposal/history for review.
- Source repair and paid reanalysis sit in a collapsed source panel, keeping the common select workflow focused.
- Empty/partial states explain the available next action and missing Gemini configuration. Processing is never represented as instant.
- Bounded lists and scrollable usage tables avoid page overflow; keyboard tabs support arrows/Home/End and preserve visible focus. No decorative 3D or animation package was added.

## Completion gates

Verified locally: isolated accounts/projects; ingestion/worklog/search/selects/clip export; valid tested source intervals; original preservation; browser-close and worker/Temporal restart recovery; credit operation uniqueness; per-file corrupt-media failure; measured synthetic multi-hour load; exercised responsive screens; fresh migrations and documented setup.

Still **needs input**: real Gemini request semantics and token/cleanup/ambiguity validation; representative-media timing/retrieval evaluation; editor round trips. The overall goal must not be marked achieved based on the synthetic evidence.


## Final review and verification notes

- [All numbered review findings](REVIEW.md) preserve the three simplify passes, four final skill reviews, follow-up findings and the validation-discovered dispatcher issue, including resolved duplicates. The size reviewer recommended a concrete staged landing plan; no remote or PR exists to label or split.
- New regressions cover immutable transcript inputs, received invalid/nonempty responses, saved-response recovery without a provider call, cancellation between stage and request start, cumulative credit settlement, true PostgreSQL savepoint failure, long-worklog filtering/anchor/context, export path relinking/provenance/replay, grouped source hashing, cleanup preservation, allowlist revocation, batch fairness and missing-workflow cancellation.
- The first combined production run failed because a synthetic cancellation referenced a missing Temporal workflow and stalled dispatch. This was fixed, given a regression, and rerun successfully. A subsequent browser test navigation error was corrected to reopen the existing collection’s Selection data controls; selection downloads then passed.
- Integration fixture teardown now finalizes its own synthetic jobs so fake workflow IDs are not left in the local outbox. No real account or footage was removed.
- `scripts/verify_schema.py` creates a uniquely named empty database, applies 0001–0004, checks 17 forced-RLS tables, then removes only its own disposable database. The documented `scripts/dev.py --production` launcher was exercised with persistent Temporal state and all four services started successfully.
- The current local instance allowlists only this repository’s generated `.local/fixtures` for selected-root tests. General installation defaults remain an empty source-root list. User footage requires an explicit configured root or file import.

Final downloaded clip: FFprobe decoded 48 video frames at 24/1 fps, duration 2.000000 seconds. Desktop player and 390px mobile settings screenshots were visually inspected. The production journey also checks 200% zoom and page overflow.
