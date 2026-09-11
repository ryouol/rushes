# Refinement verification — 11 September 2026

## Requirement status

| Requirement | Evidence | Status |
| --- | --- | --- |
| Static marketing landing, no demo/library or sample labels | DOM inspection, desktop light/dark and mobile screenshots | Complete |
| Tasteful scroll motion | Four image layers; native scrolling, pause, resume and reverse checked | Implemented; accessibility/performance limits below |
| Logo opens dashboard when signed in | Browser navigation from public landing and collection; workspace retained | Complete |
| Buggy pagination and collection editing | Real authenticated API with disposable 41-file/25-item fixtures; bounded delay/failure wrapper only for this fixture endpoint | Complete |
| Google signup, returning login and explicit account linking | Official signature verification, database state, browser binding, nonce, PKCE, scoped cookies, concurrency and revocation tests | Code complete; live setup pending |
| Simplify and all Code Review perspectives | Every finding and disposition in REVIEW.md | Complete with stated verification limits |
| Commit and push | Dependency-ordered commits on codex/production | Recorded by the final git verification |

## Automated checks

- `RUSHES_GEMINI_API_KEY= RUSHES_GOOGLE_CLIENT_ID= RUSHES_GOOGLE_CLIENT_SECRET= .venv/bin/pytest -q`: **247 passed, 1 skipped, 1 warning**, 39.73 seconds. The warning is the existing `hf_xet.download_files()` deprecation.
- Focused OAuth/database/security after review fixes: **65 passed**, 3.30 seconds.
- `npm run build`: successful production build, TypeScript, and 14 generated pages. Existing warnings concerned a parent lockfile outside the repository and experimental JSON modules.
- `npm run typecheck`, Ruff and diff whitespace checks passed.
- Six no-network analytics checks passed earlier in this refinement.
- Fresh database migration validation passed at `0006`; its disposable database was removed. See `../../validation/fresh-migrations.json`.
- Known-value and credential-shape source/client-bundle audit: zero findings; 58 API routes. The final file count is in `../../validation/security-inventory.json`. This bounded scan is not a proof of absence of every possible secret.
- The 12 new authentication browser cases and 2 state regression cases are authored and typechecked. **The Playwright suite was not executed.** Browser interactions used the selected in-app browser.

## Browser results

- Desktop 1280 × 800 and mobile 390 × 844 had no horizontal overflow. Light/dark layouts and all saved screenshots were inspected.
- Paused image transforms stayed identical while the document scrolled to 1004 pixels. Resume and scrolling back changed positions; the content itself never moved independently of normal scrolling.
- Delayed page 2 retained 40 old cards in an inert grid and keyboard focus on Next. Completion showed one active card with focus still on Next.
- Forced category failure retained that one old card inactive and displayed an error plus Try again. A successful retry showed 40 active cards and zero old alerts.
- Row 25's editor opened immediately after the row, from approximately y=119 to y=494 in the 800-pixel viewport. Its full-source checkbox received focus. Save and Cancel removed the form and restored Adjust focus. The API confirmed the saved note.
- Clicking the signed-in logo opened Projects. Public header navigation also changed to Your projects after session verification.
- Settings displayed a plain unavailable-provider message with email login still supported.
- The disposable workspace was deleted through its typed-name confirmation after testing. No paid AI requests were used; the worker was stopped during tests. The temporary API delay/failure wrapper was limited to the disposable fixture's assets endpoint and is removed from the running preview afterward.

## Pending external setup and limits

The existing Google Cloud project **Rushes** (`gen-lang-client-0912851229`) has RUSHES consent branding. The prepared Web application client **RUSHES Web** has local and hosted callback URLs ready, but **no OAuth client credential has been created**. Creating that persistent credential awaits the user's pending confirmation required by the browser tool's policy. No Wayline credential was copied, and no secret was committed.

Live Google signup/login/linking, cancellation and browser Back recovery remain pending. Reduced-motion preference changes, hidden-tab behavior, and repeated history restoration were reviewed in code but not dynamically verified. Google provider availability only indicates configuration presence. No hosted deployment or merge was performed in this refinement.

The reviewed implementation commits are `74311be` (schema, 91 changed lines), `b883740` (backend, 449), `39f02cd` (integration coverage, 742), `b5fe9d9` (navigation, 139), `b8d9ff8` (sign-in UI and browser cases, 667 plus logo binary), `1e28951` (account Settings, 238), `7c00607` (library/collection fixes, 464), and `f8c64e5` (landing/motion, 378). Each stage stays below 800 text lines; the backend implementation stays below 500. Validation records follow in a separate documentation commit.

After fixture cleanup, the normal local launcher was restored, and `/api/health` returned 200. `/api/auth/providers` returned `{ "google": false }`, confirming that live Google sign-in remains deliberately unavailable without its pending credentials. Source and bundle scanning covered **382 files**, with **zero findings** and **58 API routes**.
