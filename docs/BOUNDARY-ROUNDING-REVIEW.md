# Final timestamp rounding review

Gemini returned 14.007 seconds for a source ending at 14.006667 seconds. This rejected both otherwise valid observations. The parser now refines only a millisecond-aligned endpoint at most 500 microseconds past the chunk boundary. Other invalid ranges still fail. Original proposed timestamps and the complete provider response remain separate from the refined playable range.

## Simplify findings

1. **[P2] Mark the database regression as integration**, `tests/test_organization.py:452`. The new test used the authenticated PostgreSQL fixture without the neighboring integration marker, so excluding integration tests would still access a database. **Fixed:** added `@pytest.mark.integration` before committing. Reuse and efficiency reviews reported no findings.

## Final code review

The testing, breaking changes, context, and change size reviewers returned no additional findings. The 110-line application/test change is one coherent fix. No PR exists; no GitHub comments or label were posted.

## Validation

57 targeted inference, organization, provider-contract and recovery tests passed in a disposable PostgreSQL database. The database was removed. Tests cover the real rounding boundary, 500/501-microsecond limits, non-millisecond overshoots, invalid starts, source-duration rejection, preserved proposed timestamps, unmodified raw evidence and measured usage, and idempotent application without provider dispatch. The marker-only follow-up does not change test behavior when the isolated suite runs without a marker filter.

Previously failed windows require deliberate operator recovery from their retained responses. They are not automatically regenerated or silently marked successful.
