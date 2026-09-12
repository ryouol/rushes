# RUSHES production status

RUSHES is live at **https://rushes.onrender.com** on Render, with private speech and embedding functions on Modal. Deployment identity and settings are recorded in [the inventory](deployment-inventory.json). The tested setup is approximately $35/month fixed plus variable costs, above the requested $20/month combined amount. The later soft-target instruction and current budget clarification are being reconciled in [the goal audit](GOAL-AUDIT.md); a $20 total cap is not enforced.

## Resources and cost

| Resource | Configuration | Monthly fixed estimate |
|---|---|---:|
| Render web/API/worker/Temporal | 1 CPU, 2 GiB, one instance, Ohio | $25 |
| Render Postgres | 0.1 CPU, 256 MiB | $6 |
| Postgres storage | 5 GB; automatic growth disabled | $1.50 |
| Media disk | 10 GB at `/var/data` | $2.50 |
| Total | Before AI, builds, egress and tax | **$35** |

[Render pricing](https://render.com/pricing). Larger plans are not enabled. The selected database and service passed small hosted synthetic processing and export checks; these are not multi-user or long-footage capacity tests. Sampled memory was approximately 516 MiB for the service and 117 MiB for Postgres; these are minute samples, not instantaneous peaks. See [resource evidence](validation/render-resources.json).

- Render project `prj-dahh47mk1f9s73f99g70`, production environment `evm-dahh47mk1f9s73f99g7g`.
- Web service `srv-dahk822d0e5s73fo22o0`; private GitHub repository [ryouol/rushes](https://github.com/ryouol/rushes), branch `codex/production`; automatic deployments disabled.
- Postgres `dpg-dahk1qek1f9s73fk9n5g-a`; application schema `0007`; distinct `rushes`, `rushes_temporal`, and `rushes_visibility` databases.
- Private Modal app [rushes-compute](https://modal.com/apps/royluo05/rushes-production/deployed/rushes-compute), environment `rushes-production`. Both functions scale to zero, cap at one container each, request/limit one CPU and 2 GiB, and have 60-second startup/120-second execution bounds. [Live resource-limit verification](validation/modal-resource-limits.json).

## Spending and storage controls

The application shares a **$2 per calendar month UTC provider allowance** across Gemini and Modal. It reserves $0.06 before each Gemini call and $0.01 before each Modal call. Transactions serialize concurrent reservations and retain failed or uncertain exposure. Only SELECT/INSERT are granted to the runtime on this ledger. [Allowance evidence](validation/render-provider-allowance.json).

This is conservative request exposure, not measured billing or a total invoice cap. It excludes fixed hosting, build/deployment compute, egress, tax, and direct calls outside RUSHES. Shared Modal billing settings were not changed. Rate changes require reviewing the estimates. [Modal pricing](https://modal.com/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Uploads are limited to 1 GiB each and one hour of source duration. Disk-space checks retain a 2 GiB free-space threshold; all workspaces share the 10 GB media disk. New workspaces receive 60 internal processing credits, with 20 credits maximum per analysis request. These are application allowances; Stripe and payment collection remain outside scope.

## Verified behavior

- Google connection and returning Google-only sign-in passed on local and production at runtime `83d8758`, including an existing password account with no workspace. A fresh Google email signup was covered by automated provider-contract tests, not a live signup. [Deployment and account evidence](validation/production-google-deployment.json).
- Public HTTPS API, secure HttpOnly SameSite=Strict sessions, origin rejection, and resistance to rotating forged client-IP headers. [Ingress evidence](validation/render-ingress.json). Different-client counter separation is also covered by local middleware tests; hosted spoof checks used one external client.
- The final fresh hosted browser test **passed end to end** on runtime `2cb0774`: account creation, synthetic upload, real Gemini analysis and Modal processing, preview playback, correction persistence, selections, rendered export, search, saved searches, notes, source availability, analysis estimate, collection edits, FCP7 XML, selection JSON/CSV, usage, mobile layout and logout. [Browser evidence](validation/render-browser.json). Editor round trips remain unverified; interchange is experimental.
- Earlier runs exposed Google file-status HTTP 500 errors and one zero-duration model event. Status-read retries and prompt v6 address those specific failures. Strict validation still rejects invalid model output and retains measured usage; no uncertain generation is automatically repeated. The successful earlier continuation and final fresh run are separately recorded.
- A controlled restart retained the session, ready asset and correction, preserved preview bytes, and completed a new original-copy export whose SHA-256 exactly matched the uploaded original. [Restart evidence](validation/render-restart.json).
- The final local image workflow harness separately tested interrupted work recovery, private Temporal ports, unavailable startup termination and fail-closed worker/server crashes. [Workflow evidence](validation/workflow-hosting.json). Its historical image predates the provider allowance; Render builds the current application from the recorded repository commit.

Provider preparation failures are handled separately from generation failures: bounded retries apply only to idempotent file-status reads; generation is dispatched once. Persistent preparation failure records zero generation usage, stops later windows, and preserves the checkpoint for explicit Resume processing. Failed file deletion remains recorded; deletion must succeed or its authoritative expiry must pass before another upload. Actual generation failures remain uncertain and are never automatically repeated.

## Operational boundaries

Render runtime credentials exclude the migration owner. The application role cannot bypass tenant rules, create roles/databases, connect to the workflow database, or modify spending history. Postgres external access is disabled after deployment; runtime connections use Render's same-region private network. Internal database connections are not TLS-encrypted; external bootstrap connections used certificate-verified TLS with an explicit trusted CA bundle.

Temporal is pinned to production Server 1.31.2 and PostgreSQL schemas, listens only on loopback, and keeps three days of workflow history. The media disk makes service redeployments/restarts briefly unavailable. Modal environment separation organizes resources within the existing workspace; it is not a separate credential trust boundary.

The first app landing exceeds the review skill's size guideline. The full numbered review record and dispositions are preserved in [PRODUCTION-REVIEW.md](PRODUCTION-REVIEW.md). Backend verification passed 102 tests with one opt-in live Temporal test skipped; the final prompt refinement passed 21 focused inference/timing tests. No GitHub PR exists and no PR comments were posted. Legal/operator copy remains a draft and production-scale retrieval/editor qualification remains future work.

## Local data

The local app and database remain available independently; `.local/launcher.pid` records the launcher. Seven original MOV source hashes survived the earlier host disk-pressure incident, documented in [disk recovery](validation/disk-recovery.json). Private credentials, QA sessions and database backups remain ignored under `.local/` or `.env` and were not pushed to GitHub.

On 12 September, local Docker storage errors were recovered by clearing a download cache and restarting Docker. The existing database volume was reused, a fresh backup was checked, and all seven original hashes matched. The local application is running again at `http://localhost:3741`. [Recovery record](validation/disk-recovery-20260912.json). Local `.env` now has its own $2 monthly provider allowance; its ledger is separate from production and does not enforce a combined invoice cap.

## Supervisor follow-up

The supervisor now releases configuration/readiness dependencies after startup. Seven focused tests and the fresh full 2 GiB container upload/recovery/lifecycle harness passed. [Review](SUPERVISOR-REVIEW.md), [container evidence](validation/supervisor-hosting.json). Local tests of the $7, 512 MiB service size ran out of memory during sign-in, even with the smaller supervisor; emulation limits native-capacity conclusions. [Memory evidence](validation/supervisor-memory.json). The existing Render size remains in place and the $20/month budget discrepancy remains open.

This supervisor follow-up is live at runtime `7ba9a34` / deployment `dep-daip0kvqj5pc73b0rlng`. Startup and public endpoint checks passed, and the existing plan, instance count, disk and all environment values were verified unchanged. [Deployment evidence](validation/supervisor-deployment.json). Paid processing and real Google login were not repeated; their earlier revision-specific evidence remains above. Preexisting Google file-cleanup 403 responses remain tracked for follow-up; deletion is not confirmed.

## Provider cleanup follow-up

Runtime `3584971` / deployment `dep-daipmk8ae00c73ffk0c0` is live. The additive `0007` migration preserved all 13 existing analysis windows and 17 forced-RLS tables. Ninety isolated tests, fresh migrations, and an existing-row upgrade check passed. [Review and all findings](PROVIDER-CLEANUP-REVIEW.md), [deployment evidence](validation/provider-cleanup-deployment.json).

The newer shared-Python-runtime candidate is committed separately and has not been deployed or loaded by the local launcher. Its 132 isolated regressions pass, including actual Uvicorn failure shutdown and transcript recovery across cancellation. An earlier candidate passed a disposable 2 GiB 4K workflow check; a 512 MiB 4K check ran out of memory. The next lower-cost step requires a lighter frontend and further capacity checks. Production remains on the same plan with automatic deployments disabled. [Candidate review](SHARED-RUNTIME-REVIEW.md), [scope-specific evidence](validation/shared-runtime.json).

Uploaded files now retain their actual provider expiry before generation. Known expired files can be released without another remote call; unknown expiry stays conservative. Unresolved cleanup retries are delayed one hour so newer files can progress. Read-only production inspection confirmed the new implementation and delayed retries for the three retained ambiguous references. No uncertain generation was repeated.

Local access is running at `http://localhost:3741`, with the existing signed-in workspace and all seven original videos visible. Those seven videos still need analysis after their historical missing-key failures; the key is configured now, but they were not reprocessed during this repair while the combined-budget clarification remains pending. The current Render plans, disk, instance count, environment values and provider allowance were preserved. Paid processing and real Google login were not repeated on this deployment.
