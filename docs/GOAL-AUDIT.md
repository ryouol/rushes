# Original goal audit — 11 September 2026

This audit reconciles the original footage-worklog brief with the later production request and the newer work performed in the shared repository. It does not declare the goal complete. Historical tests below retain their original scope; a passing synthetic test does not establish representative footage quality.

## Current state inspected

At 15:05 UTC, the local app and public `https://rushes.onrender.com/api/health` returned HTTP 200. The production Google-provider endpoint returned `{google: true}`. Render's authenticated API independently reported one unsuspended `1c-2g` RUSHES instance, an available `0.1c-256mb` Postgres database, and live deployment `dep-dai1ddm743jc73dn43bg` of commit `89471a8a5d84cd11a0ccfb0086050ecb3064baba`.

The user's 10 September 23:35 UTC message in **Check current project status** relaxed the absolute $20 ceiling to a target with limited overage. The previous hard-cap and missing-Gemini blockers are therefore superseded. The actual fixed estimate remains **$35/month before variable charges and tax**, as itemized in [PRODUCTION.md](PRODUCTION.md). The separate $2 provider allowance is conservative request exposure, not a total provider invoice cap. No resource or spending setting was changed by this audit.

The latest Google deployment and the account-without-workspaces connection repair are owned by that active task. Its [deployment evidence](validation/production-google-deployment.json) records the real provider exchange, current account-linking status and follow-up deployment. Configuration presence alone is not proof of completed Google login.

## Requirements and evidence

| Original requirement | Evidence inspected | Disposition |
| --- | --- | --- |
| Accounts, isolated workspaces/projects, signup/login/logout | Hosted browser journey, runtime RLS checks, latest authentication and migration evidence | Implemented; newer Google connection completion is tracked separately |
| Multiple uploads and allowlisted directory indexing | Original core browser journey, selected-root Temporal tests, seven real uploaded MOVs | Implemented; directory access remains explicit and local |
| Durable multi-hour ingestion | Ten-hour/fifty-file synthetic load plus worker/Temporal interruption and production-container recovery | Implemented with measured synthetic evidence; representative long-footage capacity is unverified |
| Persistent observations, provenance, correction history and playable timestamps | Hosted correction/restart tests; source/proxy timing report; pipeline/recovery regressions | Implemented for exercised sources and intervals; model localization remains approximate |
| Source PTS, rational/VFR/drop-frame/rotation/no-audio boundaries | Timing/media tests and [real-footage-timing.json](validation/real-footage-timing.json) | Deterministic checks passed; seven real originals preserved, zero measured source/proxy PTS drift |
| Analysis-window validation and uncertain provider outcomes | Real Gemini usage/deletion record, rejected zero-duration model event, single-dispatch and preparation-recovery tests | Implemented; invalid output is retained and reported, uncertain generation is not retried automatically |
| Compare full-proxy provider offsets against physical chunks | Decision log explicitly chooses bounded physical chunks provisionally | Incomplete: no comparative live benchmark establishes offset semantics or a performance advantage |
| Hybrid retrieval, bounded neighboring evidence, validated citations | Search implementation and browser checks, bounded model-evidence regression | Implemented; no human-labeled precision/recall evaluation by content type |
| AI organization, editable categories/assignments and uncategorized state | Organizer/category tests and [live category smoke](design/2026-09-premium/qa/live-ai-category-smoke.json) | Implemented; live smoke uses a generated illustration and is not camera-footage semantic evaluation |
| Collections, saved queries, selects, in/out adjustment, clip/copy exports | Hosted upload-to-export journey and restart original-copy SHA-256 check | Implemented; originals are preserved and virtual collections do not duplicate them |
| JSON/CSV and editor interchange | Browser downloads, deterministic interchange tests | JSON/CSV implemented; FCP7 XML/FCPXML remain experimental; target-editor round trips need an installed supported editor; EDL N/A without a justified need |
| Usage, reservations, concurrency, settlements, explicit reanalysis estimates | Transactional credit tests and hosted provider-allowance evidence | Implemented; customer credits, conservative provider reservations and actual cloud invoices remain distinct |
| Local executable speech, private remote compute and artifact access | Local Whisper tests, deployed private Modal speech/embedding checks, hosted processing | Implemented; server-hosted media remains private and Modal receives bounded derived inputs |
| Reproducible setup and persistent production services | README, migration verification, tested image/supervisor, Render/Modal inventory and restart evidence | Implemented for recorded topology; fixed cost exceeds the original $20 target |
| Endpoint authorization, tenant RLS, private storage, safe filesystem and source/bundle secret checks | [Security audit](SECURITY-AUDIT.md), fresh migration 0006, endpoint inventory and denial tests | Exercised checks passed; bounded audits are not proof against every vulnerability |
| Responsive screens, keyboard/focus, loading/failure/recovery and reduced motion | [Refinement QA](design/2026-09-refinement/QA.md), screenshots and motion lifecycle evidence | Implemented within stated browser/harness scope; not an assistive-technology certification |
| Website titles/images/favicon/errors/navigation, disabled analytics and honest policy placeholders | Website-hardening checklist and latest refinement review | Implemented or explicitly N/A; real legal/operator/support details remain needed before a commercial release |
| Simplify and all code-review perspectives | REVIEW.md, PRODUCTION-REVIEW.md, CLOUD-REVIEW.md and design review records | Reviews and fixes recorded, including all returned findings and limitations; initial landing remains oversized |
| Representative retrieval/timing qualification and handoff | Only synthetic/generated media and seven short uploaded sources are recorded | Incomplete: representative multi-hour media and a human-labeled query set are still required for the requested quality evaluation |

## Remaining completion evidence

1. **TODO: provide representative footage and human-labeled queries**, with relevant source intervals and content-type labels, to measure retrieval precision/recall and semantic localization. Existing small/synthetic success must not be described as this evaluation.
2. Finish the explicit full-proxy-offset versus physical-chunk comparison using bounded derived media, real provider usage and cleanup, within the shared allowance. Until then the physical-chunk decision remains provisional.
3. Keep newer Google linking/returning-login and latest deployment evidence current in the active deployment task. This is additional user-requested work, not evidence supplied by an availability endpoint.
4. **TODO: provide a supported target editor** for interchange round trips. This does not delay the working folder/copy/clip workflow, but advanced interchange cannot be described as fully qualified.
5. **TODO: provide reviewed legal/operator/support information** for commercial-release copy. Do not invent contact details, terms or retention promises.

The original goal remains incomplete while its essential representative-media and provider-comparison verification is missing. The deployed application is usable; production availability and full release qualification are separate claims.

## Browser regression audit

The previously authored authentication/history and state suites were actually executed. The first run on the shared local app had 22 passes and four failures. Three test assumptions were repaired; the shared runtime was subsequently rebuilt by the parallel deployment task, so final verification used a separate archive of deployed revision `89471a8`, its own Next build on loopback port 3841, and fully mocked API routes. No user data or paid providers were involved.

1. **Fixed — Authentication alert selector included Next's route announcer.** [auth.spec.ts:160](../web/e2e/auth.spec.ts#L160) now scopes the assertion to the main authentication form. Expected cancellation/account-link messages and suppression of an unknown error code remain tested. This repair is included in commit `83d8758`.
2. **Fixed — Deletion navigation test captured the previous URL.** [state-regressions.spec.ts:297](../web/e2e/state-regressions.spec.ts#L297) now waits for the actual second-project URL before releasing the delayed deletion and checking that it cannot redirect the newer view.
3. **Fixed — Stale-card test assumed inert elements disappear from role queries.** [state-regressions.spec.ts:996](../web/e2e/state-regressions.spec.ts#L996) now tests native focus and pointer-action denial while retaining assertions that the stale grid is mounted and inert. Recovery still has to replace the stale results and clear its error.
4. **Not reproduced — Player's final processing poll timed out in the shared run.** [player.tsx:220](../web/components/player.tsx#L220) was unchanged. The separate instrumented reproduction passed the original test body: queued → preview_ready → ready, four-second polls, preserved draft/range and successful correction save. No player fix was invented. The exact first-run interruption remains unknown; its trace was overwritten by a subsequent Playwright run.

Final isolated results: **25 browser tests passed in 25.3 seconds**, plus **one separately instrumented player test passed**. The build passed. Two independent final reviewers found no actionable issue in the test repairs or reproduced player behavior. These checks validate the archived revision with the stated test corrections; they do not validate subsequent account-only Settings changes or live Google consent. [Machine-readable evidence](validation/goal-browser-audit.json) records the boundaries and logs.
