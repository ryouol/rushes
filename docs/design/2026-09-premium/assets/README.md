# Organizer sample and brand assets

> Current release update (2026-09-11): the homepage library is now a **static illustration**, as requested after review. It has no video, playback buttons, search field or clickable sample categories. The earlier moving-still demo and its interaction QA below are historical; actual organization/search remain in the authenticated product. The separate motion-study HTML remains explicitly illustrative.

Updated 2026-09-11. These source assets support the selected coastal visual direction and the public AI-organizer example. Sources are retained in this directory; application derivatives are under `web/public`. “Production” in the original prompts below means an asset intended for application use, not a claim that it has been deployed.

## Provenance and current use

The coastline and cut mark were generated from the user-selected hybrid mockup with OpenAI ImageGen. The waves and aerial stills were generated with OpenAI ImageGen on **2026-09-11**, extending the same coastal visual direction. They are illustrative generated images. They do not document a real filming location, drone flight, customer project or captured shoot.

All three scene sources are RGB PNGs at 1672 × 941 pixels. Each has WebP derivatives at widths 640, 960, 1440 and 1672 under `web/public/demo`. The local MP4s were rendered as gentle zooms from these stills using FFmpeg. File inspection confirms H.264 at 1280 × 720 with no audio stream.

| Source | Application derivatives | Landing display entry | Duration and declared categories |
|---|---|---|---|
| `coast-source.png` | `coast-{640,960,1440,1672}.webp`, `coastal-study.mp4` | `Coastline_024.mp4` | 32 seconds; Coastline, Waves |
| `waves-source.png` | `waves-{640,960,1440,1672}.webp`, `waves-study.mp4` | `Waves_017.mp4` | 16 seconds; Coastline, Waves |
| `aerial-source.png` | `aerial-{640,960,1440,1672}.webp`, `aerial-study.mp4` | `Coastline_031.mp4` | 16 seconds; Coastline, Aerials |

The display filenames and “Coastal shoot” title are example metadata declared in `web/components/landing.tsx`. Its category buttons and text search filter that metadata locally. They do not call Gemini, classify the sample at runtime or read a private workspace. The page identifies the library as an example and the footage as illustrative. Playback requires a user action. The authenticated product uses separately persisted AI observations for real category assignments.

`frame-1.webp` through `frame-12.webp` are retained thumbnails extracted from the earlier coastal study for the superseded editing-oriented demonstration. The canonical landing now uses the three scene thumbnails above rather than a trimming filmstrip. Keeping these files is not a claim that the earlier editing-first product hierarchy remains current.

The original coast/mark prompt text is preserved below as provenance, including its earlier video-review wording and requested dimensions. Those requests differ from the actual source dimensions recorded above. No verbatim prompt transcript for the waves/aerial generation is stored in this directory; this note records their generation provenance without reconstructing missing prompt text.

## Brand and type

- `mark-source.png`: generated RGBA PNG at 1254 × 1254. Transparent outer padding was trimmed using visible alpha bounds before resizing. The app uses `web/public/brand/mark.png`; favicon derivatives have a light background. The image supplies the mark while the wordmark is HTML text.
- Typeface: Inter Variable from the rsms/inter distribution. The local application files are `web/app/fonts/InterVariable.woff2` and `web/app/fonts/Inter-LICENSE.txt`.

## Original coast prompt — historical wording

Create a single production raster asset extracted/recreated faithfully from the large coastal photograph in the attached RUSHES mockup. Full-bleed cinematic photograph ONLY, no UI, no labels, no frames, no text, no logo. Target 1920x1080 landscape16:9. Preserve the rugged dark rock shoreline, sunlit cliff at left, far coast fading into mist, rocky sea stacks across center-right, delicate white surf, blue-gray ocean, pale sky and soft natural late-afternoon sunshine. Closest possible match to the attached viewer image, with believable photographic detail and subtle color. The asset will fill the main footage viewer of a premium video-review product. Do not include any mockup border, playback bar, filmstrip or typography. This is an illustrative generated sample image.

## Original mark prompt

Create a single production logo ASSET faithfully matching only the black geometric R mark at upper-left of the attached RUSHES mockup. Transparent background, PNG with alpha. No wordmark or letters other than the abstract mark, no page/UI, no presentation board, no text captions. Target1024x1024 square, the mark centered with 8%padding, crisp flat solid near-black #101116 shapes, accurate clean edges. The mark is an abstract R built from a top rounded bowl and a lower angular foot, separated by one clear diagonal negative-space cut from upper-left toward lower-right. Reproduce the reference mark's silhouette and optical balance closely; do not turn it into a conventional font R, generic play icon, filmstrip, clapperboard, ribbon flourish or enclosing tile. Flat vector-like professional brand identity, no gradients, no shadows, no texture, no simulated paper. This standalone mark will be used at24px beside an HTML 'rushes' wordmark and as the favicon. Preserve transparency throughout the outside and diagonal cut.
