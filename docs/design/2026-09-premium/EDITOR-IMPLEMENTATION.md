# Editor implementation slice

Status: implemented locally and TypeScript-checked. Parent workflow owns the required in-app browser comparison and full interaction/design QA; this is not a visual acceptance or deployment claim.

## Source and scope

The selected target is `concepts/04-refined-hybrid.png`. The built-in ImageGen adaptation, inspected before implementation, is `screens/04-review-editor.png`; its exact prompt is in `screens/04-review-editor-prompt.md`. Sample coastal footage and labels in that image are illustrative. Runtime imagery uses real authenticated media and extracted proxy frames.

Changed components: `web/components/project.tsx`, `player.tsx`, `asset-tools.tsx`, `settings.tsx`. Existing import and collection behavior was extracted into `import-dialog.tsx` and `collection-view.tsx`, reducing the project component. Added `review-timeline.tsx` and semantic-token styles in `editor.css`. Backend, package dependencies, production configuration and deployment are outside this slice.

## Implemented behavior and design constraints

- The footage library uses larger images, lighter regular headings, simpler metadata and fewer nested borders. Existing search cancellation, request identity checks, project events and true partial / retry states remain.
- The review viewer occupies the main surface. Worklog is optional, opening initially when arriving at a timestamped search result. One close control replaces two. The context panel stacks below the viewer at narrow widths. This applies Hick, Occam and Tesler to secondary information, and Proximity / Uniform Connectedness to the connected video, frame strip and range controls.
- The filmstrip samples ten actual decoded frames from the authenticated proxy and releases its media element on cleanup. Its accessible seek slider retains source-relative microsecond values. Native video transport and precise labeled In / Out inputs remain; a source-timing disclosure explains approximate browser seeking and source-frame export behavior. Targets are at least 44px, applying Fitts and Jakob to familiar playback and numeric controls.
- First Save creates a named Selects collection only on explicit submission, then saves the range. The returned collection ID is retained before item creation so item failure can retry against the same collection. Existing collections and full-source saves remain available. Saved searches are not offered as editable collection destinations. Duplicate submits are guarded; real success is announced briefly in place. This removes a first-save dead end and applies Peak-End, Zeigarnik and Doherty through immediate pending feedback and truthful completion.
- Import accepts actual dropped video files using the existing streaming upload endpoint. Folder import uses the file picker. Upload percentages remain real; status announcements summarize completion rather than every byte. Uploads retain their existing lifetime across in-app navigation, while stale view updates are ignored; the upload operation keeps beforeunload protection active until transfer finishes. Server-root indexing is disclosed only when roots exist; relinking is hidden on instances without configured roots. Privacy and processing-service disclosures remain before upload.
- Collection mutations, saved search, retry, cancellation, preview preparation, explicit export start and membership changes expose pending, error and success feedback. Existing source/range persistence and all export formats remain. Experimental interchange qualifications remain visible with those formats. Downloads become the emphasized action within the persisted export item.
- Appearance and credits precede measured activity, membership and advanced storage/processing diagnostics. No payment, invitation email, unavailable source root or backend capability was invented. This applies Miller / Pareto to common tasks and Serial Position / Von Restorff to primary actions.
- Player shortcuts ignore editable controls and any other open dialog; Space also respects native button, link and disclosure activation; reverse shuttle stops at the start of the source. Success feedback and color transitions respect the shared reduced-motion setting.

## Verification handoff

`npm run typecheck` passed after coherent implementation and formatting. An independent bounded correctness spot-check found upload unmount cancellation and overly broad button shortcut suppression; both were corrected before handoff. Browser verification must cover desktop and 390px mobile, Light / Dark / System, Worklog open/closed, real frame extraction, numeric edits and seek, first-collection Save and retry recovery, nested export dialog keyboard isolation, explicit export start/completion/download, upload/drop/error states, source-root absence, owner/editor/viewer actions, and settings disclosures. Compare the same viewport/state against the selected editor study before marking visual QA passed.

No additional design or legal TODO markers were introduced by this slice. Existing operator-content needs are owned by the public-site workflow.
