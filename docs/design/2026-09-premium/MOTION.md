# RUSHES motion and interaction specification

> Current release update (2026-09-11): the homepage library is now a **static illustration**, as requested after review. It has no video, playback buttons, search field or clickable sample categories. The earlier moving-still demo and its interaction QA below are historical; actual organization/search remain in the authenticated product. The separate motion-study HTML remains explicitly illustrative.

Status, 2026-09-11: source-checked interaction specification for the local AI footage organizer. The table distinguishes implemented behavior from browser checks still required. It is not a motion-QA completion record or a deployment claim. Timings are RUSHES CSS values, not Apple system defaults.

Motion explains location, progress and completion. It never delays access to controls or provides the only indication of success. This follows the intent of Apple's [motion guidance](https://developer.apple.com/design/human-interface-guidelines/motion?changes=_3): purposeful, brief feedback with an alternative for people who reduce motion.

## Current interaction behavior

| Surface | Implemented behavior | Reduced motion | Browser verification required |
|---|---|---|---|
| First visit | Static headline, one primary CTA, category controls and a selected footage preview. No hero entrance sequence or automatic carousel is defined in `landing.css`. | Same immediately available content. | Initial rendering, focus order, layout stability and mobile navigation. |
| Landing categories/search | All footage, Coastline, Waves and Aerials filter three declared sample entries locally. Search matches their local metadata. Selection replaces the viewer without a timed walkthrough. | Same direct changes. | Keyboard operation, no-results recovery and selected-result feedback. |
| Sample playback | Explicit Play/Pause, seek and fullscreen actions; posters precede playback and MP4s use `preload="none"`. Loading and error states are visible. | CSS motion is reduced; the gentle zoom baked into a user-played MP4 remains. Playback is never automatic. | Pause/seek/fullscreen behavior, media failure, mobile controls and switching clips. |
| Account and first project | Account panels and onboarding use 220ms entrance animations. Onboarding moves upward from an 8px offset and focuses its heading once available. | Component and global rules disable entrance animations. | Focus, retained inputs, validation, retry and route transitions. |
| Dialog or sheet | Standard dialogs define a 140ms overlay fade and 180ms entrance with an 8px vertical offset. Mobile workspace sheets define a 240ms entrance and 160ms exit with 10px horizontal movement. | Global and component rules remove animated translation and transitions. | Escape, focus containment/return and nested player-shortcut isolation. |
| Library categories | Category selection resets file pagination and clears search results. Counts and thumbnails come from the API; existing request cancellation and stale-response guards remain in place. | Same direct selection and data updates. | Slow/out-of-order requests, repeated selection, empty groups and preservation of unrelated state. |
| Upload and organization | Upload percentages and server stages reflect actual requests/jobs. Organization separately displays active processing, partial results and missing configuration. Active indicators have text equivalents. | Spinners stop; state text remains. | Upload/server-stage distinction, retry transitions, partial evidence and no fabricated ETA. |
| Category export | Preview precedes explicit start. Persisted export rows expose download actions when completed; optional select export remains available from inspection. | Same state changes. | Correct category filenames, pending/error/retry states and downloads. |
| Optional Save select | Player save state and a status notice provide local feedback; the notice clears after 2.5 seconds. | Same text feedback. | Duplicate-submit guard, focus, playback state and first-collection creation. |
| Appearance and controls | Stored Light/Dark/System preference is applied before paint; only System follows device changes. Shared controls define 120–160ms transitions and sample-thumbnail hover opacity uses 150ms. | Global rules disable CSS animations/transitions and smooth scrolling. | Theme persistence, storage failure, visible focus and both-theme contrast. |

The landing example makes no inference request. Its filtering and generated sample motion must not be presented as AI completing a real import. The authenticated library's category assignments come from persisted analysis evidence; no animation substitutes for that state.

Historical proposals included a 400ms staggered hero, a footage → moment → select → export walkthrough and a moving tab indicator. Those proposals are superseded by the organizer hierarchy and are not claims about current implementation. The earlier range/save study remains relevant only to the optional inspection flow.

## Constraints

- Animate transform/opacity where possible; avoid repeated layout measurements and permanent requestAnimationFrame loops.
- No parallax, cursor-following ornaments, oscillating controls or automatic footage playback. The public sample clips are silent gentle zooms made from generated stills, not a captured shoot.
- Preserve visible content while requests are pending. Skeletons occupy realistic space and do not imply fabricated data.
- Abort and stale-response guards remain in data hooks. Background refreshes must not reset selection or replay entrance animation.
- Large video imagery stays sharp; interface blur is reserved for a small navigation/transient layer, with an opaque fallback.
- Pressed, focused, disabled, loading, error and success states must be distinguishable in both themes.
- Touch controls are at least 44px; fine-grained range changes remain possible through labeled numeric inputs.
- Restore focus after every sheet/dialog. Scope J/K/L, I/O and Space to the active review surface and exclude editable fields and nested dialogs.
- Loading/status announcements occur on stage changes or milestones, not every upload byte or percentage.

## State copy requirements

| State | Message responsibility |
|---|---|
| Empty project | Explain the first action: import footage. Defer categories without data, collections and exports. |
| Upload active | Tell the user to keep the tab open while bytes are still transferring. |
| Server processing | Explain that processing continues after leaving this page only once upload is complete. |
| Organizing | Use the actual processing state. Resumed failed/canceled runs show processing while completed category evidence remains visible. |
| Partial | Show only categories supported so far; explain missing analysis. Offer Resume only when returned by the API. |
| AI not configured | Say visual analysis is not configured; preserve import and inspection without fabricating categories. |
| No category | Distinguish completed analysis with no identified category from older or unprocessed footage that needs analysis. |
| Uncertain provider response | Preserve available work and avoid promising a harmless automatic retry. |
| Allowance reached | Explain that new AI processing is paused; preserve review/export actions that still work. No checkout CTA. |
| No results | Keep the query and incomplete-processing context. Distinguish the landing example's local filtering from authenticated project-wide evidence search. |
| Session expired | Provide sign-in with safe navigation context. Never retain a password. |
| Export failed | Preserve the failed record and its explicit retry action. |
| Export ready | Give the real download and a clear return to footage. |

## Acceptance artifacts

Record browser demonstrations of landing category/search changes and explicit playback, import-to-organization states, library filtering, file inspection, category export completion and theme changes. Include optional range/save feedback as a secondary flow. Repeat relevant paths with reduced motion. These demonstrations supplement functional tests and screenshots; CSS declarations alone do not establish motion QA.

This documentation update inspected the component and style sources. It did not perform or certify the full browser motion matrix. The local backend suite passed 156 tests with paid AI disabled; that result does not validate frame timing, focus behavior or visual motion. Current browser/release dispositions remain in the checklist and design-QA record. No organizer deployment is claimed.

### Standalone interaction study

[Open the local motion study](motion-study.html). This single HTML file is labeled **“Interaction study • illustrative states”**. It embeds the unchanged local Inter font, its license, the RUSHES mark and the three public 640px generated WebP thumbnails. It can be opened directly or copied alone into a temporary directory for a loopback static preview; the repository does not need to be served. It is not a product route or a recording of the actual application.

Use the controls to move from Imported to Simulate processing to Show categories, filter the declared example groups, open the evidence disclosure and dialog/sheet, then reveal/reset completion feedback. Light/Dark and the visible Reduce motion switch apply to every study. States change only on user action; reduced motion removes entrances and cancels motion already in progress. There are no provider/API requests, automatic playback, simulated processing delays, export operations or downloads.

The semantic palettes and shared `cubic-bezier(.2,.7,.2,1)` curve come from `web/app/globals.css`. Dialog entrance is 180ms with an 8px offset; its backdrop fades over 140ms. The sheet uses the current `web/components/workspace.css` values: 240ms, a 10px offset and `cubic-bezier(.22,1,.36,1)`. The library, disclosure and persistent completion entrances reuse the 180ms curve as **study proposals**, not claims that those exact app transitions ship. The study initializes its switch from the device motion preference and also allows manual comparison.

Preparation checks: embedded asset bytes match their local sources, scripts pass Node syntax validation, and the file has no external asset dependencies. The separate artifact browser review is recorded below. These checks do not certify runtime device-preference behavior, actual backend state or the app's motion-QA matrix.

### Bounded artifact browser evidence — 2026-09-11

The local standalone study was exercised in the user's in-app browser. Imported → Processing → Categorized changed on command; the Waves filter showed two entries; the ready receipt showed two example copies. The evidence disclosure opened, and both the dialog and sheet opened and closed with Escape, returning focus to their respective opener. Light/Dark controls changed appearance. Enabling the manual Reduce motion switch displayed the instant-entrance state. These are interactions with declared illustrative data; no analysis or export ran in this artifact.

Desktop at 1330px and mobile at 390px had no horizontal document overflow. Saved views: [desktop dark](qa/motion-study-desktop-dark.png) and [mobile light](qa/motion-study-mobile-light.png). Screenshots document those layouts; they do not measure animation frame timing.

The actual application's OS-level `prefers-reduced-motion` matrix remains untested. The artifact's manual switch and bounded Escape/focus checks do not establish that broader app behavior or certify accessibility across browsers and assistive technologies.
