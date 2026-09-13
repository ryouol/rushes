# Export memory incident

On 12 September 2026 at 23:51:29 UTC, Render reported `server_failed` with `oomKilled.memoryLimit=512Mi` for RUSHES service `srv-dahk822d0e5s73fo22o0`. A three-second clip export had started four seconds earlier. The source was 1920×1080 HEVC with portrait rotation and approximately 60 variable frames per second. The shared web/API/worker/Temporal instance restarted, causing a temporary HTTP 502. Render recorded `server_available` at 23:51:57 UTC. The durable workflow subsequently completed the original export without intervention; its source and completed output were retained.

`render_clip` now disables x264 rate-control lookahead, threaded lookahead, and B-frame buffering, and uses one reference frame. It retains source dimensions, source-PTS selection, passthrough VFR timestamps, CRF 18, and existing audio alignment. Explicit options avoid the force-CFR behavior of the zerolatency preset. Renderer identity advances to `source-pts-v4`, so retries do not reuse receipts from the previous encoding recipe.

This trades compression efficiency for reduced frame buffering; output size and encoded quality are not promised identical. It is not a hard total-memory cap or a qualification of arbitrary footage, 4K/8K exports, or concurrent users. Hosting and provider allocations are unchanged.

## Verification

- All five existing real FFmpeg media regressions passed in 11.49 seconds: rational frame rates and original preservation, VFR half-open selections, subframe MOV timestamps, rotated audio/video previews, and late selection with nonzero PTS/delayed audio.
- A synthetic 1080p60 10-bit HEVC input with audio was exported as a three-second portrait clip in separate disposable containers limited to 512 MiB and 0.5 CPU, with 220 MiB of synthetic Python ballast. This used the existing Debian amd64 runtime image under emulation on the arm64 development machine, not the native production application. Both recipes completed without OOM. The buffering change reduced sampled container peak from 513,593,344 to 404,418,560 bytes and FFmpeg peak RSS from 301,322,240 to 187,277,312 bytes. Durations were 24.22 and 24.80 seconds. Measurements establish this comparison only; ballast does not reproduce all application activity.
- CI and production verification results will be recorded after deployment.

## Review record

All issues and qualifications from the requested review passes are retained below, including duplicate observations. Source locations refer to the reviewed diff.

1. **Simplify / reuse:** no actionable findings. Reviewed `backend/rushes/media.py:24,444` and `backend/rushes/exports.py:67`. The export-specific options need no shared proxy abstraction, and the renderer version protects receipt reuse.
2. **Simplify / quality qualification:** `backend/rushes/media.py:447`. Retaining CRF does not guarantee identical quality or output size after removing lookahead/B-frames. Accepted and documented above; no identical-quality claim.
3. **Simplify / efficiency qualification:** `backend/rushes/media.py:447`. This reduces encoder buffering but cannot cap decoder memory or other activity. Accepted and documented above; no general capacity guarantee. The reviewer independently repeated the compression-efficiency qualification in finding 2. No actionable efficiency finding.
4. **Final / testing qualification:** `tests/test_media.py:145,208`. Existing rotation and delayed-audio checks inspected proxies rather than those rendered behaviors. Fixed by adding rendered orientation/dimensions/audio, exact frame mapping, and original-versus-rendered audio-offset assertions to the existing integration tests. The initial offset assertion incorrectly compared against the unencoded fixture's intended one-second gap; the corrected assertion measures the encoded source's actual gap and allows one additional AAC priming frame.
5. **Final / breaking changes:** no findings. Reviewed `backend/rushes/media.py:24,447`, both render callers, and export receipt/resume handling. Completed exports and original copies remain usable.
6. **Final / model context:** no findings. `backend/rushes/media.py:447`, the test additions, and this document do not alter prompts or model-visible context. The Rust context-fragment requirement does not apply.
7. **Final / change size:** no findings. `backend/rushes/media.py:444`, focused media assertions, and this incident report form one small coherent change, below both skill size thresholds.
