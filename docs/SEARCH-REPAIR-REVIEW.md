# Search and Gemini repair review — 12 September 2026

Scope: Gemini 3.1 Pro with low thinking; timestamped visual and spoken-topic worklogs; precise hybrid search with relevance filtering; immediate text results; bounded, reusable search compute; production CI. Review used the requested simplify reuse/quality/efficiency passes and all four final code-review skills. No PR exists; no GitHub comments or labels were posted.

The following list preserves every reviewer finding, including duplicates. Paths and lines identify the reviewed snapshot; later edits may move them.

1. **Reuse: duplicate model initialization** — `deploy/modal_app.py:32`. Fixed: warm embedding and relevance weights with one LocalEmbedder.
2. **Reuse: duplicated query validation** — `backend/rushes/remote_compute.py:48`, `deploy/modal_app.py:64`. Fixed: shared validator, called on both sides of the RPC boundary.
3. **Efficiency P2: indefinite shared search worker** — `backend/rushes/search_compute.py:39`. Fixed: Modal call handles use bounded result waits; client timeouts do not abandon the underlying thread or redispatch its work.
4. **Efficiency P3: duplicate model initialization** — `deploy/modal_app.py:33`. Duplicate of finding 1; fixed.
5. **Efficiency observation: accepted limit 40 but only 32 candidates** — `backend/rushes/routes_search.py:158`. Fixed: retrieve 60 candidates and rerank in batches of at most 32.
6. **Quality P2: candidate truncation hides distinct moments** — `backend/rushes/routes_search.py:158`. Duplicate of finding 5, including fallback; fixed.
7. **Quality P2: diagnostic retains unsupported thinking setting** — `scripts/compare_video_windows.py:235`. Fixed: shared model-to-thinking configuration selects Pro LOW.
8. **Reuse: hand-formatted transcript timestamps** — `backend/rushes/activities.py:195`. Removed the proposed formatting change. Existing frozen transcript context remains unchanged; speech observations retain their source timestamps.
9. **Reuse: terminal failures retain call handles** — `backend/rushes/remote_compute.py:53`. Fixed: distinguish terminal failure from uncertain polling, reclaim completed retained calls, and bound result retention.
10. **Reuse: React keys omit interval end** — `web/components/project.tsx:617`. Fixed: keys include asset, start and end.
11. **Quality P2: retained calls permanently exhaust capacity** — `backend/rushes/remote_compute.py:53`. Duplicate of finding 9; fixed, including late remote completion.
12. **Quality P2: new transcript timestamps use the planned rather than extracted clock** — `backend/rushes/activities.py:195`. Removed the proposed formatting change, preserving the existing frozen context and extraction timing contract. No approximate timestamp strings were introduced.
13. **Quality P2: exact intervals need distinct React keys** — `web/components/project.tsx:617`. Duplicate of finding 10; fixed.
14. **Quality P2: existing transcript regression would fail** — `tests/test_review_regressions.py:182`. Resolved by removing the timestamp-string change, preserving its original behavior.
15. **Efficiency P2: retained calls permanently exhaust eight slots** — `backend/rushes/remote_compute.py:53`. Duplicate of finding 9; fixed and covered with a capacity recovery regression.
16. **Efficiency P3, defensive: an older waiter can remove a newer call** — `backend/rushes/remote_compute.py:55`. Fixed: removal checks handle identity. The reviewer did not establish a reachable production race under current concurrency limits.
17. **Final testing P1: zero relevance cutoff discards a relevant concept** — `backend/rushes/routes_search.py:177`. Fixed: the small local pilot's ocean passage scores −0.461, so the cutoff is −3. Relevant car/driving/ocean/hashmaps examples remain eligible; unrelated pilot evidence scores below the cutoff. The route regression retains a negative-scoring positive while rejecting an unrelated negative. This calibration is not a representative human-labeled accuracy claim.
18. **Final breaking P1: terminal Modal timeout subclasses are mistaken for polling timeouts** — `backend/rushes/remote_compute.py:60`. Fixed: release FunctionTimeoutError and OutputExpiredError before handling the uncertain polling superclass.
19. **Final breaking P2: connection failures discard uncertain handles** — `backend/rushes/remote_compute.py:62`. Fixed: retain Modal ConnectionError handles for later polling.
20. **Final breaking P1: CI's Pro setting conflicts with a Flash-only test expectation** — `tests/test_review_regressions.py:509`, `.github/workflows/ci.yml:29`. Fixed: assert the configured model's thinking level; focused regressions passed with Pro explicitly selected.
21. **Final size: complex search changes exceed the preferred 500-line stage** — `backend/rushes/routes_search.py:152`. Fixed: commit `881eb1b` contains 296 changed foundation lines; `78fe142` contains 326 integration/test lines; `2c8d80d` contains 67 CI lines. Documentation is separate.
22. **Parent verification: budget regression mocks the previous RPC method** — `tests/test_provider_budget.py:49`. Fixed the synthetic transport failure at the new spawn boundary; failed calls still retain their monetary reservation.

The final context reviewer reported no actionable findings. Earlier requests for a “full-results cache” were clarified: this implementation caches embeddings and relevance computations for ten minutes, not final database results, so new notes and corrections remain visible.

Validation: 58 focused backend tests passed against an isolated PostgreSQL database with Pro selected and paid calls disabled. The private local pilot uses the seven existing videos plus clearly synthetic concept descriptions. Initial new local search timings were 0.06–1.01 seconds and repeated computations returned in 0.02 seconds; these are local timings, not cloud cold-start guarantees. CI and deployment results are recorded in the production inventory and validation evidence.

## Live quota-rejection follow-up

The first Pro production request received an explicit Google HTTP 429 with zero free-tier quota. The existing exception path incorrectly left this known rejection ambiguous. Commit `ec10442` (54 changed lines) classifies explicit 400/401/403/404/429 rejections separately, preserves a resumable checkpoint and file-cleanup evidence, reports billing/quota access clearly, and leaves uncertain transport/server outcomes ambiguous. Monetary reservations are not refunded. A real-SDK HTTP 429 regression and the existing checkpoint/retry integration test cover this behavior; 61 focused tests passed.

The reuse and quality agents reported no findings in this follow-up. Further agent dispatch reached the tool's task limit, so the parent performed the efficiency and four final review passes locally: no additional findings. The change adds no model context, leaves API/configuration shapes unchanged, uses the existing non-retryable error and same-job resume path, and remains below the size guidance. Tested user-facing behaviors are the actionable rejection, no automatic regeneration, retained cleanup state, no analysis-credit charge, and recovery using the existing job.
