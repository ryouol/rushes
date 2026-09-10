Here’s a ready-to-paste Codex goal prompt. It combines both documents and corrects several risky assumptions around timestamps, retry billing, and local file access.

Implement **RUSHES**, a polished local-first web application that ingests large collections of video footage, produces a persistent timestamped worklog, and lets users search, organize, review, and export footage or clips.

Start from the repository’s actual state. If it is empty, build the application from scratch. If code exists, inspect and extend it. Carry the work through implementation and verification; do not stop at a plan, scaffold, or mock interface.

**Primary goal**

Deliver a working local application where a user can:

1. Sign up, log in, and create a workspace and project.
2. Import multiple videos or index an explicitly selected local directory.
3. Process hours of footage through durable background workflows.
4. Read and correct a timestamped worklog linked to playable source media.
5. Search across footage using natural language.
6. Organize source files and selected ranges into collections.
7. Preview, adjust, and export clips or organized copies.
8. Close the browser or restart services and resume completed work safely.
9. See processing progress, failures, and measured usage.

Local execution is the first release target. Gemini analysis may use its remote API. Do not describe the product as fully offline or claim that no media leaves the machine.

Implement secure foundations and polished UX throughout. Hosted deployment and live payment collection are future milestones, not prerequisites for the local release.

**Working decisions**

Use RUSHES as the working name.

Target independent editors and creators working with interviews, B-roll, and mixed shoots. Preserve editor-relevant timing and provenance while keeping ordinary folder organization simple.

Use:

- Next.js, TypeScript, Tailwind, and accessible UI components for the frontend.
- Python, FastAPI, Pydantic, SQLAlchemy, and Alembic for the backend.
- Temporal’s Python SDK for orchestration.
- PostgreSQL with pgvector for application data and retrieval.
- FFmpeg/ffprobe for media inspection, proxies, and exports.
- PySceneDetect for candidate shot boundaries.
- A locally executable transcription backend selected for the actual hardware.
- Gemini behind a typed analyzer interface.
- Local filesystem storage initially.

Choose compatible, maintained dependency versions after checking official documentation. Do not blindly copy versions, SDK examples, pricing, throughput claims, or limits from the planning documents.

Avoid unnecessary infrastructure. Add object storage only when a concrete requirement warrants it.

At the start, report the repository state, framework, styling approach, backend/database, local runtime requirements, and intended hosting boundary. Then proceed.

**Execution discipline**

Work in the phases below. After each phase, briefly report changed files, validation performed, and outstanding items with reasons.

Maintain a durable implementation checklist and decision log in the repository. Label requirements as implemented, needs input, deferred, or N/A. Deferred requirements are not completed requirements.

Make routine implementation decisions autonomously. Ask only for genuinely necessary credentials, inaccessible media, or consequential product choices that cannot reasonably be inferred.

Never print secrets. Never fabricate business information, legal terms, customer claims, analytics identifiers, or test results.

Prefer real functionality. Fixtures and mocks are allowed for isolated tests, but must not masquerade as successful processing in the application.

**Phase 0 — Establish the foundation and verify feasibility**

Inspect repository instructions and existing code. Before feature expansion, resolve exposed credentials, broken authentication gates, and unsafe existing endpoints.

For an empty repository, establish server-only secrets, validated configuration, migrations, and workspace ownership from the first implementation.

Build a small media-analysis vertical slice using the same core modules the final application will use:

- Inspect a video.
- Produce a lightweight proxy.
- Detect candidate shots.
- Transcribe available speech.
- Analyze bounded video windows.
- Persist structured observations with provenance.
- Seek to observations and export a selected range.

Avoid a throwaway parallel implementation.

Use supplied footage if available. Otherwise create clearly labeled synthetic timing fixtures for deterministic checks and request representative footage for semantic evaluation. Do not invent successful real-footage benchmarks.

**Timing correctness is a release requirement**

Deterministic media tools define the media timeline and render boundaries. Models propose meaning and approximate event locations.

Store:

- Rational frame rate where applicable.
- Original presentation timestamps and time base.
- Source start timecode and drop-frame metadata when available.
- Frame indices on explicitly identified constant-frame-rate timelines.
- Explicit source-to-proxy timing mappings.

Variable-frame-rate media cannot be mapped reliably by multiplying seconds by an average frame rate. A constant-frame-rate proxy does not erase the need to map back to the original.

Preserve the model’s proposed interval separately from any refined interval. Validate intervals against their analysis window and source duration.

Do not snap every event to a shot boundary. Speech, gestures, and visible text can occur inside a shot. Use detected cuts as evidence for shot-level boundaries and refine other events appropriately.

Do not claim that model descriptions, automatic shot detection, or a browser player provide guaranteed frame accuracy. Distinguish approximate semantic localization from deterministic export accuracy.

Use a consistent interval convention and test boundaries, long durations, rational rates, drop-frame formatting, rotation, missing audio, and variable-frame-rate inputs.

Exit this phase with a working slice and documented accuracy limitations.

**Phase 1 — Durable ingestion and the worklog**

Build bounded Temporal workflows for:

- Batch ingestion.
- Per-asset processing.
- Reanalysis with explicit model/prompt versions.
- Clip rendering and organization export.

Separate media-heavy work from inference work through task queues and concurrency limits. Ensure workers can access the artifacts their activities require; a local path is not automatically accessible to a remote worker.

Keep workflow code deterministic. Run filesystem, database, subprocess, and provider operations in activities.

Pass IDs and artifact references through workflow history, not media bytes or large transcripts.

Configure persistent local Temporal state, bounded histories, cancellation, retries, backoff, and Continue-As-New where appropriate. Base limits on actual history growth rather than arbitrary asset counts alone.

Use heartbeats to report progress. Resume only from verified durable checkpoints. Do not assume restarting FFmpeg with a seek offset safely repairs a partial container. Use validated segment artifacts or restart the affected unit.

Persist successful results atomically and use unique operation keys to prevent duplicate committed outputs.

A provider request can succeed before its response is saved. Track this ambiguity explicitly. Do not promise that Temporal guarantees exactly-once API execution or zero repeated provider charges.

Ingestion must:

- Index selected source files without moving or renaming originals.
- Preserve relative paths and source metadata.
- Fingerprint files and detect duplicates within authorized scope.
- Detect changed or missing sources and support relinking.
- Bound disk, memory, CPU, and API concurrency.
- Handle corrupt files independently.
- Produce usable results incrementally.
- Reuse valid previews, transcripts, and completed analyses.

Use shot-aware windows where helpful, with a hard maximum duration and a fallback for long continuous shots. Overlap boundaries deliberately and reconcile duplicate observations.

Benchmark full-proxy upload with bounded provider offsets against physical analysis chunks. Verify timestamp semantics and SDK behavior before choosing. Upload only derived media, never camera originals by default.

Handle provider file expiration and clean up temporary artifacts.

**Persist a first-class, editable worklog**

Use normalized records for users, workspaces, memberships, projects, assets, media timelines, shots, analysis windows, runs, observations, collections, collection items, jobs, exports, and usage.

Each observation needs:

- Authorized workspace and source asset.
- Source interval and timeline reference.
- Kind: visual event, speech, OCR, shot description, or other supported type.
- Description and structured attributes.
- Evidence references.
- Producer, model, prompt, and preprocessing versions.
- Review status and uncertainty where appropriate.
- Link to its analysis run and raw response.

Do not present inferred identity, camera focal length, or approximate transcription as verified metadata.

Keep processing events separate from footage observations. User corrections must survive reanalysis. Preserve version history so users can inspect changes without losing their edits.

Cache keys must cover all material analysis inputs, including source identity, interval, preprocessing, transcript version, model, prompt, schema, and sampling configuration.

Avoid hardcoding embedding dimensions before selecting an embedding model. Model changes may require a new index and re-embedding.

**Phase 2 — Search and context retrieval**

Implement hybrid retrieval over transcript and observation text using keyword search and embeddings, with explicit workspace filtering and ranking fusion.

Group overlapping results into useful source ranges. Every result must identify its asset and seekable interval.

Retrieve bounded evidence plus neighboring context for questions. Keep summaries as navigation aids; do not replace detailed evidence with summaries or append the entire archive to a growing conversation.

Validate citations against retrieved records. Clearly indicate incomplete processing or insufficient evidence.

Treat transcripts, OCR, filenames, and model outputs as untrusted content. They must not authorize filesystem operations, change instructions, or trigger arbitrary commands.

Use typed, validated actions for organization and exports. Never execute model-generated shell commands.

Keep the analyzer and embedder replaceable through small interfaces. Do not claim that switching to native multimodal retrieval is a trivial schema change.

**Phase 3 — Complete the application experience**

Implement real signup/login, logout, sessions, workspace creation, membership roles, and project ownership using an established authentication solution.

Use a coherent dark, media-focused design: restrained color, generous thumbnails, readable typography, monospace timecodes, strong focus states, and one clear primary action per screen.

State this aesthetic before implementation, then proceed within this authorized direction. Avoid decorative 3D and unnecessary animation dependencies.

Build:

- Onboarding and local setup.
- Project library.
- Multi-file and directory import.
- Asset player with synchronized worklog and transcript.
- Search results with timestamped thumbnails.
- Collections and selects review.
- Export queue and completed outputs.
- Settings, storage, and usage.

Support play/pause, J/K/L transport where feasible, and I/O selection shortcuts. Do not capture shortcuts while users type in inputs.

Show source timecode when available and elapsed time separately. Do not invent source timecode.

Provide loading, empty, success, error, partial-completion, canceled, and disconnected states. Show progress through SSE or a comparably appropriate mechanism with reconnection.

A browser cannot scan arbitrary local directories. Implement explicit import or a configured, allowlisted local source root through the local backend. Keep this boundary understandable to users.

Large imports should resume where supported or clearly identify files requiring reselection.

**Phase 4 — Organization and exports**

Implement:

- Manual collections.
- Suggested organization from user instructions.
- Editable assignments and an uncategorized state.
- Saved searches where practical.
- Prompt-based selects.
- Manual in/out adjustments.
- Export previews with collision and disk-space checks.

Collections are virtual and may reference the same source without duplication.

Offer organized file copies and rendered subclips in a separate output root. Preserve originals. Explain whether a collection contains full files or selected ranges.

Use deterministic render plans. Choose accurate re-encoding where required; expose stream-copy limitations rather than silently producing inaccurate cuts.

Implement JSON/CSV worklog and selection exports with provenance.

Add editor interchange in this order: FCP7 XML for Premiere-oriented workflows, FCPXML for supported applications, then EDL if justified. Document each format’s limitations.

Validate against real target editors when available. Structural XML validation alone is not evidence of a successful round-trip. If the editor is unavailable, mark round-trip validation needs input and do not claim completion.

Do not let advanced interchange delay the working local folder-and-clip workflow.

**Phase 5 — Usage and credit foundations**

Implement usage accounting from the initial pipeline, then expose it in the app.

Record analyzed duration, unique source duration, provider tokens, model, retries, rendering, and storage separately.

Use footage-minute credits as the initial customer-facing concept, with configurable rates. Do not adopt unverified cost or margin claims from the draft plan.

Implement transactional reservations, settlement, release, and audit entries. Enforce balances safely under concurrent requests and prevent duplicate settlements.

Internal retries must not multiply customer debits. Additional user-requested analysis should show its estimated cost before starting.

Provide explicit local development credits and configurable spending caps. No fake checkout or silent unlimited mode.

Defer Stripe and live payment collection. Keep the ledger ready for a later payment integration.

**Phase 6 — Security and production-readiness pass**

Audit and remediate throughout implementation, then perform a final pass.

Required security checks:

- Search source, history where appropriate, and generated client bundles for exposed secrets. Report names and locations, never values. Moving a leaked credential does not revoke it; flag rotation requirements.
- Inventory endpoints and their validation, authentication, and authorization.
- Allow public access only to deliberately public routes such as signup and health checks, with appropriate abuse controls.
- Protect reads, mutations, media streaming, SSE, search, and exports across workspace boundaries.
- Enable and test tenant-table PostgreSQL RLS alongside application authorization. Define appropriate separate access for authentication/system tables.
- Ensure application roles do not unintentionally bypass policies. Set tenant context safely with connection pooling and background workers.
- Remove disabled guards and unsafe bypass flags.
- Keep storage private; authorize media requests and use scoped, expiring access where appropriate.
- Restrict filesystem access to configured roots. Address traversal, symlink escapes, command injection, unsafe filenames, and excessive resource use.
- Protect the local backend against access from untrusted browser origins. Keep credentials server-side.
- Test cross-workspace denial paths and role boundaries.

Review every website-hardening item below and implement it or record a specific N/A, deferred, or needs-input reason:

- Custom 404 and application error pages.
- Clear above-the-fold primary actions.
- Appropriate page titles and descriptions.
- Public-page Open Graph/Twitter metadata and fallback image.
- Favicon set and manifest.
- Robots rules and public-only sitemap; never expose private projects.
- Meaningful image alternatives; empty alt text for decorative images.
- Analytics integration point, disabled without real configuration.
- Privacy/Terms placeholders clearly marked as non-final where business input is missing.
- Consent-gated analytics where applicable; no performative cookie banner without a corresponding requirement.
- Submission confirmations or thank-you pages where appropriate.
- Real contact details only when supplied.
- Clickable logo, working navigation, valid footer links, and dynamic copyright year.
- No dead buttons, unused navigation, or misleading placeholder content.

Use `TODO: provide …` markers for genuinely missing external information and list them in the handoff. Do not fabricate an address or treat an unnecessary marketing contact page as a blocker for the local application.

**Phase 7 — Responsive UX, performance, and validation**

Ensure:

- No accidental page-level horizontal overflow.
- Usable mobile layouts and accessible menus.
- Touch targets of at least 44px where practical.
- Clear labels, inline validation, and useful recovery actions.
- Optimized thumbnails, responsive images, and lazy loading.
- Pagination or virtualization for large libraries and worklogs.
- Keyboard access and visible focus.
- Reduced-motion support.
- Immediate feedback for long operations without claiming they finish instantly.

Apply UX principles through concrete improvements: reduce unnecessary choices, group related controls, put actions near their targets, use familiar patterns, distinguish the primary action, and finish flows with clear next steps.

Record the principle behind meaningful changes. Treat “7±2” as a heuristic rather than a mandatory navigation limit, and perceived responsiveness as a design objective rather than a false processing-time promise.

Run appropriate unit, integration, and browser tests. Prioritize timing, source preservation, permissions, retries, credit concurrency, and complete user journeys over superficial coverage.

**Completion gates**

The local release is complete only when verified evidence shows:

- Real accounts, workspaces, and isolated project data.
- Working ingestion, worklog, search, organization, and clip export.
- Correct source references and valid intervals.
- Preserved originals.
- Recovery after browser closure and service interruption.
- No duplicate committed outputs or customer settlements.
- Transparent treatment of ambiguous provider requests.
- Useful partial results and recoverable per-file failures.
- A measured multi-hour run on documented hardware.
- Responsive, accessible core screens.
- Reproducible setup instructions and no secrets in committed code.

Target a ten-hour, fifty-file evaluation batch when representative media is available. Measure retrieval quality against a human-labeled query set and report results by content type. Missing footage or API access is an explicit verification gap, not a passing result.

Do not mark the overall goal achieved while required local functionality or essential verification remains missing.

**Final handoff**

Provide:

- What works and how to start it locally.
- Required dependencies, environment variables, and credentials.
- Phase checklist marked done, needs input, deferred, or N/A.
- Tests performed and actual results.
- Measured timing, retrieval, throughput, and usage findings.
- Outstanding TODO markers and release blockers.
- Known limitations, especially semantic timing and editor interchange.
- Relevant file links and a short demonstration walkthrough.

Keep deployment, payment activation, and unsupported performance claims out of the completion declaration.