# Management and static landing verification

Local verification on 2026-09-11; final implementation commit `e64ba31` and its preceding backend/security commits, before evidence commit. This is not a hosted deployment record.

## Actual disposable-file cleanup

Created a new workspace named “Management deletion QA 626d6a29” and project “Disposable management check” only for this check. Two synthetic files, 122,880 bytes each, were uploaded through the real authenticated API. No video analysis was dispatched; the temporary worker was stopped and the API key disabled during these checks.

| Operation | HTTP result | Reclaimed bytes | Removed files |
|---|---:|---:|---:|
| Delete first uploaded video | 200 | 122,880 | 1 |
| Delete project containing second upload | 200 | 122,880 | 1 |
| Delete now-empty workspace | 200 | 0 | 0 |

The workspace, project and both disposable files are gone. The pre-existing Design QA projects and organizer fixture were retained. Actual HTTP deletion and backend integration tests verify cleanup. In-app browser checks opened the corresponding confirmation dialogs and canceled them; no claim is made that a destructive browser confirmation was clicked in this session.

## Browser verification

- Workspace/project exact-name confirmation stays disabled for a wrong or empty name and enables for the correct name. Keep cancels safely. Video confirmation clearly describes uploaded-copy removal and separately retained completed exports.
- Reload after actual video deletion shows only the remaining disposable upload. Manage footage opens Projects.
- Settings member disclosure expands to the existing email/role form and collapses again. Support details is collapsed by default.
- Desktop Light and mobile Dark settings captured; 390px viewport and document width both measure 390px. Header icons/labels, storage values and deletion action remain readable.
- Static landing retains the approved imagery and has zero videos, search inputs or buttons inside the example-library section. Mobile 390px has no horizontal overflow.
- Normal API and worker configuration restored after tests. HTTP health returned 200 and the browser reports AI is set up. Temporary viewport overrides and Dark theme were reset for handoff.

Screenshots: [settings desktop](settings-storage-desktop.png), [settings mobile dark](settings-storage-mobile-dark.png), [landing desktop](static-landing-desktop.png), [landing mobile](static-landing-mobile.png), [project confirmation](delete-project-confirmation.png). Settings screenshots taken during blank-key QA show the truthful Needs setup state; the normal private key was restored afterward and AI is set up was verified in the browser.

## Storage diagnosis

At investigation time the local host had 2,124,619,776 bytes free, slightly below the existing 2,147,483,648-byte processing reserve, explaining zero usable capacity. RUSHES media used about 380 MiB and exports about 8 MiB; the app was not the main host disk consumer. Only an unused, rebuildable web/.next/dev cache was removed (427.0 MiB of file bytes). No existing uploaded footage or export was removed to free space. Later host free-space increases occurred independently and are not attributed to that cache cleanup. Local capacity is distinct from hosted persistent-disk capacity.

Settings now reports capacity after the reserve. The batch preflight uses a fresh settings read and a conservative working-copy estimate, retaining server-side checks when the advisory read is unavailable. Four settings and ten storage regressions passed in the final suite; eight separately exercised component flows covered zero capacity, batch estimates, exact boundary, unavailable settings, server error and retry. Those component checks were stubbed, not browser automation.

## Final checks and limits

- Full backend: 194 passed, one opt-in Temporal skipped, one dependency deprecation warning, 33.53 seconds. Includes authorization, cross-tenant isolation, source preservation, failed cleanup/retry, accounting retention and repeated-cancel thread/deletion exclusion.
- Analytics: six isolated no-network tests passed.
- Production Next build: passed, 1,101 ms compilation, 2.2 seconds TypeScript, 14 generated pages. Final separate TypeScript check passed after new browser regressions.
- Ruff and whitespace: passed. Source/client-bundle audit: 356 files, zero findings, 53 API operations.
- Browser regression suites were updated and reviewed but not executed via Playwright CLI. Manual in-app checks above supplement them.
- No new model inference, deployment, Docker-image build or production-data mutation was part of this iteration. Contact/legal operator TODOs remain as previously documented.
