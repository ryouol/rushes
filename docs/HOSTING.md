# Container preparation

The image packages the Next.js web server, FastAPI API, RUSHES worker and pinned Temporal Server 1.31.2. It is deployed as the Render RUSHES service, with private Modal compute. [PRODUCTION.md](PRODUCTION.md) records the soft $20/month target, the stated $35 lean hosting estimate, provider allowance, and hosted verification results.

## Build and runtime

```sh
docker build --platform linux/amd64 -t rushes:hosting-candidate .
```

The build uses locked Python/npm dependencies and excludes private configuration, local media and Git files from the context. The runtime uses UID 10001, has production dependencies and FFmpeg, and runs the public web server on `PORT` (default 10000). FastAPI binds only `127.0.0.1:8741` inside the container. Runtime configuration needs:

- `RUSHES_DATABASE_URL`: a reachable migrated PostgreSQL/pgvector database using the non-owner runtime role with tenant RLS. Supply administrative credentials only to a separate migration operation; the running image neither needs nor receives them.
- `RUSHES_SECRET`: private server secret, generated independently for the deployment.
- `RUSHES_ORIGIN`: the exact public HTTPS origin, without credentials, path, query or fragment.
- `RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD`: combined conservative Gemini/Modal request allowance, set to `2000000` for the initial deployment.
- `RUSHES_CLIENT_IP_HEADER`: either `x-rushes-ingress-client-ip` or `true-client-ip`, only after verifying that the trusted ingress overwrites it with a single validated client IP. The web server forwards a separately named internal header to its loopback API. Arbitrary client-supplied forwarding headers are not authoritative.
- Durable storage mounted at `/var/data`, writable by UID 10001. Originals/previews, exports and model caches have separate subdirectories. The private Modal functions receive bounded derived audio bytes and text; they never access the Render disk. FFmpeg, source storage and workflow orchestration must remain on the RUSHES host.

The web port must be reachable only through the trusted ingress. Otherwise a direct caller could forge its asserted client IP and bypass per-client authentication limits. The local harness uses its own Caddy ingress that overwrites the header. The actual Render True-Client-IP path was tested against rotating forged forwarding headers; see validation/render-ingress.json.

The default upload body limit is 20 GiB and the default duration limit is two hours, configurable by `RUSHES_MAX_UPLOAD_BYTES` and `RUSHES_UPLOAD_TIMEOUT_SECONDS` (1–86400 seconds). The Next custom HTTP server and API both enforce the duration. Slow uploads release database connections between initial authorization and final commit; the latter rechecks session, membership and project access. Failed/timed-out uploads do not publish an asset/job. These are technical limits, not affordable storage allocations or a spending cap. Provider ingress limits also need validation.

Set `RUSHES_HOST_WORKFLOW_SERVICE=true` for the combined host. Supply `RUSHES_TEMPORAL_DATABASE_URL` and `RUSHES_TEMPORAL_VISIBILITY_DATABASE_URL` for two additional, explicitly provisioned PostgreSQL databases. Their names and the application database name must be distinct and cannot contain percent encoding. Workflow roles may own their workflow databases but must not be superusers or bypass application RLS. Keep `RUSHES_TEMPORAL_ADDRESS=127.0.0.1:7233`; all Temporal RPC and membership ports bind loopback. The service uses no public Temporal endpoint.

Workflow URLs default to `sslmode=verify-full`; `sslrootcert=system` uses the image trust store, or supply an absolute mounted CA path. `sslmode=require` and `disable` are available for environments whose transport requirements explicitly call for them. Bootstrap schema separately using `python scripts/bootstrap_workflow_db.py` inside the image with these URLs. It checks schema initialization before applying matching pinned migrations and supports repeating the operation. Provision the databases first; the command does not create them.

`scripts/serve.py` starts Temporal, waits for the namespace and starts both processing queues, API and web. On termination the public/API/worker processes stop first, both worker queues drain concurrently, and then Temporal stops. A process crash stops its companions. Startup termination is observed during readiness. Without the host flag, it supplies only web/API and requires externally operated workflow infrastructure. The development launcher pins loopback ports and passes the validated root `.env` origin/duration to Node. Run local development as described in the README; never deploy its SQLite-backed Temporal development server as production.

## Disposable local verification

With the normal local database configured and Docker running:

```sh
uv run python scripts/verify_hosting.py
```

This creates a uniquely named test database, two test containers and one volume, then removes only those resources. It binds TLS on loopback port 3843, uses a temporary local CA without changing system trust, and writes its private runtime environment with mode 0600 before deleting it. It does not use Gemini, Modal or paid hosting.

The default check deliberately streams a synthetic video for 345 seconds, beyond Node's previous default upload timeout, then checks real FFmpeg preview generation, ranged playback, unchanged source hash, secure sessions, tenant isolation, static assets, forged-header rejection, private API isolation, shutdown with SSE and persisted session/media after restart. `--slow-upload-seconds 0` is a quick diagnostic and does not verify the long-upload boundary. Evidence is saved in [hosting-container.json](validation/hosting-container.json); logs and synthetic fixtures remain under `.local/hosting-qa`.

The preparation function is invoked directly inside the image for this test. It does not verify remote Temporal/Modal dispatch or representative semantic analysis. The separate workflow harness, `RUSHES_GEMINI_API_KEY= uv run python scripts/verify_workflow_hosting.py --image rushes:production-amd64`, exercises the built image with three disposable databases, verified PostgreSQL TLS, an interrupted activity, persisted workflow history, sessions/media and shutdown/crash cases. Verification helpers and a held FFmpeg fixture are mounted separately; production code and binaries come from the image. `--mount-source --image rushes:hosting-candidate` is an explicitly weaker development check requiring local matching binaries under `.local/temporal-server`. Evidence states whether source was mounted. It does not call paid providers or verify cleanup after FFmpeg writes partial output. Production remains blocked until actual ingress, capacity and authorized spending controls are implemented and tested.
