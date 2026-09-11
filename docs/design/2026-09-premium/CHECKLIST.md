# Production hardening and premium UX acceptance checklist

Updated 2026-09-11. RUSHES is an **AI footage organizer**: bulk import → AI categories → library/search → inspect → optional organized export. The earlier editor-first direction is superseded. This checklist preserves the earlier local implementation review; the final management addendum below supersedes counts and commit status; no new production deployment or merge is claimed.

Stack: Next.js 16.3.4 / React 19.3, Tailwind 4 tooling and custom CSS; FastAPI, Temporal, PostgreSQL/pgvector; Render web/API/worker/private media disk, with optional private Modal compute. The original six-phase request is `/Users/royluo/.codex/attachments/5d0dd615-87df-456f-ba9a-a1ea9a89d3e8/pasted-text-1.txt`.

✅ Done means implemented with the bounded evidence below. ⚠️ Needs-input means missing operator facts/configuration, not invented content or an implicit approval request. ➖ N/A includes its reason. Local implementation is distinct from release clearance. [BRIEF.md](BRIEF.md), [MOTION.md](MOTION.md), [security audit](../../SECURITY-AUDIT.md) and QA artifacts preserve the detailed limits.

## Phase 1 — Security; block release until hosted checks are refreshed

| Requirement | Disposition |
|---|---|
| Exposed keys: source, history and client bundle; relocate and list exposures | ✅ The final local scan covered 339 source/client-bundle files with zero findings after the production build; the refreshed inventory has 49 operations. The separate history scan remains historical. No relocation/rotation was needed. Secret variable names and server-only locations are listed in the security audit without values. Rebuilt hosted bytes remain a release check. |
| Every endpoint: auth + input validation, with inventory | ✅ All 49 current operations inventoried. Public auth/health exceptions are explicit. Member-read organization and category filters retain tenant/project scoping; mutations require editor/owner. Request bodies are bounded at 64 KiB, folder batches at 8 MiB; media upload retains streaming limits. |
| RLS/security rules for every table; anonymous access | ✅ Fresh local catalog: 17 forced tenant policies, 23 tables inventoried, six justified authentication/system exceptions, zero PUBLIC table grants. Hosted SQL needs fresh release evidence. |
| Broken/disabled/hardcoded auth gates | ✅ No bypass found in inspected current source. |
| Public storage buckets; scoped media access | ✅ Private disk storage uses authenticated media/download routes and containment checks. ➖ Bucket policy changes are N/A: no S3/Supabase/Firebase object bucket is configured. Hosted disk/Modal configuration remains a release check. |

Changed: `backend/rushes/security.py`, `api.py`, organizer/category/export routes, `organization.py`, `exports.py`, `tests/test_security.py`, `test_organization.py`, `test_organization_exports.py`, `docs/SECURITY-AUDIT.md`. Deliberately skipped: credential rotation without an exposure, nonexistent bucket policies, production mutation during local design work. Release remains blocked on the hosted verification named in the audit.

## Phase 2 — Production surfaces

| Requirement | Disposition |
|---|---|
| Custom 404 and supported 500 | ✅ Custom not-found, route error and global error recovery surfaces; useful home/workspace/retry actions. 404 status/title verified over HTTP. Error boundary behavior is covered by implementation review; a production server crash was not induced. |
| Above-fold CTA | ✅ Public landing offers Organize your footage before authentication; distinct Sign in for returning users. Auth/onboarding have one main action. |
| Per-page title/description | ✅ Landing, login, signup, onboarding, app, contact, privacy, terms and 404 have route metadata. Private project names remain absent. Local HTML verified. |
| Per-page OG/Twitter, default image | ✅ Route titles/descriptions with a shared 1200 × 630 RUSHES social card; both image endpoints return PNG responses with HTTP 200. |
| Full favicons | ✅ ICO, 16/32px PNG, 180px Apple touch and 192/512px manifest assets; raster mark shared with header. |
| robots.txt and generated sitemap.xml | ✅ Runtime-origin crawler files; account/API/workspace excluded, public landing indexed; draft legal/contact noindex. Local origin is deliberate in local configuration. |
| Image alt text | ✅ Informative footage images have descriptions; decorative brand mark has empty alt inside an accessible home link. Player thumbnails use source labels. |
| Analytics wired up | ✅ Optional GA4 adapter, server-only ID configuration, three allowlisted completion events, private fields omitted. ⚠️ Needs-input: actual provider/ID/tracking decision. Disabled while unconfigured. |
| Privacy and Terms | ✅ Public factual scaffolds clearly marked draft. ⚠️ Needs-input: legal entity and reviewed policy/Terms; no legal approval is claimed. |
| Cookie banner / consent gating | ✅ Basic opt-in banner/preferences when analytics is configured; no third-party tag before consent; revocation and cross-tab handling. ⚠️ Needs-input: approved consent/cookie copy and provider-side Enhanced Measurement audit before enabling. Essential-only unconfigured use does not show an unnecessary banner. |
| Thank-you page after form submits | ➖ Separate lead/payment thank-you route is N/A: no lead form or checkout. Applicable account/project/save/export confirmations are implemented in place. |
| Clickable real email/phone/address | ✅ Server-configured contact scaffold validates mailto/tel values and renders address. ⚠️ Needs-input: real email, phone, address and operating identity. No fabricated links. |

Changed: `web/app/layout.tsx`, `page.tsx`, `login/`, `signup/`, `onboarding/`, `app/`, `contact/`, `privacy/`, `terms/`, `error.tsx`, `global-error.tsx`, `not-found.tsx`, `robots.ts`, `sitemap.ts`, `manifest.ts`, `opengraph-image.tsx`, favicon/font/public assets; `web/lib/metadata.ts`, `analytics.ts`, `components/analytics-consent.*`. `.dockerignore`/Dockerfile now include required public assets. Deliberately skipped: fabricated legal/contact content and live analytics configuration; standalone thank-you route without a corresponding form.

## Phase 3 — Forms, states and dead ends

| Requirement | Disposition |
|---|---|
| Loading states for async actions/transitions | ✅ Workspace/auth/onboarding loaders; upload bytes vs server processing, asset/category loading, pending saves/exports, cancellation and stale-response guards. Real processing states are retained. |
| Inline validation/form errors | ✅ Auth requirements, trimmed name/email, unchanged password semantics, first-error focus; onboarding and project validation; source timing constraints. Correcting a field clears its existing error without moving the submit target on blur. |
| Success/error feedback for submissions | ✅ Account/onboarding, upload, notes/corrections, collections, export preview/start/download and settings report outcomes/recovery. Confirmed real note edit survives collapse and saves correctly. The synthetic organizer fixture's Waves category produced two real full-file copies; a browser download event and matching output/original hashes are recorded. |
| Buttons/links do something | ✅ Core journey connected to real API. Public demo categories/search/clear/recovery/playback work locally on deliberately illustrative data. No editor timeline remains on the homepage. |
| Broken links, including footer | ✅ Public destinations and 404 verified; legal/contact/home links share real routes. No invented contact destination. |
| Clickable logo → home | ✅ Shared Brand link on public/auth/product surfaces. |
| Remove placeholders/unused navigation | ✅ Unsupported editor-first homepage replaced; real Library/Collections/Exports hierarchy. Deliberate sample labeling and operator TODO scaffolds remain explicit. |
| Dynamic copyright year | ✅ Rendered from current year, not hardcoded. |

Changed: `components/landing.*`, `auth.*`, `onboarding.tsx`, `rushes.tsx`, `project.tsx`, `organization-library.*`, `player.tsx`, `collection-view.tsx`, `import-dialog.tsx`, `settings.tsx`, `dialog.tsx`, `asset-tools.tsx`, shared header/footer and E2E suites. Deliberately skipped: unsupported payments, social publishing, password recovery delivery and emailed invitations. These are not offered as dead controls.

## Phase 4 — Mobile and performance

| Requirement | Disposition |
|---|---|
| No horizontal scrolling | ✅ All seven public routes checked at 320px in dark mode: document width equals viewport. Landing also checked at 390px and 1330px; authenticated/mobile QA evidence is recorded separately. |
| Responsive breakpoints across pages | ✅ Landing/auth/legal/workspace/library/player/dialogs/settings adapt their columns, navigation and controls. Mobile dark export inspection identified the download foreground issue; links now use `--on-accent`. The disk output path is collapsed under Output location, leaving downloads visible. Final visual review is recorded separately. |
| Mobile menu: focus trap, closes on navigation | ✅ Radix dialog navigation; keyboard wrap, Escape and focus return verified. Explicit menu-trigger ref repairs return focus. |
| Sticky mobile CTA | ✅ Appears after landing introduction scrolls away; hides while introduction is visible. Manual scroll check verified both states; avoids covering initial playback controls with a duplicate CTA. |
| Image optimization | ✅ WebP 640/960/1440/1672px variants, srcset/sizes, reserved dimensions, below-fold lazy thumbnails. Public videos load on request, without autoplay. Source mockup PNGs are design artifacts, not page backgrounds. |
| 44px targets/readable text | ✅ Primary/icon/category/menu controls use a 44px minimum; mobile seek target increased to 44px. Appearance radio labels provide full 44px targets around native indicators. Narrow-route bounds and visible layout inspected. |

Changed: semantic tokens and responsive rules in `globals.css`, `landing.css`, `auth.css`, `workspace.css`, `editor.css`, `organization-library.css`, `legal.css`; responsive public assets. Deliberately skipped: automatic background video and heavy 3D packages, which would add cost without supporting footage organization.

## Phase 5 — Applied UX constraints

| Principle | Implemented change |
|---|---|
| Hick / Occam / Tesler | ✅ One main import action; three primary project tabs; advanced selection/range tools and analysis details disclosed on demand; AI does category assignment. |
| Fitts / target distance | ✅ Large primary import/auth actions and nearby category-export action; 44px controls; mobile CTA after the first action scrolls away. |
| Jakob / Similarity / Uniform Connectedness | ✅ Conventional public/auth routes, labeled forms, searchable library, consistent tabs and grouped footage controls. |
| Proximity / Prägnanz | ✅ Footage grid uses restrained separators; file metadata stays with its thumbnail; related worklog edits stay together. |
| Miller | ✅ Three project views; first three AI categories with More for remaining categories. This is choice reduction, not a claim that seven is a universal limit. |
| Doherty | ✅ Immediate pending/pressed/loading feedback; background content retained where safe; real processing progress rather than fake fast AI completion. No universal latency benchmark is claimed. |
| Von Restorff | ✅ One blue primary action per task; secondary controls visually quieter. |
| Serial Position | ✅ Library first; optional exports last; import action above content. |
| Peak-End / Zeigarnik | ✅ Explicit upload/processing progress and local saved/export-ready confirmation; onboarding preserves confirmed creation steps on retry. |
| Postel | ✅ Appropriate text is trimmed/normalized; passwords preserved; category labels, IDs, times and authorization validated strictly server-side. |
| Pareto | ✅ Prioritized first visit → account → import → AI organization → find footage. No invented usage percentages. |

Changed: the Phase 3/4 components and organizer backend. Deliberately skipped: fabricated completion percentages, estimates and optimistic claims that processing finished before the server confirms it.

## Phase 6 — Selected visual direction

| Requirement | Disposition |
|---|---|
| Coherent proposal before coding | ✅ Three original direction studies; user chose option 2 typography + option 3 image with better logo/less clutter. Corrected AI organizer landing/library mockups precede the organizer layout. Earlier editor-first concepts are explicitly historical. |
| Magic UI where useful/supported | ➖ No added Magic UI dependency: existing Radix/Lucide and small CSS transitions supply the required restrained interactions; extra ornamental components do not serve this selected direction. |
| Threlte/R3F if purposeful 3D | ➖ Threlte is not applicable to React; no approved 3D scene requires R3F. Footage remains the main visual. |
| Vectary/Jitter external export slots | ➖ No installation: optional authored explainer/landing media could replace an illustrative asset later. Neither is required for the implemented UI. |
| Premium light/dark/system, screens and motion | ✅ Shared Inter type, custom raster mark, semantic themes, public/auth/onboarding/library/inspection/settings surfaces and purposeful dialog/form transitions. Responsive/theme studies and comparisons are retained. The standalone [motion study](motion-study.html) adds three user-controlled illustrative flows with Light/Dark and Reduce motion controls. It is a local design artifact, not an app recording or backend evidence. Detailed motion/verification limits remain in [MOTION.md](MOTION.md) and the final QA report. |

Changed: `docs/design/2026-09-premium/` briefs, generated concepts/screens/prompts/assets/QA, `web/public/`, local Inter/font license, shared themes/brand and component styles. Deliberately skipped: unsupported controls/text invented by ImageGen (including the mobile study’s photo-upload wording); reference artifacts do not expand product capability.

## Operator TODO markers

Replace only with real approved content. Literal comments remain in the relevant sources.

- `<!-- TODO: provide legal entity name -->`
- `<!-- TODO: provide reviewed privacy policy -->`
- `<!-- TODO: provide reviewed Terms -->`
- `<!-- TODO: provide analytics measurement ID -->`
- `<!-- TODO: provide analytics provider, measurement ID, and tracking decision -->`
- `<!-- TODO: provide applicable analytics consent requirements and approved cookie copy -->`
- `<!-- TODO: provide contact email -->`
- `<!-- TODO: provide contact phone number -->`
- `<!-- TODO: provide physical contact address -->`

## Evidence and release limits

- Full backend suite: 156 passed, 1 opt-in Temporal test skipped, one dependency deprecation warning, 38.02 seconds; paid AI disabled.
- Subsequent organizer/inference/export focused suite after aggregation simplification: 53 passed; later category normalization checks: 27 passed. These are focused runs after the full-suite result, not another full-suite run. Analytics adapter: 6 tests passed without network. The final production web build passed: 791 ms compilation, 2.2 seconds for TypeScript and 14 generated pages. A fresh source/client-bundle scan then checked 339 files with zero findings and refreshed the 49-operation inventory.
- Separate live AI smoke: one 16-second generated wave clip returned Coastline/Waves; 1,394 input and 186 output tokens; provider temporary file removed. A $0.06 conservative request reservation was bounded within the existing $2 allowance; it is not a measured invoice. No app key/configuration was changed and the smoke response was not inserted into a user library.
- Browser QA uses the user’s in-app browser. Updated Playwright suites were typechecked and reviewed; CLI Playwright was not run. Core real auth/onboarding/upload/correction/select/export/download paths and the corrected public demo have manual browser evidence. Synthetic organization fixture data is labeled separately from the live model smoke.
- Category-copy evidence: the explicitly synthetic [Organizer fixture QA project](qa/organizer-fixture-readme.md) supplied deterministic Waves membership. The real API/worker exported two full files into the `waves/` group; a browser download event was observed, and both output byte hashes match the preserved originals. [Export verification](qa/category-export-verification.json) records the two outputs and byte-match results. This validates the export path for fixture membership, not live model classification quality.
- The [standalone motion study](motion-study.html) embeds the local font, mark and three compressed generated thumbnails. It makes no API/provider requests and has no playback or automatic state progression. Embedded bytes, script syntax and DOM references were checked. In-app browser review verified its stage controls, two-entry Waves filter, two-copy example receipt, disclosure, dialog/sheet Escape and focus return, theme controls and manual instant-entrance state. Desktop 1330px and mobile 390px layouts had no horizontal overflow; [MOTION.md](MOTION.md) links the screenshots. The actual app's OS-level reduced-motion matrix remains untested.
- Local handoff: normal AI key inheritance was restored after QA by removing the temporary blank-key override; `.env` is unchanged. The production-mode API/worker are healthy under the environment-only `RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD=2000000` limit, preserving the authorized $2 allowance. No jobs were pending/running and no new inference was requested at restoration. The monthly conservative reservation was $0.06, not a measured invoice. The fixture categories remain explicitly synthetic.
- Hosted production is unchanged. Before release: refresh hosted SQL/RLS/storage/Modal/ingress evidence, rebuild/scan hosted client assets, fill public-content decisions, audit analytics provider settings if enabling, and merge reviewed slices. No capacity increase or deployment was performed.


## Final management update

- Homepage sample is explicitly static, preserving the approved design; obsolete playback/search interactions are removed.
- Plain-language storage/settings, capacity preflight, workspace/project/video/export/collection deletion and cancellation-safe cleanup are implemented.
- Final validation: 194 backend passed, one opt-in Temporal skipped; six analytics passed; production Next build and final TypeScript check passed; Ruff/whitespace passed. Security scan: 356 files, zero findings, 53 operations.
- Disposable upload deletion reclaimed 122,880 bytes, project deletion another 122,880 bytes, then the empty workspace was removed. Existing footage was preserved.
- Three deletion browser regressions are authored/typechecked/reviewed, not executed. Final in-app mobile/desktop checks and confirmation/cancel checks are recorded in qa/management-verification.md.
- Requested commit series separates coherent changes; the frontend cutover remains a documented large stage. No deployment or merge is claimed.
