# Development

Use the [README quick start](../README.md#run-locally) for a fresh checkout. Setup needs Python 3.12/3.13, uv, Node 22+, Docker Compose, FFmpeg, and ffprobe. Whisper and FastEmbed download public weights on first use. The default local speech model is `tiny` with CPU int8 inference.

## Configuration

Run `uv run python scripts/configure.py` to generate a private `.env` with random development credentials. It uses mode 0600 and preserves an existing file. [`.env.example`](../.env.example) is the checked-in reference; never replace generated credentials with a shared password.

| Setting | Purpose |
| --- | --- |
| `RUSHES_GEMINI_API_KEY` | Required for visual analysis; keep server-side. Previews and transcription can run without it. |
| `RUSHES_GEMINI_MODEL` | Defaults to `gemini-3.1-pro-preview`; `gemini-3.6-flash` is also supported. See [config.py](../backend/rushes/config.py) for the supported set and thinking levels. |
| `RUSHES_ANALYSIS_WINDOW_SECONDS` | Defaults to 20 seconds; combined inputs are token-counted and bounded before generation. |
| `RUSHES_COMPUTE_BACKEND` | `local` or private `modal` RPCs for speech and embeddings. |
| `RUSHES_SOURCE_ROOTS` | JSON array of explicit, absolute source directories. Empty by default. |
| `RUSHES_STORAGE_ROOT` / `RUSHES_OUTPUT_ROOT` | Separate working and export directories; must not overlap source roots. |
| `RUSHES_DATABASE_URL` / `RUSHES_ADMIN_DATABASE_URL` | Separate runtime and migration credentials. Do not deploy the migration owner as the API role. |
| `RUSHES_GOOGLE_CLIENT_ID` / `RUSHES_GOOGLE_CLIENT_SECRET` | Optional OAuth configuration. Register the exact callback for your origin; see [Google authentication](GOOGLE-AUTH.md). |
| `RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD` | Application-side provider accounting allowance, in millionths of a US dollar. Use `0` to disable new paid dispatch during tests. This is not a total hosting invoice cap. |
| `RUSHES_LOCAL_CREDITS` / `RUSHES_MAX_ANALYSIS_CREDITS` | Development workspace grant and per-analysis allowance; no payment is collected. |
| `RUSHES_MIN_FREE_BYTES` | Working disk reserve; defaults to 2 GiB. |

Restart the app after changing server configuration. Origin, public contact/legal values, and the analytics identifier are embedded in exported pages, so production-style startup also requires a fresh `uv run python scripts/build_web.py`. The server checks the exported public configuration at startup. Private credentials are not part of that manifest.

## Processes and storage

| Port | Local purpose |
| --- | --- |
| 3741 | Public application origin |
| 55432 | PostgreSQL, bound to loopback |
| 7233 | Temporal |
| 8233 | Local Temporal UI |
| 8741 | Development-only API behind the frontend server |

`scripts/dev.py` refuses occupied ports. Ctrl-C stops only the launcher's child processes; the database volume remains. Logs are in `.local/logs`. Production-style local startup serves the exported frontend from Python without a Node server.

The API and processing worker must share the storage referenced by database paths. Back up PostgreSQL, Temporal state, originals, and working/export storage together. Do not delete a database volume to resolve a setup failure.

Uploads copy into managed storage. Directory indexing references allowlisted originals without renaming them. Changing storage roots does not migrate recorded paths. A source with changed bytes needs a new import; relinking requires the expected hash. Interrupted uploads need reselection, while completed imports continue through durable processing after the browser closes.

## Verification

### Backend and frontend build

Run after the local database is healthy and migrations are applied:

```sh
uv run ruff check backend scripts deploy tests
RUSHES_GEMINI_API_KEY= RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD=0 uv run pytest -q -m "not provider"
uv run python scripts/build_web.py
npm --prefix web run typecheck
uv run python scripts/audit_local.py
```

The audit scans tracked/unignored source and client bundles for configured secret values and credential shapes. It reports names and locations, never credential values; it is not a proof that every possible secret is absent.

### Browser regressions

Start the local app separately. The focused regression suites stub API responses and do not need real Google credentials or paid model calls:

```sh
cd web
npx playwright install chromium
npx playwright test e2e/auth.spec.ts e2e/state-regressions.spec.ts --workers=1
```

The full `npm run test:e2e` includes integration journeys that need a prepared local runtime. Use an isolated development database and synthetic media, not a production account. [CI](../.github/workflows/ci.yml) shows the reproducible isolated setup.

### Opt-in integration checks

`scripts/verify_schema.py` creates and removes a disposable database using the migration role. Temporal integration uses `RUSHES_TEST_TEMPORAL=1` and requires the configured runtime. `scripts/create_fixture.py` uses macOS `say`; media tests also generate portable FFmpeg fixtures.

Live Gemini tests require explicit provider configuration and may cost money. Do not enable `RUSHES_TEST_LIVE_GEMINI=1` or provider diagnostics in an ordinary review run. Disabling the shell's key does not reconfigure an already-running worker; restart that worker with the intended settings before a live integration test.

Recovery and load scripts deliberately interrupt selected services or generate media. Read their arguments and documented fixture assumptions before running them; the historical throughput records are not representative-camera benchmarks.

## Troubleshooting

- **Visual analysis is incomplete:** confirm a server-side key, supported model, and available provider allowance; inspect the recorded job error before requesting new analysis.
- **Startup reports a configuration mismatch:** rebuild through `scripts/build_web.py` with the same public values used at runtime.
- **Port occupied:** stop the intended RUSHES launcher or use its existing instance. Do not kill unrelated processes.
- **Not enough storage:** use the app's deletion controls for footage you intend to remove; retain originals and backups. Model caches, previews, and exports also consume space.
- **Media works locally but not remotely:** ensure the worker can access the same managed storage and that source roots are valid for the host.
