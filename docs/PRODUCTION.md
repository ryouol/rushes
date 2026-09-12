# RUSHES production status

RUSHES is live at **https://rushes.onrender.com** on Render, with private speech and embedding functions on Modal. The local app is running at **http://localhost:3741**. All 14 production uploads and all nine local MOV assets are now ready after recovering the budget-blocked and older partial analyses. Current deployment identity and settings are recorded in [the inventory](deployment-inventory.json).

## Resources and the combined monthly budget

The user confirmed **$20 per month combined**, covering this project's local and cloud provider calls plus hosting. The running service was reduced from $25 to $7 after replacing the production Node process with built pages served by the shared Python runtime.

| Resource | Configuration | Monthly estimate |
|---|---|---:|
| Render web/API/worker/Temporal | 0.5 CPU, 512 MiB, one instance, Ohio | $7 |
| Render Postgres | 0.1 CPU, 256 MiB | $6 |
| Postgres storage | 5 GB; automatic growth disabled | $1.50 |
| Media disk | 10 GB at `/var/data` | $2.50 |
| Fixed hosting total | Before AI, builds, egress and tax | **$17** |
| Production provider allowance | Gemini and Modal combined | $1.90 |
| Local provider allowance | Separate local ledger | $0.85 |
| Fixed hosting plus provider allowances | Before other fees | **$19.75** |

[Render pricing](https://render.com/pricing). These allowances reserve $0.075 before each Gemini request and $0.01 before each Modal call. Concurrent reservations serialize in PostgreSQL. Confirmed Gemini responses settle against their reported input, output and thinking tokens; definite preflight or HTTP rejections release their holds. Unknown outcomes and Modal calls retain conservative exposure. Both original reservations and their settlements are append-only. New AI requests stop when their instance's allowance is exhausted, while existing footage remains available. The two configured instance allowances sum to $2.75; new instances must not be added without reallocating this total.

**This is not an enforceable $20 total invoice cap.** Render has no project-level total-spend stop covering fixed resources, egress, builds and taxes. The application allowance combines token-priced Gemini usage with outstanding conservative holds; it is not an invoice. Direct provider calls outside RUSHES are excluded. No account-wide billing limit was changed because other projects share the accounts. Rate changes require reviewing reservations. [Modal pricing](https://modal.com/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

RUSHES’s Google project `gen-lang-client-0912851229` (`50426910677`) was initially unlinked and returned HTTP 429 with zero free-tier Pro quota. It is now linked to the existing personal paid billing account, with Tier 1 access and a **$2.75 Gemini project spend cap** verified in AI Studio. Google labels this cap experimental and warns of roughly ten-minute enforcement latency. The application still caps combined Gemini/Modal reservations separately; the Google cap is an extra backstop, not a combined invoice guarantee. No new payment method, prepayment purchase or other project setting was changed. To undo the link, use this project’s Linked account page; disabling its billing would stop paid Gemini processing.

Read-only billing inspection on 12 September found $2.17 accrued for RUSHES's Render service/disk/database, within the shared account's $3.24 total. Build usage was 25/500 included minutes and bandwidth 336 MB/5 GB. Modal's personal workspace showed $1.01 usage offset by included credits, $0 billed, and $28.99 credit balance; the RUSHES app page showed $0.02 usage. These are scoped observations, not future guarantees or the other projects' budgets.

## Resource organization

- Dedicated Render project `prj-dahh47mk1f9s73f99g70`, production environment `evm-dahh47mk1f9s73f99g7g`.
- Web service `srv-dahk822d0e5s73fo22o0`; private repository [ryouol/rushes](https://github.com/ryouol/rushes), branch `codex/production`; one instance and automatic deployments disabled.
- Postgres `dpg-dahk1qek1f9s73fk9n5g-a`; schema `0008`; distinct application, Temporal and visibility databases. External access and storage growth remain disabled.
- Private Modal app [rushes-compute](https://modal.com/apps/royluo05/rushes-production/deployed/rushes-compute), environment `rushes-production`. Both functions scale to zero, cap at one container each, and request/limit one CPU and 2 GiB, with 60-second startup and 120-second execution bounds. [Resource evidence](validation/modal-resource-limits.json).
- Wayline and UNRENDER resources were not changed. Modal environment separation organizes this app within the existing workspace; it is not a separate credential or billing boundary.

## Current validation

The budget repair completed all 14 user uploads in production and all nine local assets. Eight production jobs resumed their original checkpoints; one reused its retained response after the timestamp fix, and one uncertain older run received a separately tracked Pro analysis. Two older local partial assets also received new Pro analysis. Original uncertain histories and their spending holds remain intact. The final production driving search returned the car at 0–11.451667 seconds. After recovery and that search, accounted usage plus holds was $1.483716/$1.90 in production and $0.459891/$0.85 locally. All 23 original-file hashes matched. Peak cgroup memory reached 512 MiB during recovery and operator checks, with 829 limit/reclaim events and no OOM or killed process; this does not establish bulk capacity. [Budget accounting, recovery and review evidence](validation/budget-repair.json).

Runtime `0a11071` is deployed on Render; Modal was updated first with the compatible optional relevance argument. New analysis uses **Gemini 3.1 Pro Preview with LOW thinking**, a 10,000-input-token preflight and 4,096-output-token ceiling. Existing runs retain their original model and raw evidence. The worklog prompt now asks for separate visual events and spoken concepts, tight event intervals, and simultaneous searchable concepts such as car, driving and ocean when supported by the footage.

Search shows immediate text matches, then semantic results with cross-encoder relevance ranking. It retrieves at most 60 candidate observations, processes them in batches of at most 32, excludes low relevance evidence, and merges only identical intervals. Query and ranking computations are reused for ten minutes, including work that finishes after a client timeout. New notes and corrections still query fresh database evidence. Cold cloud startup can delay semantic refinement; local pilot repeat queries took about 20 milliseconds. This is a small footage check, not a representative accuracy benchmark.

[CI](https://github.com/ryouol/rushes/actions/runs/34725046825) passed: **318 backend tests, 27 browser regressions, lint, type checking and the production build**; two opt-in checks were skipped. The budget repair also passed 35 focused isolated regressions with paid calls disabled, plus fresh-schema verification. [All 22 findings and dispositions](SEARCH-REPAIR-REVIEW.md).

A current production Pro analysis completed the existing 12-second synthetic source in **21.86 seconds** after billing was linked. The cloud search check returned the blue screen at **5–12 seconds**, excluded an unrelated elephant query, and measured 0.17 seconds for initial text matches, 9.24 seconds for first semantic refinement and under 0.1 seconds for repeat queries. Actual runtime inspection confirmed Pro/LOW, Modal, 512 MiB/0.5 CPU and no OOM events. The remaining production browser journey also passed: collection adjustment, XML, JSON and CSV export, mobile layout and logout. [Current evidence](validation/search-repair.json).

The static frontend passed 141 isolated backend regressions and 27 local browser regressions. A frozen-source 512 MiB/0.5 CPU container passed 4K synthetic upload, interrupted preparation, same-job recovery, source/session preservation and supervisor failure checks. Three short muted derivatives preserving actual uploaded video streams also prepared successfully. A basic two-second, 1 fps, flat-color 8K fixture passed with a 502,222,848-byte peak. These are scoped functional checks, not representative long-footage, high-complexity 8K, or concurrent-user capacity claims. [All twenty static frontend review findings](STATIC-FRONTEND-REVIEW.md), [validation and cleanup](validation/static-frontend.json).

All seven original local MOVs now have ready worklogs and AI categories, and their SHA-256 hashes still match. Processing used seven new Gemini calls. One result rounded 14.006667 seconds to 14.007; a bounded fix refined the playable end while retaining the original proposal and raw response. The saved response was recovered into the same job without another generation or duplicate measured usage. Fifty-seven targeted regressions passed. [Review and every finding](BOUNDARY-ROUNDING-REVIEW.md).

## Existing verified behavior and boundaries

- Google connection and returning Google-only sign-in passed locally and in production at `83d8758`, including an existing password account without a workspace. Fresh Google signup has provider-contract test coverage, not live qualification. [Account evidence](validation/production-google-deployment.json).
- Earlier production checks verified secure HttpOnly SameSite=Strict sessions, origin rejection and resistance to rotating forged client-IP headers. [Ingress evidence](validation/render-ingress.json).
- The historical full paid browser journey passed on `2cb0774`: signup, upload, Gemini/Modal processing, playback, corrections, collections, rendered export, search, notes, selection data, FCP7 XML, mobile settings and logout. [Historical browser evidence](validation/render-browser.json).
- An earlier controlled restart retained the session, asset, correction and preview bytes, and a new original-copy export exactly matched the uploaded source. [Restart evidence](validation/render-restart.json).

Generation is dispatched once; uncertain outcomes are never automatically repeated. Only idempotent provider file-status reads have bounded retries. Unknown file expiry and failed remote cleanup stay recorded, with delayed retries. [Provider cleanup review](PROVIDER-CLEANUP-REVIEW.md).

Runtime credentials exclude the migration owner. Application access uses forced tenant rules and cannot change spending history or access the workflow databases. Internal Render database connections use the private same-region network without TLS; external bootstrap used certificate-verified TLS. Temporal Server 1.31.2 listens on loopback and retains three days of workflow history. A persistent media disk causes brief downtime during deployments.

Uploads are limited to 1 GiB per file and one hour of duration, with a 2 GiB free-space reserve. All cloud workspaces share the 10 GB media disk. New workspaces receive 60 internal credits and a maximum of 20 credits per analysis request. These are processing allowances; Stripe/payment collection is outside scope.

## Remaining qualification and operator input

The low-cost instance is qualified only for the stated short inputs. The September accounting repair reconciled eleven production and seven local historical holds using retained provider responses, without resetting history or increasing allowances. Before recovering blocked footage, accounted exposure fell from $1.90 to $1.252130 in production and from $0.84 to $0.434819 locally. See [budget repair and recovery evidence](validation/budget-repair.json) and [all review findings](BUDGET-REPAIR-REVIEW.md). The $20 combined monthly target does not support unlimited long or bulk Pro analysis. Representative multi-hour retrieval evaluation, human-labeled semantic accuracy, concurrent-user capacity and actual editor round trips remain incomplete. Editor interchange is experimental. Legal/operator copy remains a draft: contact details and legal entity are not configured. A hard total invoice cap remains unavailable on the current providers.

Private credentials, QA sessions and backups remain ignored under `.local/` or `.env`. The local database and seven originals survived the earlier disk-pressure incident; [recovery evidence](validation/disk-recovery-20260912.json) records the backup and hash checks. No original media or unrelated project resources were removed.

Earlier review records remain available: [initial production](PRODUCTION-REVIEW.md), [supervisor](SUPERVISOR-REVIEW.md), [shared runtime](SHARED-RUNTIME-REVIEW.md). No GitHub PR exists and no review comments were posted.
