# RUSHES premium experience redesign

> Current release update (2026-09-11): the homepage library is now a **static illustration**, as requested after review. It has no video, playback buttons, search field or clickable sample categories. The earlier moving-still demo and its interaction QA below are historical; actual organization/search remain in the authenticated product. The separate motion-study HTML remains explicitly illustrative.

Status, 2026-09-11: the canonical product is an AI footage organizer. The corrected landing page, authenticated footage library, persisted category assignments and category-copy exports are implemented in the local worktree. A bounded live classification smoke check is recorded below. This brief does not claim a deployment or completion of visual QA. Historical starting points were production runtime `2cb0774` and repository `ad8a9ce`.

## Product correction — 2026-09-11

The user explicitly corrected the central product model: RUSHES exists to let people dump footage in and have AI sort, categorize and organize it. The earlier design overemphasized manual ranges, selects and editing. That hierarchy is superseded. The existing typography, prominent footage imagery, clean logo and restrained light/dark appearance remain the chosen visual ingredients.

Canonical journey: bulk import → AI analysis and organization → browse categories or search natural language → inspect the relevant footage → optionally export organized footage or selects. The homepage demonstrates an organized, searchable library. The main authenticated surface is the real footage library and its processing state. A player is a secondary inspection tool; timelines and trimming do not define the product.

The corrected [AI-organizer landing concept](concepts/05-ai-organizer-landing.png), its [saved prompt](concepts/05-ai-organizer-landing.prompt.txt) and the [library study](screens/08-ai-organizer-library.png) supersede the earlier editing-centered hierarchy. Earlier concepts remain historical evidence of visual selection. Mockups do not establish working behavior or classification quality.

## Required outcome

Rebuild the public first visit, login, signup, onboarding and footage-organizing workspace into one coherent experience. The first visit explains and demonstrates the product before requesting an account. Light is the default, with persistent Light / Dark / System choices across public and authenticated routes. The requested design artifacts, motion, visual verification, simplify and code-review workflows remain acceptance requirements; this brief does not replace their evidence.

The user's six-phase production/UX checklist is the acceptance source: `/Users/royluo/.codex/attachments/5d0dd615-87df-456f-ba9a-a1ea9a89d3e8/pasted-text-1.txt`. Every item remains in scope unless its final disposition explicitly explains missing operator input or why it does not apply. The earlier local-only checklist is historical and does not waive public-site requirements.

## Product and implementation facts

- Next.js 16.3.4 / React 19.3; Tailwind 4 tooling and custom CSS; Lucide icons and Radix dialogs.
- Render web/API/worker and Postgres; FastAPI, Temporal, private Modal transcription/embeddings and Gemini visual analysis.
- Primary value: import footage in bulk, let AI categorize its visible content, browse the resulting whole-file groups, search available evidence and export the files needed. Inspection, manual collections and selected ranges remain optional tools.
- Current constraints: source-relative integer microsecond timing, tenant membership/RLS, roles, durable processing checkpoints, provider allowances, explicit export preview/start, authenticated media and downloads.
- No multitrack editor, social publishing, montage generator, subtitle styling, social OAuth, password-recovery delivery, payment checkout or emailed invitations exists. Mockups must not imply those features.
- The public landing page contains an implemented local example with three deliberately public clips. Its categories and text search filter declared sample metadata in the browser. It makes no workspace request or AI request and is not evidence of classification accuracy.

## Current organization behavior

The existing Gemini window-analysis request now asks for zero to three content-specific category labels per observation, such as Coastline, Waves or Aerials. It retains the existing provider allowance and output cap; there is no second categorization request. Validated labels and deterministic slugs are stored with an organization version in `Observation.attributes`. The existing database schema and forced tenant policies carry this data; no category table or migration was added.

Project groups are derived from the latest organization-capable analysis run and its completed windows. Counts refer to distinct full assets, and an asset can appear in multiple categories. Category selection filters assets before pagination. Both project and per-asset category lists are bounded at 100, with the actual category total and an indication of additional results. This is semantic labeling during analysis, not a separate project-wide taxonomy or synonym-merging engine.

The authenticated library shows actual thumbnails, category counts, and processing, partial, not-analyzed or organized states. Completed category evidence remains visible during partial analysis and retries. A missing Gemini configuration is stated explicitly. Older analyses are not assigned invented categories or automatically sent for paid reanalysis; the existing estimate-and-confirm flow remains available. A completed analysis with no supported category is distinct from an asset that has not been analyzed. Manual collection membership is separate from AI category membership.

Natural-language search uses the existing project-wide evidence retrieval, including its keyword fallback and incomplete-processing notices. The UI identifies search as across all footage; selecting a category returns to file browsing. Category export is an explicit preview/start action for owners and editors: it copies up to 500 full originals into a separate category subfolder with numbered filenames, source verification and frozen category evidence. The first 20 supporting observations per file are retained in the export snapshot with the full evidence count and a truncation flag. Export lists expose compact download metadata rather than the full evidence payload. Existing collection/select exports remain available.

The landing example is separately implemented in `web/components/landing.tsx`: All footage, Coastline, Waves and Aerials filter three declared entries; text search matches their local names, descriptions and keywords. Its selected viewer plays only after user action. The visible filenames and “Coastal shoot” project label describe an illustrative example, not an actual captured shoot or live AI results. Source and derivative provenance is recorded in [assets/README.md](assets/README.md).

## Visual principles

Footage supplies the color. The interface supplies calm structure: generous spacing, strong type hierarchy, restrained separators, subtle surfaces and one action accent. Avoid decorative dashboards, nested cards, excessive badges and permanent technical explanations beside creative controls.

Apple inspiration means coherent behavior, clear content/control hierarchy and precise feedback. It does not mean reproducing Apple branding or assuming native framework behavior on the web. Limit translucency to navigation or transient controls, preserving legibility. This direction interprets Apple's [materials guidance](https://developer.apple.com/design/human-interface-guidelines/materials), which distinguishes controls from underlying content and recommends restrained effects.

Dark mode needs its own semantic surfaces, contrast, icons and states; it is not a color-inversion filter. Respect System only when that option is selected, and apply explicit stored appearance before paint. Apple's [Dark Mode guidance](https://developer.apple.com/design/human-interface-guidelines/dark-mode?changes=la&language=objc) informs the contrast checks; proposed web implementation details are RUSHES design decisions.

## Historical visual concepts

The numbered order below matches the actual order of generated images displayed in the conversation.

| Displayed option | Artifact | Structural direction |
|---|---|---|
| 1 | [Daylight Studio](concepts/01-daylight-studio.png) | Spacious central product story, then a substantial review preview. |
| 2 | [The Contact Sheet](concepts/02-contact-sheet.png) | Editorial text and a connected photographic contact sheet with selection context. |
| 3 | [The Editing Desk](concepts/03-editing-desk.png) | Product demonstration dominates the first visit, with a smaller introduction. |

These are initial direction studies. They are not implemented screens, final typography specifications, or proof that pictured controls work. Detailed implementation must correct any generated text, proportions, timing inconsistencies and unsupported controls. The [prompt set](PROMPTS.md) records the built-in ImageGen inputs and actual screenshot references.

## Historical user-selected visual refinement

The user chose the lighter editorial typography in option 2 and the dominant footage preview in option 3, with a better logo and a cleaner layout. The resulting [refined hybrid](concepts/04-refined-hybrid.png) established the cut-shaped R mark, lowercase wordmark, coastal imagery and quieter structure. The [refinement specification](REFINEMENT.md) records that feedback. Those visual ingredients carry forward; the hybrid's editing-first workflow is superseded by the organizer correction. Generated auth, onboarding, responsive, dark landing and library studies are retained under `screens/`; their presence does not mark implementation or browser QA complete.

## Journey architecture

1. Public landing: understand AI organization, browse the illustrative category library, play a sample and choose Organize your footage. Sign in remains accessible for returning users.
2. Signup: name, email, password, visible requirements, inline errors; clear next step. Login is a distinct route with a return destination.
3. First project: ask what the user is working on. Create a private workspace only after explicit submission, then create the project; retain returned IDs so recovery does not duplicate resources.
4. Import: file selection first, folder upload second, configured server roots only when available. Explain private server storage and derived-media processing before upload.
5. Progress and organization: distinguish uploading from server processing. Keep-the-page-open guidance applies while uploading. Show real stages and categories as completed evidence becomes available; preserve partial and unconfigured states.
6. Library: browse All footage, content-specific AI categories or Uncategorized. Use project-wide evidence search when looking for a particular subject or moment. Category counts measure files, not observation counts.
7. Inspect: open a file in the player to verify its content and evidence. Worklog, source details, reanalysis estimates, range controls and manual Selects support optional follow-up work.
8. Export: preview and explicitly start a category copy or existing collection/select export, watch persisted status, download and return to the library. Preserve the experimental editor-interchange disclosure.

The implemented route families include `/`, `/login`, `/signup`, `/onboarding`, `/app`, and workspace/project routes beneath `/app`. Legal/contact routes remain public; private project titles, thumbnails and data must not enter sitemap or social metadata.

Historical journey: the earlier proposal made video, worklog and range controls the primary workspace and centered first-select creation. That hierarchy is preserved in the earlier concept artifacts but is superseded here. Those controls survive as optional inspection and export tools.

## Artifact and build scope

| Deliverable | Evidence required before completion |
|---|---|
| Current-state audit | Accepted current screenshots, numbered findings, behavior/accessibility limits. |
| Three direction studies | Three independent generated images, saved prompts and actual display mapping. |
| Selected page mockups | Landing, login, signup, first project/import onboarding, library, player/selects, export completion and settings. |
| Theme and responsive studies | Selected key surfaces in light and dark; mobile landing/auth/onboarding/player; readable controls and hierarchy. |
| Component/state system | Semantic tokens, type/spacing scale, forms/buttons/tabs/dialogs, empty/loading/partial/error/success states. |
| Motion studies | Implemented, inspectable interaction examples with reduced-motion counterparts; see MOTION.md. |
| Working redesign | Real routes and flows connected to the existing API, no fabricated backend capabilities. |
| Production/UX checklist | Every six-phase item implemented, needs-input with literal TODO marker, or N/A with a specific reason. |
| Review and verification | Simplify passes, all code-review skill findings and dispositions, focused tests, complete browser journeys, visual comparisons and responsive/theme checks. |

## Reviewable implementation slices

1. Fix the verified request-body security issue and complete its focused review/tests.
2. Build semantic appearance/type/spacing/motion foundations and shared controls.
3. Build public landing, distinct auth routes, metadata/icons, public sitemap and operator-content scaffolds.
4. Build resumable onboarding and stable authenticated navigation.
5. Build the AI-organized library, import, search and category-copy export surfaces; retain request cancellation, SSE, pagination and permissions.
6. Preserve player/evidence inspection, optional range/collection actions and export completion beneath the library hierarchy.
7. Finish everyday settings, advanced disclosure, motion, mobile and accessibility.
8. Verify the complete requested outcome and merge only reviewed code. Hosting or provider capacity changes are not part of this design task.

## Operator input to preserve honestly

The new public site needs real operating identity, contact details, reviewed legal/policy text and an analytics decision. Do not invent a support email, address, telephone, privacy promise, endorsement, customer count or price plan. Final UI scaffolds must include the user's requested literal TODO markers, and handoff must list them. These content gaps do not prevent producing mockups or implementing the functional experience.

## Current validation boundary

The current local backend suite completed with `RUSHES_GEMINI_API_KEY= .venv/bin/python -m pytest -q --tb=short`: **156 passed, 1 skipped in 38.02 seconds**, with one `hf_xet` deprecation warning. The skip is the opt-in Temporal integration check. Local PostgreSQL access was allowed after sandbox review; paid AI was disabled. The suite covers category persistence, bounds, latest-run behavior, retry states, tenant/project isolation, frozen category exports and existing regressions using synthetic evidence.

A local browser check confirmed the real organization endpoint's unconfigured state and an existing asset with no AI category. A separate [live smoke check](qa/live-ai-category-smoke.json) made one generation request for the 16-second generated waves sample and received Coastline and Waves categories, using 1,394 input tokens and 186 output tokens, with no pending provider-file cleanup. The $0.06 conservative reservation was a cap, not a measured invoice. The check did not change application key configuration or persist its response into a user library.

That one sample verifies the real response path; it does not establish general classification quality or a complete production import-to-library journey. The landing example still uses its declared local metadata. No organizer deployment has occurred. Final visual, accessibility and release dispositions belong in the checklist and design-QA evidence, not in this brief.
