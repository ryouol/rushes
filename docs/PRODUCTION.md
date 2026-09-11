# RUSHES production status

RUSHES is live at **https://rushes.onrender.com** on Render, with private speech and embedding functions on Modal. Deployment identity and settings are recorded in [the inventory](deployment-inventory.json). The user clarified that $20/month is a soft target; the lean tested setup is approximately $35/month fixed plus variable costs.

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
- Postgres `dpg-dahk1qek1f9s73fk9n5g-a`; application schema `0005`; distinct `rushes`, `rushes_temporal`, and `rushes_visibility` databases.
- Private Modal app [rushes-compute](https://modal.com/apps/royluo05/rushes-production/deployed/rushes-compute), environment `rushes-production`. Both functions scale to zero, cap at one container each, request/limit one CPU and 2 GiB, and have 60-second startup/120-second execution bounds. [Live resource-limit verification](validation/modal-resource-limits.json).

## Spending and storage controls

The application shares a **$2 per calendar month UTC provider allowance** across Gemini and Modal. It reserves $0.06 before each Gemini call and $0.01 before each Modal call. Transactions serialize concurrent reservations and retain failed or uncertain exposure. Only SELECT/INSERT are granted to the runtime on this ledger. [Allowance evidence](validation/render-provider-allowance.json).

This is conservative request exposure, not measured billing or a total invoice cap. It excludes fixed hosting, build/deployment compute, egress, tax, and direct calls outside RUSHES. Shared Modal billing settings were not changed. Rate changes require reviewing the estimates. [Modal pricing](https://modal.com/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Uploads are limited to 1 GiB each and one hour of source duration. Disk-space checks retain a 2 GiB free-space threshold; all workspaces share the 10 GB media disk. New workspaces receive 60 internal processing credits, with 20 credits maximum per analysis request. These are application allowances; Stripe and payment collection remain outside scope.

## Verified behavior

- Public HTTPS API, secure HttpOnly SameSite=Strict sessions, origin rejection, and resistance to rotating forged client-IP headers. [Ingress evidence](validation/render-ingress.json). Different-client counter separation is also covered by local middleware tests; hosted spoof checks used one external client.
- Fresh production accounts uploaded synthetic footage, completed real Gemini analysis and Modal processing, played previews, and saved corrections. The remaining selection/search/export journey passed using a successful analysis and its existing session after correcting two test assumptions. Fully fresh reruns also encountered Google file-status HTTP 500 errors; those assets remained partial without repeating uncertain generation.
- The hosted continuation checked selection saves, rendered clips, correction history, keyword/semantic search fallback, saved searches, notes, source availability, FCP7 XML generation, selection JSON/CSV, usage settings, mobile overflow and logout. Editor round trips remain unverified; interchange is experimental.
- A controlled restart retained the session, ready asset and correction, preserved preview bytes, and completed a new original-copy export whose SHA-256 exactly matched the uploaded original. [Restart evidence](validation/render-restart.json).
- The final local image workflow harness separately tested interrupted work recovery, private Temporal ports, unavailable startup termination and fail-closed worker/server crashes. [Workflow evidence](validation/workflow-hosting.json). Its historical image predates the provider allowance; Render builds the current application from the recorded repository commit.

Provider preparation failures are handled separately from generation failures: bounded retries apply only to idempotent file-status reads; generation is dispatched once. Persistent preparation failure records zero generation usage, stops later windows, and preserves the checkpoint for explicit Resume processing. Failed file deletion remains recorded and must complete before another upload. Actual generation failures remain uncertain and are never automatically repeated.

## Operational boundaries

Render runtime credentials exclude the migration owner. The application role cannot bypass tenant rules, create roles/databases, connect to the workflow database, or modify spending history. Postgres external access is disabled after deployment; runtime connections use Render's same-region private network. Internal database connections are not TLS-encrypted; external bootstrap connections used certificate-verified TLS with an explicit trusted CA bundle.

Temporal is pinned to production Server 1.31.2 and PostgreSQL schemas, listens only on loopback, and keeps three days of workflow history. The media disk makes service redeployments/restarts briefly unavailable. Modal environment separation organizes resources within the existing workspace; it is not a separate credential trust boundary.

The first app landing exceeds the review skill's size guideline. The full numbered review record and dispositions are preserved in [PRODUCTION-REVIEW.md](PRODUCTION-REVIEW.md). No GitHub PR exists and no PR comments were posted. Legal/operator copy remains a draft and production-scale retrieval/editor qualification remains future work.

## Local data

The local app and database remain available independently; `.local/launcher.pid` records the launcher. Seven original MOV source hashes survived the earlier host disk-pressure incident, documented in [disk recovery](validation/disk-recovery.json). Private credentials, QA sessions and database backups remain ignored under `.local/` or `.env` and were not pushed to GitHub.
