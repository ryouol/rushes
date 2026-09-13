# Security

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/ryouol/rushes/security/advisories/new). Do not disclose exploitable details or credentials in public issues or pull requests.

Include the affected revision, reproduction steps, impact, and a minimal synthetic example. Redact credentials, cookies, personal data, and provider payloads. Do not test against other users' workspaces or run destructive/load tests on the live instance.

## Scope and expectations

The current development branch is `codex/production`. This is an actively developed project, without a published security-response SLA or long-term support schedule. Public deployment does not establish that every input, workload, or hosting configuration is qualified.

The implementation uses separate database owner/runtime roles, workspace RLS, authenticated media access, configured source roots, and server-side provider credentials. These controls should be evaluated with their tests; they are not a blanket security certification.

## Sensitive material

Never commit `.env`, runtime credentials, private keys, session tokens, database backups, or users' original footage. Local storage and test artifacts belong under ignored paths. Prefer synthetic fixtures for public reports.

If a real credential is exposed, revoke or rotate it with its provider. Removing it from the current file does not remove it from Git history. Coordinate any history rewrite with the repository owner rather than force-pushing shared history unannounced.

## Repository checks

Run `gitleaks git --redact` for a history scan and `uv run python scripts/audit_local.py` for configured-value/source-bundle checks. The seven exact fingerprints in `.gitleaksignore` are reviewed false positives: source-file SHA-256 values in `docs/validation/shared-runtime.json`. No whole file or rule is excluded. A clean scan is useful evidence, not a complete security review.
