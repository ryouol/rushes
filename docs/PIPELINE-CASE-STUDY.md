# Upload to searchable footage: measurement and checkpoint recovery

This study measures RUSHES ingestion, preprocessing, real local faster-whisper transcription, FastEmbed indexing, hybrid retrieval, and a separate clip export. The fixed corpus is 205 seconds of synthetic video and speech. Gemini visual analysis is deliberately disabled; assets finish **partial but speech-searchable**, not fully visually analyzed. This is a pipeline scheduling and durability experiment, not a representative camera-footage capacity or semantic-quality benchmark.

## Measurement contract

Three fixed, hashed fixtures use FFmpeg `testsrc2` at 24 fps plus macOS Samantha synthetic speech: 15 seconds at 640×360 H.264, 65 seconds at 1280×720 H.264, and 125 seconds at 1920×1080 HEVC. Each run uploads all three into a fresh project. Five fixed queries run five times each. The export is a separate 1–4 second selection from the HEVC source. [Fixture manifest](validation/pipeline/fixtures.json).

The processing worker runs in the existing Debian amd64 RUSHES runtime under emulation on an arm64 Mac. Every controlled worker has **2 CPU / 2 GiB** limits, two FFmpeg/model threads, and one inference activity slot. Baseline media concurrency is one; the candidate is two. Model weights are already downloaded, but every run starts a new worker and new asset/checkpoint directories. “Cold” here excludes dependency/weight download. The API and PostgreSQL remain on the same development host; their memory and CPU are not included in the worker cap or reported container peak. The results do not qualify the production 0.5-CPU/512-MiB host, which uses remote model compute.

Time-to-searchable starts before uploading each file and ends when the API reports its completed processing state after indexing. Polling is at 100 ms; files are inspected in submission order, so these are client-observed upper bounds. Corpus throughput is total media seconds divided by elapsed corpus seconds; it is not the sum of per-file throughput. Search measurements include query embedding, SQL retrieval and reranking; the first query pass and cache hits are retained together. Export wall time includes its independent dispatch delay. Nearest-rank p50/p95 is used; 25 requests and two repetitions are small samples, not a load-test SLA.

## Correlation and profiling

A validated W3C `traceparent` provides request correlation. Upload and export jobs persist that carrier. Dispatch spans additionally expose the database-outbox delay before starting Temporal. An activity interceptor creates a fresh span for every actual attempt, including logical job ID, workflow/run ID, activity ID and attempt number. It records current-attempt schedule-to-start wait separately from monotonic activity execution. The original schedule-to-start field additionally includes elapsed time across retries and must not be called queue wait. Child batch jobs retain their own saved upload context. Spans cover media substeps, transcription calls, embeddings, retrieval and export; they contain no queries, transcript text, credentials or media paths.

Trace writes occur in API code and activity execution, never in workflow code. Completed history is replayed through the SDK replayer as a separate check. A killed attempt has a start record without an end record; the collector does not invent a successful duration. Trace-sink failure cannot turn committed work into a retry. Production uses structured `rushes.trace` log lines; an optional `RUSHES_TRACE_FILE` writes private JSONL for isolated collection. Operators own retention/rotation.

[Full correlated trace](validation/pipeline/full-trace.jsonl), [Python py-spy profile](validation/pipeline/python-profile.json), and [actual retrieval query plans](validation/pipeline/query-plans.json) are retained. The py-spy diagnostic collected 68 active Python samples over 20 seconds at a requested 50 Hz, with zero sampling errors. It identifies Python stacks, including Whisper generation/encoding and executor work; it is not a profile of independent FFmpeg processes or an exhaustive native CPU attribution. Linux `/proc` RSS and cgroup memory were sampled separately at approximately 50 ms. Peaks are sampled lower bounds and include the memory sampler in the container total. Database plans use the runtime tenant role and `EXPLAIN (ANALYZE, BUFFERS)` on the actual retrieval statements; this tiny corpus cannot establish large-index scaling.

## Controlled scheduling change

The single media slot serializes expensive preparation and transcription, while light planning/completion activities also wait for that queue. Stage totals and queue wait must be read separately; concurrent activity execution durations overlap and must not be added to calculate wall time. Raising media slots allows overlap and reduces the time shorter uploads spend behind long activities, at a memory cost. Local transcription calls consume the shared Whisper generator under a process lock; preparation can still overlap transcription. The production default remains **one slot**. The two-slot setting is an operator-controlled option for separately qualified resources, not a new 512-MiB production recommendation.

| Run | Searchable: 15 / 65 / 125 s files (s) | Corpus (s) | Media min / wall min | Container peak (MiB) | Query p50 / p95 (ms) | Export wall / activity (s) |
| --- | --- | ---: | ---: | ---: | --- | --- |
| baseline-1 | 161.05 / 162.73 / 162.64 | 162.87 | 1.259 | 971.6 | 29.6 / 219.8 | 5.35 / 2.92 |
| baseline-2 | 163.65 / 163.60 / 164.56 | 164.76 | 1.244 | 1011.3 | 30.5 / 245.3 | 5.40 / 2.95 |
| candidate-3 | 134.55 / 135.90 / 163.02 | 163.26 | 1.256 | 1109.5 | 26.6 / 230.3 | 4.70 / 3.21 |
| candidate-4 | 133.48 / 134.59 / 160.03 | 160.25 | 1.279 | 1146.2 | 33.9 / 246.6 | 4.46 / 3.45 |

| Run | Prepare execution (s) | Transcribe execution (s) | Index execution (s) | Sum of activity queue waits (s) |
| --- | ---: | ---: | ---: | ---: |
| baseline-1 | 74.43 | 80.60 | 2.54 | 312.83 |
| baseline-2 | 73.63 | 83.02 | 2.66 | 316.30 |
| candidate-3 | 132.22 | 153.54 | 4.05 | 127.55 |
| candidate-4 | 129.40 | 152.11 | 3.88 | 126.41 |

The final candidate reduced mean client-observed latency for the 15-second and 65-second files by **17.5%** and **17.1%**, respectively. Mean corpus time changed from **163.82 to 161.75 seconds** (1.3%); that small difference does not establish a durable total-throughput improvement. All 25 searches per run returned hybrid results, with no activity retries during cold runs. Individual FFmpeg sampled peak RSS stayed around 171 MiB. Export activity time remained approximately three seconds; no faster-export claim is made.

[All measurements and exploratory runs](validation/pipeline/measurements.json). Queue sums represent waiting across three jobs, not additional elapsed corpus time. Activity execution also includes I/O and waiting for the local model lock; neither table is a CPU profile. All six synthetic exports have the same SHA-256 and size (5,124,559 bytes). [Frame/audio/source verification](validation/pipeline/fidelity.json).

The two exploratory two-slot runs are also retained in the evidence, but the final comparison uses the two runs with serialized access to the shared local transcription model. Repeated single-slot baselines themselves produced different segmentation on the repetitive long synthetic speech. We therefore do not attribute that ASR variability to concurrency or claim byte-identical transcripts. The evidence records normalized transcript hashes and segment counts, validates every segment against source-time bounds, and keeps the fixed hybrid-search outcomes. Source/audio preparation, transcription window boundaries, model and decoding settings remain unchanged. The synthetic exports are compared by bytes; VFR, rotation, delayed audio, subframe timing and original-preservation regressions separately exercise the existing renderer.

## Crash after a completed checkpoint

The isolated worker was killed with SIGKILL immediately after the second 60-second transcription call started. The first 60-second transcript file and its database usage checkpoint already existed. The same container was restarted against the unchanged Temporal and application databases.

- Container restart command completed **0.39 seconds** after the kill.
- The retry activity began **98.79 seconds** after the kill; the remaining heartbeat timeout/backoff dominated the delay.
- The asset became speech-searchable **133.02 seconds** after the kill.
- **0 completed media minutes were recomputed.** The first transcript and preprocessing manifest retained identical hashes; preparation was not repeated.
- **1 in-flight media minute was reissued**: the interrupted second window. This is the duration submitted again, not a claim that a whole minute had already been computed before SIGKILL.
- Four local transcription invocations produced three successful windows. There were **0 duplicate completed windows** and **0 paid-provider requests**.
- The database contains one source-usage record and three transcription records totaling exactly 125 seconds. Every recovered observation has an embedding.

[Recovery measurements](validation/pipeline/recovery.json) and [attempt-level trace](validation/pipeline/recovery-trace.jsonl) retain the evidence. Cold ingestion timings above are separate from this post-crash recovery interval.

This measures actual local transcription invocations. It does not demonstrate exactly-once behavior at a paid external provider: Gemini is disabled and no paid request is sent. A completed local checkpoint is reused; the in-flight unit can be reissued. A lost external response remains a separate uncertainty, handled by the existing provider accounting and ambiguous-outcome policy.

## Export-memory result remains narrowly scoped

The prior **38% lower FFmpeg peak RSS** comparison remains exactly the workload in the [export memory incident report](EXPORT-MEMORY-REVIEW.md): a three-second portrait selection from synthetic 1080p60 10-bit HEVC with audio, Debian amd64 under emulation, 512 MiB / 0.5 CPU and 220 MiB Python ballast. RSS changed from 301,322,240 to 187,277,312 bytes; elapsed times were 24.22 and 24.80 seconds. It did **not** establish faster exports. The low-buffering encoder recipe trades compression efficiency for reduced memory; CRF 18 does not promise identical encoded quality or size. This study changes neither that recipe nor its renderer version.

## Reproduce

After normal local database setup and downloading the local model weights, generate the fixtures once and retain their manifest/checksums. Use a compatible pinned RUSHES runtime image. The controller refuses occupied ports, creates a disposable database, owns its API/Temporal processes and labeled container, and removes those resources at exit. Evidence and synthetic files remain in the private output directory. Run only on the local development host with sufficient disk space.

```sh
uv run python scripts/pipeline_fixtures.py
uv run python scripts/run_pipeline_study.py \
  --image rushes:supervisor-check \
  --fixtures .local/pipeline-study/fixtures \
  --output .local/pipeline-repeat --runs 2
```

The image tag identifies the measured local image; [environment evidence](validation/pipeline/environment.json) records its immutable image ID. Tags are not a substitute for checking that ID. The fixture generator uses macOS `say`; another platform should use the saved corpus, not silently substitute a different speech signal. No binaries or model weights are committed.

For a separate diagnostic profiling run, install py-spy inside a disposable worker, grant that container `SYS_PTRACE` with its seccomp restriction removed, and run `py-spy record --pid 1 --duration 20 --rate 50 --format speedscope -o PROFILE.json`. Exclude installation from timings. macOS attachment without elevated privileges was unavailable in this session; the recorded profile came from the isolated Linux container. `scripts/sample_pipeline_memory.py` must run **inside** the measured Linux container. `scripts/explain_pipeline_search.py` executes plans only against an isolated synthetic project. `scripts/summarize_pipeline_study.py` aggregates activity spans without double-counting nested media spans.

## Validation

- 325 backend tests passed, one opt-in Temporal test skipped; the isolated real-worker experiment and SDK history replay were run separately.
- All five FFmpeg media regressions passed, including VFR/source-PTS selection, rotation, delayed audio, rational rates and original preservation.
- Nineteen focused telemetry, worker-lifecycle, concurrency and measurement tests passed after adding dispatch timing.
- Six synthetic exports each contain 72 frames with expected 24-fps source-relative timestamps, 1920×1080 dimensions, audio and zero audio/video start offset. All original upload hashes are unchanged.
- The replay-only trace sink remains absent after replaying a completed ingestion history, demonstrating no telemetry writes from workflow replay.
- Python lint and the local credential audit passed. Deployment and CI are verified against the pushed revision after commit.

The long repetitive speech fixture produced 29–32 transcript segments across runs, including different single-slot baselines. This study validates preserved timing bounds and retrieval availability, not identical stochastic ASR segmentation, labeled word-error rate or comprehensive semantic correctness. The source-time renderer regressions remain the stronger timing evidence.
