# Organizer fixture QA — synthetic local browser fixture

Prepared and API-verified 2026-09-11T03:25:36.740804+00:00.

**This is deterministic fixture data, not live AI-processed footage.** It exists only in the explicitly designated synthetic local QA workspace. No existing project was modified or deleted.

- Project: `Organizer fixture QA` (`8f3e8281-e750-4390-a412-4f5ba7b88ffe`)
- Workspace: `5fa9da8e-0d20-49c3-a9f7-48f53b0d552f`
- Open: [http://localhost:3741/app?workspace=5fa9da8e-0d20-49c3-a9f7-48f53b0d552f&project=8f3e8281-e750-4390-a412-4f5ba7b88ffe](http://localhost:3741/app?workspace=5fa9da8e-0d20-49c3-a9f7-48f53b0d552f&project=8f3e8281-e750-4390-a412-4f5ba7b88ffe)
- Authentication: use the existing local synthetic QA account. Credentials are not included in this document or the fixture record.
- Machine-readable provenance: ignored `.local/organizer-ui-fixture.json`.

## Media and states

| File | Public source | Actual duration | Fixture state | Deterministic categories |
|---|---|---|---|---|
| Organizer fixture Coastline.mp4 | `web/public/demo/coastal-study.mp4` | 32 seconds | ready | Coastline, Waves |
| Organizer fixture Waves.mp4 | `web/public/demo/waves-study.mp4` | 16 seconds | ready | Coastline, Waves |
| Organizer fixture Aerial.mp4 | `web/public/demo/aerial-study.mp4` | 16 seconds | partial | Coastline, Aerials |

The three clips were uploaded through the authenticated API and processed by the existing local worker. That normal path created real private source copies, fingerprints, source/proxy timelines, previews and thumbnails. The original public demo files remain unchanged; their SHA-256 values match the uploaded assets. Authenticated thumbnail reads returned HTTP 200 and 1,024-byte proxy range reads returned HTTP 206 for all three files.

Gemini was verified disabled in the local API and worker before upload. The normal asset jobs completed as partial because visual AI analysis was unavailable; those job records were retained unchanged. Synthetic current-schema AnalysisRun, AnalysisWindow and Observation records were then added only for these new assets. Their producer/model/prompt explicitly identify fixture data, attempts are zero, and no paid analysis Usage records were created.

Coastline and Waves have complete deterministic evidence. Aerial has evidence for its first eight seconds and an intentionally failed synthetic window for the remaining eight seconds. Asset ready/partial states are fixture states; they do not claim that Gemini processed these files.

## Expected browser/API behavior

- All footage: 3 files; Coastline: 3; Waves: 2; Aerials: 1; Uncategorized: 0.
- Organization counts: 3 categorized, 1 partial, 0 processing, 0 not analyzed.
- The global AI-unconfigured message remains truthful and visible because application key configuration was not changed.
- Opening a file uses real authenticated media. The Worklog identifies its category evidence as synthetic local QA.
- An owner/editor can use Export category, inspect the real export preview, then explicitly start full-original category copies. Source identity, category membership and fixture evidence use the actual export pipeline. No export was started while preparing this fixture.

The demo media are generated illustrative stills with gentle zooms. This fixture is for UI, authorization and export behavior; it is not a captured shoot, a classification-quality benchmark or live AI evidence. No provider call was made and no product code, existing project, original public source or completed job was changed during fixture preparation.
