# Production preparation review — 2026-09-10

> Historical review: current provider configuration, deployment state and later fixes are recorded in [CLOUD-REVIEW.md](CLOUD-REVIEW.md) and [PRODUCTION.md](PRODUCTION.md). Earlier missing-key and empty-Modal statements below describe the prior snapshot.

All issues returned by the three simplify agents and four xhigh final skill reviewers are preserved below, including duplicates and open gates. This supplements, rather than replaces, the earlier 48-item REVIEW.md. File locations refer to the post-repair snapshot at report generation. The verification section below records the final checks and their limits.

1. **Simplify / reuse — Upload validation could crash React.** [web/components/project.tsx:933](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:933>) Fixed: XHR and fetch share typed error normalization; arrays/objects never enter progress text. Browser validation regression added.

2. **Simplify / reuse — Late search restored cleared results.** [web/components/project.tsx:173](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:173>) Fixed: one reset helper aborts the request and clears query, results, notice and busy state.

3. **Simplify / reuse — Settings lacked guarded loading.** [web/components/settings.tsx:59](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/settings.tsx:59>) Fixed: abort superseded/unmounted requests, commit the three related responses together, key the view by workspace.

4. **Simplify / quality — Adjusting another select reused stale fields.** [web/components/project.tsx:1267](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:1267>) Fixed: remount the uncontrolled form for each selection ID.

5. **Simplify / quality — Old workspace settings could overwrite new settings.** [web/components/rushes.tsx:281](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/rushes.tsx:281>) Fixed; duplicate of reuse finding, retained here as returned by the reviewer.

6. **Simplify / quality — Concurrent suggestion additions removed the wrong row.** [web/components/project.tsx:1180](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:1180>) Fixed: use stable asset/start/end identity and guard repeated submissions.

7. **Simplify / quality — Cleared searches could reappear.** [web/components/project.tsx:173](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:173>) Fixed; duplicate of reuse finding.

8. **Simplify / quality — Saved query differed from displayed results.** [web/components/project.tsx:407](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:407>) Fixed: save the submitted result query, not the subsequently edited input.

9. **Simplify / quality — Projects after the first 40 were unreachable.** [web/components/rushes.tsx:38](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/rushes.tsx:38>) Fixed: bounded API pages plus total, matching UI navigation and integration/browser boundary tests.

10. **Simplify / efficiency — Repeated frame-map scans scale quadratically.** [backend/rushes/source_frames.py:11](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/source_frames.py:11>) Deferred optimization, not claimed fixed. Reviewer measured 1.179 seconds to locate the last 20 seconds of a two-hour/30fps map; 360 windows revisit about 39 million records. A versioned seekable index needs its own integrity/recovery design. The current reader remains bounded in memory. This has no impact on the seven short repaired clips, but is a documented long-footage performance limitation.

11. **Simplify / efficiency — Settlement loaded full model responses.** [backend/rushes/activities.py:534](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:534>) Fixed: select only completed interval bounds and the necessary mapped JSON scalar endpoints, without loading full model responses.

12. **Simplify / efficiency — Export history loaded discarded plans.** [backend/rushes/routes_exports.py:198](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_exports.py:198>) Fixed: exclude plan columns in SQL before serialization.

13. **Simplify / efficiency — Export preview performed two reads per select.** [backend/rushes/routes_exports.py:62](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_exports.py:62>) Fixed: fetch distinct assets and timelines in two bounded queries, preserving project/tenant checks.

14. **Simplify / efficiency — Upload progress published unchanged state.** [web/components/project.tsx:917](</Users/royluo/Documents/ChatGPT/Video Clipping/web/components/project.tsx:917>) Fixed: retain the same state reference when rounded percentage and status are unchanged.

15. **Final / breaking changes — Resuming across preprocessing versions lost the manifest.** [backend/rushes/pipeline.py:236](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/pipeline.py:236>) Fixed: dependent processing ensures the current preparation exists within an activity, rebuilding from the authorized source when needed; workflow command order is unchanged.

16. **Final / breaking changes — Video version bump duplicated transcripts.** [backend/rushes/inference.py:19](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/inference.py:19>) Fixed: the unchanged audio recipe keeps its existing cache identity; exact committed per-window usage prevents reinserting or overwriting corrected transcripts. Existing valid inactive v2 previews remain usable.

17. **Final / breaking changes — Retries reused clips from the old renderer.** [backend/rushes/exports.py:52](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/exports.py:52>) Fixed: unfinished clip receipts require the current renderer version. Byte-exact copy receipts remain reusable.

18. **Final / breaking changes — Changed indexed sources could not follow reimport guidance.** [backend/rushes/routes_media.py:132](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_media.py:132>) Fixed: changed size/mtime produces an actionable error directing a new upload or distinct indexed path. It does not silently replace a fingerprinted source.

19. **Final / breaking changes — Source endpoint exceeded proxy endpoint.** [backend/rushes/pipeline.py:219](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/pipeline.py:219>) Fixed: explicitly crop derived extraction to measured proxy coverage, retain both intervals/offset/tail, and bound transcription to actual coverage. This repairs the additional 8,334-microsecond tail mismatch in real footage.

20. **Final / breaking changes — Hosted origin/proxy configuration is absent.** [backend/rushes/config.py:63](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/config.py:63>) Open deployment gate: current configuration is intentionally local. See PRODUCTION.md. Changing only the origin guard would not establish a safe hosted topology.

21. **Final / breaking changes — Remote workers cannot access local paths.** [backend/rushes/pipeline.py:36](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/pipeline.py:36>) Open deployment gate: no Modal media/storage/execution integration exists; only an empty dedicated environment was created.

22. **Final / breaking changes — Combined hard spending cap is unresolved.** [docs/deployment-inventory.json:14](</Users/royluo/Documents/ChatGPT/Video Clipping/docs/deployment-inventory.json:14>) Open authorization/provider gate: no billable services started. Render egress remains billable; pending user question must not be treated as consent to overruns.

23. **Final / context — Oversized WebMCP search context.** [web/lib/webmcp.ts:67](</Users/royluo/Documents/ChatGPT/Video Clipping/web/lib/webmcp.ts:67>) Fixed: dedicated typed citation/excerpt result capped at 8,000 serialized UTF-8 bytes with truncation flag, leaving rich UI results intact. Reviewer reproduced 249,899 bytes / 48,000 words before the fix. Worst-case escaped multilingual regression added. Original severity was P0 manual-review gate / P2 runtime impact.

24. **Final / context — Footage credits do not enforce a monthly dollar cap.** [backend/rushes/credits.py:18](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/credits.py:18>) Open deployment gate. Explicit output/thinking limits were added, but a separate shared provider-dollar reservation ledger and provider-side controls still must be implemented before hosted paid analysis. Customer footage credits are not represented as cloud dollars.

25. **Final / context — Failed/ambiguous attempts release customer credits.** [backend/rushes/activities.py:534](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:534>) Documented customer-credit behavior remains; it must not enforce provider spending. Open deployment gate: separate cost accounting must debit actual paid attempts and retain worst-case ambiguous exposure.

26. **Final / context — Thinking tokens omitted from normalized usage.** [backend/rushes/inference.py:185](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/inference.py:185>) Fixed: output usage now includes candidate and thinking tokens, with the separate raw provider fields retained. New generation settings explicitly disable thinking for the configured Gemini 2.5 Flash and cap output at 4,096 tokens. Live provider reconciliation remains unverified.

27. **Final / context — Gemini input exceeds the skill’s 1K manual-review threshold.** [backend/rushes/inference.py:159](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/inference.py:159>) Manual review completed: transcript serialized <=8,000 UTF-8 bytes; video+text pre-generation count <=10,000 tokens; independent immutable requests, not growing conversation history. No unbounded-input defect found. Live counting remains unverified. Rust core/context traits are N/A.

28. **Final / testing — Hosted startup is rejected.** [backend/rushes/config.py:63](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/config.py:63>) Open deployment gate; duplicate of the hosted configuration finding. Local Next production-build tests are not HTTPS production smoke tests.

29. **Final / testing — Partial PATCH silently changed selection endpoints.** [backend/rushes/routes_collections.py:162](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_collections.py:162>) Fixed: lock the current item, merge explicitly supplied fields, validate merged endpoints, preserve omitted note/timing. Integration covers note-only, single-endpoint and invalid merged updates.

30. **Final / testing — Canceled received responses bypassed provider cleanup.** [backend/rushes/maintenance.py:65](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/maintenance.py:65>) Fixed: aged received checkpoints are eligible for deletion retry even if their saved response is retained for recovery. Cleanup selects only IDs/file names, continues after an individual failure and locks before clearing a matching file reference. Integration verifies both response retention and continued cleanup.

31. **Final / testing — Other projects hid active jobs from SSE.** [backend/rushes/routes_media.py:447](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_media.py:447>) Fixed: frontend subscribes by project; server verifies ownership and filters before bounded ordering. Running/cancel-requested, dispatched and queued jobs sort ahead of history in that order. Integration covers 105 newer cross-project historical jobs and 105 same-project queued jobs.

32. **Final / testing — Collection #201 disappeared after creation.** [backend/rushes/routes_collections.py:57](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_collections.py:57>) Fixed: explicit transactional 200-collection/saved-search limit, matching the retrievable collection list. User receives an actionable error rather than an inaccessible new collection. Boundary integration added.

33. **Final / testing — Older exports became inaccessible.** [backend/rushes/routes_exports.py:196](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_exports.py:196>) Fixed: paginated history with total count and UI navigation; integration crosses the 100-export boundary. SQL still excludes private plans.

34. **Final / testing — Later members lacked removal controls.** [backend/rushes/routes_settings.py:125](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_settings.py:125>) Fixed: explicit transactional 200-member limit matching the manageable list; existing member role changes still work at the limit.

35. **Final / testing — Live analysis/provider accounting unverified.** [backend/rushes/inference.py:161](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/inference.py:161>) Open credential/validation gate: Gemini key absent. Needs bounded real upload, activation, count, generation, durable response, deletion and billing reconciliation. Seven MOV checks do not verify semantics.

36. **Final / testing — No verified deployment or combined budget stop.** [docs/deployment-inventory.json:36](</Users/royluo/Documents/ChatGPT/Video Clipping/docs/deployment-inventory.json:36>) Open deployment gate; no billable service or live production URL exists. Provider project folders alone are not deployment.

37. **Final / testing — Semantic search/editor compatibility unmeasured.** [tests/test_interchange.py:15](</Users/royluo/Documents/ChatGPT/Video Clipping/tests/test_interchange.py:15>) Open validation gate: keep interchange experimental and retain explicit lack of editor round trip and labeled retrieval evaluation. Do not infer these from synthetic timing tests.

38. **Final / change size — Initial app exceeds bounded review guidance.** [backend/rushes/api.py:19](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/api.py:19>) Open review-process limitation: reviewer snapshot had 21,035 lines/106 files, 15,863 authored after generated/evidence exclusions. Smallest coherent initial stage is 216 authored lines: .gitignore, .python-version, pyproject.toml, rushes/__init__.py, timing.py, test_timing.py. Leave tests/conftest.py out of that first stage because its eager API import pulls all routers. Subsequent stages: storage/config, pure interchange, persistence+RLS, media inspection/render, durable preparation, paid analysis/checkpoints, endpoints, then frontend surfaces with matching tests. No PR exists to label. Later repair edits exceed the snapshot; counts are historical, not a final current-diff assertion.

39. **Simplify / rejected suspicion — FFmpeg allegedly decoded the entire remainder for every trim.** [backend/rushes/media.py:393](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/media.py:393>) Rejected after the reviewer measured actual decoding: trim propagated EOF and only 26 frames decoded for a one-second clip. No speculative duration workaround was applied.

40. **Final follow-up / testing — Queued work could hide a running job.** [backend/rushes/routes_media.py:424](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/routes_media.py:424>) Fixed: running/cancel-requested jobs sort before dispatched, queued and historical work in both GET and SSE. Regression covers 105 newer queued jobs in the same project as well as cross-project history.

41. **Final follow-up / testing — Model evidence discarded degraded-search status.** [web/lib/model-evidence.ts:23](</Users/royluo/Documents/ChatGPT/Video Clipping/web/lib/model-evidence.ts:23>) Fixed: preserve retrieval mode and a bounded server notice separately from evidence guidance, within the same 8,000-byte serialized envelope. The multilingual regression asserts the keyword fallback warning.

42. **Final follow-up / breaking — Gemini accepted an omitted proxy tail.** [backend/rushes/activities.py:291](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:291>) Fixed: generation and received-response validation share the mapped first source frame and extracted proxy endpoint; requested source bounds remain separate. Regression rejects evidence in the omitted tail.

43. **Final follow-up / breaking — Usage included omitted footage.** [backend/rushes/activities.py:534](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:534>) Fixed: new transcription and analysis usage use extracted coverage; settlement unions effective intervals from scalar JSON projections without loading model responses. The provider interface regression verifies a nine-second crop, nine-second usage and 150-millicredit settlement.

44. **Final follow-up / breaking — Thinking settings broke accepted model configurations.** [backend/rushes/config.py:8](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/config.py:8>) Fixed: settings and analyzer construction both validate gemini-2.5-flash before a provider upload. Other models are rejected with an actionable configuration error. This bounded configuration disables thinking and caps generated output; it does not establish a monthly dollar limit. Google documents model-specific thinking support: https://ai.google.dev/gemini-api/docs/generate-content/thinking .

45. **Final follow-up / breaking — Settlement overflowed 32-bit microseconds.** [backend/rushes/activities.py:540](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:540>) Fixed: JSON interval extraction explicitly casts to PostgreSQL BIGINT. A 40-minute offset regression verifies cropped overlapping coverage and historical mappings.

46. **Final follow-up / breaking — Historical settlement could decrease on recovery.** [backend/rushes/activities.py:547](</Users/royluo/Documents/ChatGPT/Video Clipping/backend/rushes/activities.py:547>) Fixed: historical mappings without extraction metadata retain both original requested bounds. New mappings use both effective bounds. The long-offset regression includes a historical first-frame gap and repeats reservation/settlement without decreasing prior charges.

## Verification

- Final backend suite with the opt-in real Temporal test enabled: **66 passed in 42.42 seconds**. One upstream Hugging Face deprecation warning; no skipped tests in this run.
- Next.js production build and TypeScript check passed.
- Playwright: **5 passed in 37.4 seconds**. The core journey uses the real API/worker for account creation, upload, persistent worklog, selects and rendered export. Four focused UI/output regressions use explicitly synthetic fixtures.
- Ruff checks passed. Production npm audit reported zero known vulnerabilities.
- Source/client-bundle audit: 126 files, 48 API routes, zero configured-secret or credential-shape findings. This is a bounded scan, not a guarantee against every possible secret pattern.
- Seven actual uploaded MOV sources preserved their hashes and showed zero measured source/proxy PTS drift. All seven now have previews and completed local processing; their honest status remains partial without Gemini visual analysis.
- Follow-up findings 40–46 were fixed; tests cover same-project job pressure, degraded-search status, cropped coverage, supported models, 64-bit offsets and historical cumulative settlement. The last reviewer identified the historical fallback issue, which was then fixed and passed both focused and full verification.

**Production remains undeployed.** Live Gemini, strict combined spending enforcement, hosted infrastructure/storage/auth, representative semantic quality and editor round trips remain open. The long-footage frame-map optimization and initial change-size review limitation are also retained explicitly above. No PR exists, and no GitHub review comments or labels were posted.


## Provider allowance follow-up

50. **Simplify / reuse and quality — duplicate timeout option rejected valid database URLs.** [provider_budget.py:34](../backend/rushes/provider_budget.py#L34) Fixed: serialize the connection identity and merge query options before setting one timeout; preserves CA paths containing spaces.

51. **Simplify / efficiency — exhausted allowance prepared every remaining clip.** [activities.py:432](../backend/rushes/activities.py#L432) Fixed: a distinct definitely-unsent denial restores the pending window, records no usage, and raises a nonretryable failure to stop remaining work. Existing checkpoints and settlement remain intact.

52. **Simplify / quality — failed note indexing had no retry path.** [routes_media.py:522](../backend/rushes/routes_media.py#L522) Fixed: editors can resume independent failed index jobs without rerunning media preparation.

53. **Simplify / quality — allowance exhaustion looked like temporary search warmup.** [routes_search.py:138](../backend/rushes/routes_search.py#L138) Fixed: explicit allowance notice alongside keyword evidence.

54. **Simplify / quality — Modal memory was only a minimum request.** [modal_app.py:46](../deploy/modal_app.py#L46) Fixed: both functions set CPU and memory request/limit tuples and bounded startup/runtime. Updated functions deployed; representative post-change validation remains pending.

55. **Final / breaking and testing — latest-per-kind retry hid older failed note jobs.** [routes_media.py:243](../backend/rushes/routes_media.py#L243) Fixed: failed index jobs retain independent eligibility; integration regression includes an intervening successful index job.

Context follow-up found no new prompt/provenance defect. No GitHub PR exists to label; no comments were posted. The allowance is one shared pool, not separate $2 budgets per provider. Historical credential and absolute-budget blockers above are superseded by the configured Gemini key and the user's soft-budget clarification; actual hosted verification remains outstanding.

56. **Final / change size — initial landing remains oversized.** [pyproject.toml:1](../pyproject.toml#L1) Open process limitation: the 23:55 UTC snapshot contains 145 files / 25,979 lines, of which 19,879 are authored source, tests, scripts, configuration and prose. Earlier functional review dispositions remain recorded. A future reviewable sequence starts with timing (161 lines plus minimal package setup), source-frame/interchange (285), persistence, media, workflows, endpoints and frontend; provider allowance is a separate 294-line core stage plus call sites, and independent index retries can be separate. No claim that this initial deployment landing meets the 800-line guidance.

57. **Hosted testing — live-mode browser assertions assumed disabled analysis and an already selected collection.** [core.spec.ts:108](../web/e2e/core.spec.ts#L108) Fixed: explicitly select the destination and test enabled analysis only in live mode. Review found no weakened coverage; the successful hosted analysis was resumed through all remaining UI checks.

58. **Hosted testing — transient file-status failures unnecessarily stopped analysis and looked ambiguous.** [inference.py:182](../backend/rushes/inference.py#L182) Fixed: retry only idempotent status GET failures twice, retain one generation dispatch, and record zero generation usage for failures before submission. Three new tests cover transient status, persistent status and ambiguous generation, including cleanup and reservation counts. All simplify reviewers found no new issue.

59. **Final / breaking — preparation failures could repeat across every remaining window.** [activities.py:433](../backend/rushes/activities.py#L433) Fixed: use a distinct preparation_failed result, restore the definitely-unsent pending checkpoint, and raise nonretryable ProviderPreparationError. Explicit retry reuses the same job/run/window. The integration regression covers both spending denial and provider preparation failure through successful retry and settlement.

60. **Final / breaking — failed provider cleanup could lose the uploaded-file reference.** [activities.py:388](../backend/rushes/activities.py#L388) Fixed: preserve the pending cleanup reference, include pending windows in maintenance, and clean the previous upload before another attempt. Failed cleanup leaves the checkpoint unchanged and sends no new analysis. The regression exercises cleanup failure, successful recovery and settlement; the reviewer confirmed resolution.

## Current deployment follow-up verification

- Full backend suite: **102 passed, 1 skipped in 25.93 seconds**. The skipped test is the opt-in live Temporal integration; the previously recorded workflow harness remains separate evidence. One upstream Hugging Face deprecation warning.
- Ruff and diff whitespace checks passed. The focused preparation/budget/recovery suite passed all 32 tests. The new runtime changes are limited to backend preparation and cleanup; browser changes correct live-mode assumptions and allow an explicit hosted base URL.
- Hosted deployment, Modal resource limits, ingress and restart results are recorded in [PRODUCTION.md](PRODUCTION.md) and its linked evidence. These supersede earlier undeployed and missing-credential gates. The initial landing size and representative retrieval/editor qualification limitations remain open.
