# RUSHES current experience audit

Captured during this redesign session on 2026-09-11 UTC against the deployed application. This is a baseline audit, not verification of the proposed redesign. The browser used a deliberately synthetic QA account and synthetic footage. No customer footage was used in the design concepts.

## Observed journey

1. **First visit → authentication.** The root URL immediately presents login, with signup as a secondary choice. It offers no public footage demonstration or clear preview of the result. The dark amber treatment and repeated storage explanations compete with the primary action. Add a public introduction and useful product demonstration, with distinct login/signup routes. [First visit](audit/01-first-visit.png).
2. **Signup → account form.** Name, email and password are familiar, and the password requirement is visible. The page still asks for commitment before showing the editing experience. Retain clear requirements; add field-specific feedback, password visibility and a clear next step. [Signup](audit/03-signup.png).
3. **Workspace → project.** Separate dialogs ask the user to create a workspace and then a project. Their focus rings and focused initial fields are useful. The sequence exposes organizational administration before creative value. Consolidate first-run setup around the first project, while preserving deliberate submission and recoverable resource creation. These dialogs were opened in an existing QA account; this was not a fresh-account onboarding replay. [Workspace dialog](audit/07-workspace-setup.png), [project dialog](audit/08-project-setup.png).
4. **Project library → footage.** Large folder placeholders dominate the project card, while the persistent sidebar gives substantial space to workspace administration. Use a compact project hierarchy and useful footage previews. [Project library](audit/04-project-library.png).
5. **Footage library → partial source.** The synthetic source has a usable preview but incomplete analysis. A technical schema error competes with a small thumbnail and leaves the next action unclear. Keep partial results available, explain the consequence in plain language, and expose detailed diagnostics separately. A historical invalid model interval caused this particular asset state; this screenshot does not show a newly failed processing run. [Footage library](audit/05-footage-library.png).
6. **Player → first select.** The player provides source-relative timing and an editable worklog, but the video shares a constrained modal with dense instructions. Saving the first select is disabled until a collection is created in another tab. Keep the viewer, evidence and range actions together; support first-save collection creation inline. Duplicate close controls and permanent instructions can be reduced. [Review player](audit/06-review-player.png).
7. **Settings → operational detail.** Storage locations and processor configuration dominate everyday settings. Put appearance and usage first, and group technical diagnostics under an explicit advanced disclosure. [Settings](audit/09-settings.png).
8. **Mobile settings → navigation.** At 390 × 844, wrapped navigation consumes roughly the first 250 pixels before the page content. This state measured a 390-pixel document width, so no horizontal overflow was observed here. A compact menu with focus management and close-on-navigation should restore content space. [Mobile settings](audit/10-mobile-settings.png).

## Preserve during the rebuild

- Explicit privacy information before source import and genuine upload/processing progress.
- Source-relative timing, corrections, saved ranges and persisted export status.
- Visible dialog focus, familiar form controls and access to technical evidence when needed.
- Honest partial, failed, uncertain and allowance-limited states. Visual polish must not imply completed analysis or promise an unavailable retry.

## Evidence boundaries

The accepted desktop captures show the actual browser viewport, approximately 813 pixels wide; they are not 1440-pixel desktop acceptance images. One full-page capture after a viewport override was malformed by the capture path and is excluded from the audit. The mobile measurement applies only to the captured settings state.

Import transfer, fresh-account setup, export preview/completion, navigation history, every role, keyboard-only operation, focus trapping, screen-reader output, color contrast and all responsive widths still need end-to-end verification against the rebuilt experience. The captured workspace/project dialogs are useful interface evidence, not proof of the complete first-run sequence. Earlier production browser results are recorded separately in `docs/PRODUCTION.md` and are not new redesign acceptance evidence.

## Design response and status

The three independent concept studies address the same journey with different composition: a spacious product story, an editorial contact sheet, and an immediately visible editing workspace. Their displayed mapping is recorded in [BRIEF.md](BRIEF.md). They remain direction studies; user selection is pending. Detailed auth, onboarding, product, mobile and dark-mode mockups and implemented motion remain outstanding.

Changed paths for this audit: this report and the accepted images under `audit/`. No frontend code or production configuration changed. The complete six-phase requirement ledger is maintained in [CHECKLIST.md](CHECKLIST.md).
