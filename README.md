# RUSHES

A working local footage library, persistent worklog, search workspace, and clip exporter. This is a **local release candidate with explicit verification gaps**, not a completed production release. Gemini analysis sends derived clips and transcript context to Google; local-first does not mean fully offline.

**RUSHES is live at [rushes.onrender.com](https://rushes.onrender.com).** Render hosts the web/API, durable workflows and media; private Modal functions handle speech and embeddings. The $20/month budget is a soft target: this lean configuration is approximately $35/month fixed, with a separate $2 monthly provider-call allowance. See [deployment status and verification](docs/PRODUCTION.md) and [the numbered review record](docs/PRODUCTION-REVIEW.md).

## Start locally

Tested on Apple M1 Pro, 16 GiB RAM, macOS, Node 22.23.2, Python 3.12.12, Docker, and FFmpeg/ffprobe 8.0.1. Requires `uv`, Node 22+, Docker Compose, FFmpeg/ffprobe, and a supported Python 3.12/3.13. The local transcription backend uses CPU int8, two threads, and the tiny Whisper model. Whisper and FastEmbed download public model weights on first use. Allow several GB for dependencies/models **plus footage, proxies, and exports**; the default working-disk floor is 2 GiB.

From this repository:

```sh
uv sync --locked
uv run python scripts/configure.py

docker compose up -d
# Wait for `docker compose ps` to show PostgreSQL healthy.
uv run python scripts/bootstrap_db.py
uv run python scripts/setup_temporal.py
npm --prefix web ci
uv run python scripts/reindex.py
uv run python scripts/dev.py
```

Open [RUSHES](http://localhost:3741). Create an account, workspace, and project. No seeded login or shared password is provided. Local workspaces receive an explicit development-credit grant; no money is collected.

`configure.py` creates `.env` once with private generated credentials and mode 0600; it preserves an existing file. The PostgreSQL service is isolated on **55432**. RUSHES uses API **8741**, web **3741**, Temporal **7233**, and the local Temporal UI **8233**, all bound to loopback. The launcher refuses occupied service ports and stops only its own children on Ctrl-C. Logs are under `.local/logs`. PostgreSQL remains running with its persistent Docker volume.

For the production build:

```sh
npm --prefix web run build
uv run python scripts/dev.py --production
```

The API and worker must share this machine's storage. Do not run the worker remotely against these local path references. Keep `.local/temporal.db`, the PostgreSQL volume, uploaded originals, and working storage together when backing up. A database-only restore does not restore media. Do not delete the database volume to fix a setup problem.

## Configuration

See `.env.example`. Set server values in the private `.env`, then restart the API and worker.

| Variable | Purpose |
| --- | --- |
| `RUSHES_GEMINI_MODEL` | Only `gemini-3.6-flash` is supported by the bounded analyzer configuration; other models fail validation before upload. |
| `RUSHES_GEMINI_API_KEY` | Optional for local previews/transcription; required for visual analysis. Never put it in a browser/public variable. |
| `RUSHES_ANALYSIS_WINDOW_SECONDS` | Default 20 seconds. Combined video/transcript content is counted and rejected above 10,000 tokens before generation. Live synthetic counting has passed. |
| `RUSHES_COMPUTE_BACKEND` | `local` (default) or private `modal` speech and embeddings; Modal mode requires authenticated SDK credentials. |
| `RUSHES_MODAL_ENVIRONMENT` | Dedicated Modal environment, default `rushes-production`. Never change the account default or another project’s environment. |
| `RUSHES_SOURCE_ROOTS` | JSON list of explicit absolute, non-overlapping source folders, e.g. `["/Volumes/Footage/Shoot"]`. Empty by default. |
| `RUSHES_STORAGE_ROOT` / `RUSHES_OUTPUT_ROOT` | Separate private working and export directories. Neither may overlap a source root. |
| `RUSHES_DATABASE_URL` / `RUSHES_ADMIN_DATABASE_URL` | Generated runtime and migration credentials. Runtime is not a table owner and cannot bypass RLS. |
| `RUSHES_TRANSCRIPTION_MODEL` | Whisper model. Modal mode is pinned to `tiny`; larger local models need measured hardware capacity. |
| `RUSHES_EMBEDDING_MODEL` | Text model; Modal mode is pinned to `BAAI/bge-small-en-v1.5`. After changing it, run `scripts/reindex.py` to create a model/dimension-specific index and queue durable re-embedding. |
| `RUSHES_LOCAL_CREDITS` / `RUSHES_MAX_ANALYSIS_CREDITS` | Initial development grant and per-analysis spending cap. Defaults: 600 / 120 credits. |
| `RUSHES_CREDITS_PER_MINUTE` | Configurable footage-minute rate; defaults to one credit per minute. No cost/margin claim. |
| `RUSHES_MIN_FREE_BYTES` | Disk reserve; default 2 GiB. |

Changing storage roots does not migrate existing paths. Keep existing storage available or back it up and perform an explicit migration. Removing an indexed source root revokes reads on the next configured service run; managed uploads remain scoped to their workspace and asset. Changing a source's contents requires a new import; relinking accepts only matching SHA-256 bytes. File-picker uploads copy into private storage; indexing references originals without moving or renaming them. Interrupted uploads require reselection. Completed imports continue after the browser closes.

## Demonstration

1. Create a workspace and project; choose **Import footage**. Use files/folders, or index selected files from a configured source root.
2. Open a source when its preview appears. Speech and configured visual analysis populate the worklog. Without a Gemini key, processing ends **partial**, with previews and any transcript usable.
3. Click worklog timestamps to seek. Edit an observation and inspect its history. Mark in/out with **I/O** or numeric elapsed seconds; use **J/K/L** for transport. Add a manual note if needed.
4. Search a phrase or visual description. Results link to recorded evidence and bounded source intervals. Save a query or create a collection and request suggested ranges; review before adding.
5. Adjust collection ranges. Preview and start a clip export or a full-source organized copy. Download completed outputs or open the separate local output folder. Selection JSON/CSV, worklog JSON/CSV, and experimental XML formats are available.
6. Inspect **Settings & usage** for storage, service status, credit ledger, and owner-managed access to existing local accounts. Review an explicit estimate before new visual analysis.

## Verification

```sh
uv run ruff check backend scripts tests
uv run pytest -q
# With the local API/Temporal/worker running and synthetic fixture present:
uv run python scripts/create_fixture.py
# For selected-root integration, allowlist .local/fixtures in RUSHES_SOURCE_ROOTS
# and restart API/worker with the same configuration first.
RUSHES_TEST_TEMPORAL=1 uv run pytest tests/test_temporal.py -q
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e
npm --prefix web run build
uv run python scripts/audit_local.py
uv run python scripts/verify_schema.py
```

Tests create clearly labeled synthetic accounts/workspaces and private test artifacts. Browser tests default to a development instance with Gemini disabled and assert the honest partial state. The opt-in `RUSHES_TEST_LIVE_GEMINI=1` expects complete visual analysis and makes paid provider calls when the worker is configured with a real key. `create_fixture.py` uses macOS `say`; portable FFmpeg-only fixtures are generated by the media tests.

Pre-review recorded evidence is under `docs/validation` (throughput was not re-benchmarked after the final fixes): 50 synthetic files / ten source hours at 160×90 processed in 168.03 seconds; all originals preserved; no Gemini requests or customer debits. This highly compressible, muted fixture is **not representative camera-footage throughput or retrieval evaluation**. A separate in-flight worker kill plus persistent Temporal restart recovered a five-minute 1080p synthetic source in 140.5 seconds and isolated a corrupt file; source usage was recorded once.

The recovery harness requires explicit PIDs and interrupts only the selected RUSHES services:

```sh
uv run python scripts/verify_recovery.py --worker-pid <RUSHES_WORKER_PID> --temporal-pid <RUSHES_TEMPORAL_PID>
```

Do not run it against unrelated services or while using the instance for real work. It leaves replacement RUSHES services running and records their PIDs in `.local/recovery/services.json`.

## Accuracy and release gaps

- Intervals are half-open source elapsed microseconds. Original frame PTS, rational time bases, source start timecode where supplied, and explicit proxy mappings are retained. Export selects decoded source frames whose presentation starts fall inside the interval; a final frame can extend beyond the requested out point.
- Browser seeking, model localization, scene detection, and transcription are approximate. Human review remains necessary. A fixed-rate proxy is never used to infer VFR source frame indices.
- Clips are re-encoded H.264/AAC from the original; only the first video/audio stream is supported. This is not archival mastering, multichannel audio preservation, HDR/color-managed finishing, or a claim of bit-identical export. Organized copies are byte-for-byte originals.
- FCP7 XML and FCPXML are experimental straight-cut exports for shared-rate, unrotated CFR sources. Mixed rates, VFR and rotated sources require rendered clips. **No target editor is installed; a structural XML check is not a verified round trip.** EDL is N/A until a concrete need justifies its narrower format.
- Provider requests can succeed before a result is saved. In-flight requests with uncertain outcomes become **ambiguous** and are not automatically repeated. Received responses and usage commit before local validation; invalid output stays reviewable. Internal recovery retains the original billing operation and confirmed checkpoints, re-reserves only unused exposure, and charges only new confirmed coverage; new analysis uses a new reviewed estimate. This does not promise exactly-once provider execution or zero external charges.
- Search ranks bounded keyword and local embedding candidates. The distance cutoff is a heuristic, not a quality guarantee. **TODO: provide representative footage and a human-labeled query set**, separated by interview, B-roll, OCR, and mixed content.
- **Live Gemini:** the private key is configured. A bounded synthetic video passed upload, token counting, generation, interval validation and file deletion. A subsequent full browser run received HTTP 503 and safely ended partial without an automatic paid repeat. Representative semantic quality and a successful full hosted journey remain unverified. Physical chunks are the provisional implementation.
- **TODO: provide a supported target editor** for real interchange validation. **TODO: provide reviewed legal/operator/support information** before any hosted commercial release. Privacy/Terms pages clearly remain drafts.
- Optional WebMCP search is feature-detected; no supported browser registry was available for live contract verification. Ordinary browser search was verified.

The requested simplify and final review are recorded in [all numbered findings and dispositions](docs/REVIEW.md). The remaining review-process limitation is the size of this initial application snapshot; the report provides a concrete staged landing plan.

See [the phase checklist](docs/IMPLEMENTATION.md), [decisions](docs/DECISIONS.md), and [security inventory](docs/validation/security-inventory.json). The hosted Render/Modal deployment and its soft budget target are documented in [production status](docs/PRODUCTION.md). [Container operation](docs/HOSTING.md) covers the web/API entrypoint. Stripe and payment collection remain deferred by scope; editor round trips and production-scale qualification remain unverified.
