# RUSHES deployment status — 2026-09-10

**The public Render application is not deployed.** The private Modal compute service is deployed and working. The user has clarified that **$20 USD/month is a target, not a hard cap**, and modest overage is acceptable. Deployment is authorized with a lean configuration and controlled variable usage; the previous absolute-ceiling blocker is superseded.

## Verified resources

- Render workspace `tea-cv3ru4tumphs73elr4g0`; [RUSHES project](https://dashboard.render.com/project/prj-dahh47mk1f9s73f99g70), production environment `evm-dahh47mk1f9s73f99g7g`. The smallest Ohio Postgres instance `dpg-dahk1qek1f9s73fk9n5g-a` is available; application schema 0005 and separate application/workflow roles are provisioned. Web service and media disk deployment is in progress. Other projects were left alone.
- [Modal app rushes-compute](https://modal.com/apps/royluo05/rushes-production/deployed/rushes-compute), ID `ap-67aprLNM1JZAG0lWjzfdcQ`, environment `rushes-production`. Private functions `embed` and `transcribe_audio`; no public endpoint, persistent volume or application secrets. All RUSHES commands must explicitly select this environment; the account default remains `main`.
- Each Modal function has one maximum container, zero minimum containers, 1 CPU, 2 GiB memory, a 120-second timeout and no SDK retries. Model downloads are baked into the image. Idle deployment was verified with zero running tasks. These are execution bounds, not a monthly spending cap.
- Gemini key saved privately in the ignored `.env`; model pinned to `gemini-3.6-flash`. The user supplied Google project `projects/50426910677`. The key itself is excluded from reports and Git.

Resource IDs and state are in [deployment-inventory.json](deployment-inventory.json).

## Integration and evidence

`RUSHES_COMPUTE_BACKEND=modal` routes speech transcription and all embeddings, including search queries, through private Modal RPCs. Only derived audio (at most 60 seconds / 4 MiB) and bounded text batches leave the host. Returned model identities, dimensions, finite vectors and source-time bounds are checked. Source files, FFmpeg work, Postgres access and Temporal orchestration stay on the RUSHES host. The default `local` backend remains available.

- [Modal validation](validation/modal-compute.json): actual embeddings and speech, correct 60-second source offset, and an actual 16,000-byte Unicode request against the updated deployment passed.
- [Gemini validation](validation/gemini-live.json): one 12-second synthetic video passed upload, preparation, token counting, generation, strict local interval validation, source preservation and provider-file deletion. Preflight 1,346 tokens; measured input 1,202 and output 201. This is not representative semantic quality evaluation.
- [Full cloud browser attempt](validation/cloud-browser.json): Modal speech and indexing completed, but Gemini returned HTTP 503. The asset ended partial and the request was not repeated automatically. The complete live-provider browser journey has not passed.
- Backend suite: 91 passed, one opt-in Temporal test skipped; that Temporal test separately passed. The latest encoded-database-name guard passed its four focused workflow tests. Current Next production build passed. Final browser/container results are recorded in [CLOUD-REVIEW.md](CLOUD-REVIEW.md).

## Durable workflow hosting

The container now includes pinned Temporal Server 1.31.2 with matching PostgreSQL schemas. When `RUSHES_HOST_WORKFLOW_SERVICE=true`, the supervisor starts Temporal on loopback, waits for the default namespace, then launches both processing queues, FastAPI and the web server. Application, workflow and visibility databases must have distinct literal names; verified TLS uses system or explicit CA trust. Schema bootstrap is a separate operation and does not receive application-admin credentials at runtime. See [HOSTING.md](HOSTING.md).

[Workflow hosting verification](validation/workflow-hosting.json) passed actual verified-TLS bootstrap twice, an interrupted activity resuming with the same job ID, workflow-history recovery after container destruction/recreation, persisted sessions/media/source hashes, private-port isolation, termination during unavailable startup, and public-service closure when either worker or Temporal crashes. The two queues begin draining concurrently. The active media fixture pauses before FFmpeg executes; this test does not establish cleanup after partial media output. The final successful run uses the built linux/amd64 image with no application-source or Temporal-binary overrides. Its identity is recorded in the validation report, and the installed workflow module hash matches the reviewed source. It is not evidence for a deployed Render service or representative capacity.

## Budget decision and hosting design

[Render's bandwidth policy](https://render.com/docs/outbound-bandwidth) bills public egress above the shared Hobby allowance at $0.15/GB when a payment method exists. Its build-pipeline spending limit does not impose a total project invoice ceiling. [Modal's net-spend limit](https://modal.com/docs/guide/budgets) is workspace-wide; changing it here would also affect Wayline. Environment budgets require a paid higher-tier plan. No shared billing setting was changed.

A minimal topology to investigate is one 2 GiB Render service running the web/API, worker and a **production Temporal server backed by Postgres**, with a separate managed Postgres instance and a 10 GiB media disk. Published fixed costs would be $25 service + $6 smallest database + $1.50 for 5 GiB database storage + $2.50 media disk = **$35/month before AI, egress, builds and applicable tax**. The smallest database and colocated memory capacity have **not been validated**; a 1 GiB database increases this estimate to $48/month. The $35 lean configuration was stated after the user clarified the soft target; larger plans require revisiting the estimate. [Render pricing](https://render.com/pricing).

Even two $7 services plus the $6 database already exhaust $20 before storage and AI. The small final-image workflow fixture already peaked around 642 MiB, above a 512 MiB service limit. A larger instance still needs representative capacity validation. The SQLite-backed Temporal development server must not be deployed as production. [Temporal self-hosting](https://docs.temporal.io/self-hosted-guide/deployment).

The user clarified the spending preference directly: the target is soft and modest overage is acceptable. Keep provisioning to the smallest tested configuration and bound variable provider usage. Substantial plan upgrades still require a revised estimate.

## Remaining work

1. Select and validate the smallest stable hosting/database configuration near the soft budget target, then deploy it.
2. Verify production storage bounds and enable the combined $2 monthly Gemini/Modal allowance. The new append-only reservation ledger commits before provider dispatch, serializes concurrent calls, and retains failed/ambiguous reservations. It is conservative request exposure, not measured provider billing or an invoice ceiling. The final amd64 image, hosted Temporal startup, PostgreSQL persistence and lifecycle behavior have passed local component checks. Customer footage credits cannot cap provider dollars, and ambiguous requests must retain cost exposure.
3. Verify the actual Render ingress, HTTPS sessions, uploads, processing, recovery, playback, search and exports. The local TLS harness is evidence for a container component, not Render ingress behavior or a full hosted system.
4. Complete a successful live-provider browser journey and representative retrieval checks. Editor interchange remains explicitly experimental without editor round trips. Legal/operator details remain drafts.

## Local availability and data

The app runs at [localhost:3741](http://localhost:3741/) under the launcher recorded in `.local/launcher.pid`. The final synthetic regression launcher disables Gemini for cost-free tests; the private key remains configured in `.env`. Seven previously uploaded sources retain the verified timestamp repair and preserved source hashes documented in [real-footage-timing.json](validation/real-footage-timing.json).

During container verification, Docker reported disk I/O errors on a nearly full host. Restarting Docker recovered the existing Postgres volume; a database dump was then saved privately under `.local/hosting-qa/`. No source footage or unrelated Docker resources were deleted. The final linux/amd64 image built and passed runtime verification. During earlier builds Docker hit disk I/O errors on the nearly full Mac; its automatic image scan also caused memory/swap pressure. Docker was restarted, the existing database recovered, and only disposable RUSHES build/cache artifacts were removed. A fresh private database backup was taken, and all seven original source hashes were checked again and preserved; see [disk-recovery.json](validation/disk-recovery.json). The RUSHES image scan was stopped and the local app paused during testing, then restored. Architecture and verification limits remain explicit in the evidence.

## Provider allowance verification

The final local backend run passed 98 tests (one opt-in Temporal test skipped). Focused tests cover concurrent reservations, retained ambiguous costs, blocked network dispatch, database failures, pending Gemini checkpoint recovery, keyword-search notices and independent failed note-index retries. Gemini reserves $0.06 per call and Modal $0.01, shared across the calendar-month allowance. Both Modal functions now request and limit one CPU and 2 GiB, with a 60-second startup and 120-second execution timeout. Rejected Gemini requests stop further windows and can resume from the same checkpoint. Failed indexing can be explicitly retried without reprocessing footage. Provider build/deployment work and direct calls outside RUSHES are not covered by this ledger.
