# Refinement verification — 11 September 2026

## Requirement status

| Requirement | Evidence | Status |
| --- | --- | --- |
| Static marketing landing, no demo/library or sample labels | DOM inspection, desktop light/dark and mobile screenshots | Complete |
| Tasteful scroll motion | Four image layers; native scrolling, pause, resume and reverse checked | Implemented; accessibility/performance limits below |
| Logo opens dashboard when signed in | Browser navigation from public landing and collection; workspace retained | Complete |
| Buggy pagination and collection editing | Real authenticated API with disposable 41-file/25-item fixtures; bounded delay/failure wrapper only for this fixture endpoint | Complete |
| Google signup, returning login and explicit account linking | Official signature verification, database state, browser binding, nonce, PKCE, scoped cookies, concurrency and revocation tests | Complete; live linking and returning login verified |
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
- The 13 new authentication/history browser cases and 2 state regression cases are authored and typechecked. **The Playwright suite was not executed.** Browser interactions used the selected in-app browser.

## Browser results

- Desktop 1280 × 800 and mobile 390 × 844 had no horizontal overflow. Light/dark layouts and all saved screenshots were inspected.
- Paused image transforms stayed identical while the document scrolled to 1004 pixels. Resume and scrolling back changed positions; the content itself never moved independently of normal scrolling.
- Delayed page 2 retained 40 old cards in an inert grid and keyboard focus on Next. Completion showed one active card with focus still on Next.
- Forced category failure retained that one old card inactive and displayed an error plus Try again. A successful retry showed 40 active cards and zero old alerts.
- Row 25's editor opened immediately after the row, from approximately y=119 to y=494 in the 800-pixel viewport. Its full-source checkbox received focus. Save and Cancel removed the form and restored Adjust focus. The API confirmed the saved note.
- Clicking the signed-in logo opened Projects. Public header navigation also changed to Your projects after session verification.
- Settings displayed a plain unavailable-provider message with email login still supported.
- The disposable workspace was deleted through its typed-name confirmation after testing. No paid AI requests were used; the worker was stopped during tests. The temporary API delay/failure wrapper was limited to the disposable fixture's assets endpoint and is removed from the running preview afterward.

## Pre-deployment snapshot and limits

Before deployment authorization, the existing Google Cloud project **Rushes** (`gen-lang-client-0912851229`) has RUSHES consent branding. The prepared Web application client **RUSHES Web** has local and hosted callback URLs ready, but **no OAuth client credential has been created**. Creating that persistent credential awaits the user's pending confirmation required by the browser tool's policy. No Wayline credential was copied, and no secret was committed.

At that snapshot, live Google signup/login/linking, cancellation and browser Back recovery were pending. Reduced-motion preference changes and repeated landing-page history restoration were subsequently verified in the browser. Hidden-document behavior, idle stopping and cleanup passed a controlled Node harness; that is simulation evidence, not a native background-rendering measurement. Google provider availability only indicates configuration presence. No hosted deployment or merge had been performed at that snapshot; the later deployment evidence supersedes the deployment status.

The reviewed implementation commits are `74311be` (schema, 91 changed lines), `b883740` (backend, 449), `39f02cd` (integration coverage, 742), `b5fe9d9` (navigation, 139), `b8d9ff8` (sign-in UI and browser cases, 667 plus logo binary), `1e28951` (account Settings, 238), `7c00607` (library/collection fixes, 464), and `f8c64e5` (landing/motion, 378). Each stage stays below 800 text lines; the backend implementation stays below 500. Validation records follow in a separate documentation commit.

After fixture cleanup, the normal local launcher was restored, and `/api/health` returned 200. `/api/auth/providers` returned `{ "google": false }`, confirming that live Google sign-in was unavailable at that pre-deployment snapshot. Source and bundle scanning covered **382 files**, with **zero findings** and **58 API routes**.

## Continuation verification

The preceding goal turn made concrete progress: nine reviewed commits were pushed at `003ad79`, the UI flows were verified, and the synthetic workspace was removed. This continuation closed motion-verification gaps and found/fixed one additional navigation defect.

- Temporarily enabled macOS Reduce Motion from its original Off setting. The actual in-app browser reported `prefers-reduced-motion: reduce`, all four computed image transforms were `none`, and the motion button disappeared. Navigating to the workflow section moved the document to 1084 pixels while all transforms remained `none`. Restored the setting to Off, confirmed the preference became false, the Pause control returned and transforms resumed, then closed System Settings.
- Inspected [reduced-motion screenshot](qa/09-reduced-motion.png); text and imagery remain visible, with no motion control.
- [Controlled lifecycle evidence](qa/motion-lifecycle.json): 15 grouped assertions passed against the production module. Initial, scrolled and visible-restart loops settled in 48, 53 and 52 simulated frames at 60Hz. Tests covered coalescing, zero writes for unchanged clamped transforms, hidden-document cancellation/no scheduling, visible remeasure/restart, complete cleanup and ten start/cleanup cycles without duplicate listeners. This does not measure native rendering or React integration.
- Reproduced a history defect twice: native hero section link → Privacy → Back restored `/#workflow` in the address bar while Privacy content remained. Direct landing → Privacy → Back worked. Installed Next router code ignores null history state; documented Next Link supports section hashes. Replaced the hero's native anchor with the already-imported Next Link.
- After rebuilding and reloading, repeated the exact section link → Privacy → Back sequence twice. Both returned the landing heading, four motion layers and Pause control at `/#workflow`. The returned Pause control also worked. Added an authored browser regression that checks content as well as the URL; the suite remains unexecuted.
- Production build/TypeScript and diff checks passed after the two-line UI fix. Follow-up Simplify and all Code Review perspectives reported no new issues. The implementation/regression diff was 26 changed lines.
- At the end of that continuation, `/api/auth/providers` returned HTTP 200 with Google false and the Google Console displayed the prepared client form. Credential creation and live provider checks were still pending then; the deployment below supersedes that status.


## Live deployment verification

The user authorized deployment and completion of Google sign-in. A dedicated RUSHES Web OAuth client is configured for the exact local and production callbacks, with basic identity scopes and an External audience published In production. The client secret is stored only in ignored local configuration and the server environment. An unused initial credential was retired and deleted before installing its replacement; no credential is committed.

- Production migrated from `0005` to `0006`: 17 forced-RLS tables, both OAuth tables, two cascading foreign keys and runtime CRUD grants verified. Temporary migration access was limited to the current IPv4 `/32`; the original empty external allowlist was restored and verified.
- The reviewed application deployed to [RUSHES](https://rushes.onrender.com). Exact deployment and subsequent follow-up identifiers are in [production evidence](../../validation/production-google-deployment.json). Existing password-session workspace data remained available, and the updated settings UI rendered. Public landing, privacy, terms, health and provider endpoints returned 200; Google availability was true.
- Real Google account selection and consent reached the expected existing-password-account recovery on both local and production. Password authentication succeeded on both deployments. Local explicit linking displayed Google connected; logout and Google-only sign-in returned to the same account, workspace and projects.
- Production sign-in → Google chooser → Back restored an enabled Google button; retry reached the chooser again. Local Settings → Connect Google → chooser → Back restored enabled connection controls and reloaded status; retry successfully connected the account.
- Production exposed one new gap: a password account with no workspaces was redirected from connection settings to first-project onboarding. Follow-up `83d8758` provides account-only Settings, reuses the existing GoogleAccount component, and adds an Account settings link during onboarding. The production build and TypeScript checks passed; all Simplify and Code Review perspectives found no remaining issues after the busy-link guard fix.
- Render deployment `dep-dai1us9594qs73e2glqg` made that follow-up live at `2026-09-11T15:35:52.238858Z`. The actual account-only production screen displayed Connect Google. Real Google linking returned a connected confirmation. After logout, Google-only sign-in opened the same existing account; onboarding’s Account settings link showed Google connected. No workspace or project was created. Local linking and workspace access also persisted after restarting the updated app.
- Compared all 20 preexisting server environment values with the final 22-variable configuration: all preserved, both Google settings matched the private source, the service plan stayed unchanged, and the database external allowlist remained empty.
- A synthetic callback query marker was absent from observed application logs while the callback path appeared. No request logs were returned; external ingress query redaction remains unverified.

The additional browser regression is authored and typechecked; CLI Playwright execution remains unperformed. Real new-Google-account creation cannot be repeated with the selected existing account; signup creation, cancellation and identity edge cases retain the earlier generated-token integration evidence. Live linking and returning login are recorded separately from those automated cases.
