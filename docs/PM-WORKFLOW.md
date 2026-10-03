# Weekly product improvement workflow

RUSHES has a weekly PM and delivery review, requested by the owner on October 3,
2026. Review evidence, pick one focused improvement, implement it, test it, and
ship through the existing GitHub and Render process. Record what actually shipped
and what remains blocked.

## Planning records

- [ChatGPT Space](https://chatgpt.com/space/page_6ac1872b5cf881918a16fba790747e80)
- [Notion product and delivery](https://app.notion.com/p/3ee69b28e04f81e6944dc338d9963f22)
- [Source repository](https://github.com/ryouol/rushes)
- [Live application](https://rushes.onrender.com)

The linked Space and Notion page summarize priorities and delivery. They do not
provide automatic two-way file synchronization or grant access to local code.
The repository remains the source of truth for implementation and test evidence.
Preserve edits in each planning record and reconcile current content before
updating it.

## Cadence and responsibility

The local ChatGPT automation `rushes-weekly-product-improvements` is scheduled for
Mondays at 09:00 America/Toronto in the originating chat. It is the single scheduled
owner of this workflow. Local execution requires the computer and app to be
available. A Dot may coordinate once connected; do not create a duplicate schedule
or have two agents edit the same change concurrently. The Space contains the Dot
handoff and [connection guidance](https://learn.chatgpt.com/docs/dots/computers-and-apps).
Saving that handoff does not activate a Dot.

## Each review

1. Read repository instructions, current code, open pull requests, recent failures,
   and available user feedback. Historical audits are leads to recheck.
2. Rank opportunities by user impact, confidence, implementation effort, and cost.
   Select one bounded change with an observable before/after acceptance criterion.
3. Implement and review the change. Preserve original media, human corrections,
   tenant isolation, provider provenance, and unrelated work.
4. Test relevant behavior with isolated synthetic data and paid providers disabled.
   Run required CI and build checks. Do not claim tests passed if they were skipped.
5. Create a focused pull request and ship through the existing deployment process
   when access and checks allow. Verify the running revision and relevant behavior;
   a push, merge, or build alone is not proof of deployment.
6. Update both planning records with the issue, behavior change, evidence, PR/commit,
   release status, and next priority. Notify the owner of meaningful results,
   failures, or decisions; remain quiet when nothing actionable changed.

The owner authorized implementation, builds, and shipment of improvements. Keep
the existing documented budget. Increasing paid resources, messaging customers,
deleting original data, or changing commercial/legal policy needs separate scope.
If credentials or a required decision are missing, finish a tested, reviewable
change and record the specific blocker.

## Initial backlog

1. Current evidence across search, worklog, surrounding context, and worklog exports.
2. Clear partial-analysis status and accurate recovery actions.
3. Reviewed category corrections that survive reanalysis.
4. Resumable imports with completed-file verification.
5. Verified account recovery.

This order is informed by the September 22–23 local audit, not by customer
interviews or a current production performance benchmark.

## Current evidence acceptance policy

Run-independent observations (including notes and transcripts), human-corrected
observations, and observations from the newest analysis attempt are current.
Newest means creation time followed by run ID to break ties. A running, partial,
or failed replacement does not silently reactivate older machine claims.

Default search, worklog pagination, nearby context, and JSON/CSV worklog exports
use this policy. The observations endpoint accepts `include_history=true` to
retrieve retained rows with a `superseded` flag. Direct context links to older
observations remain available and label their citation and evidence as superseded.
No rows, original files, provenance, saved collections, or revision history are
deleted. Whole-file category correction remains a separate backlog item.
