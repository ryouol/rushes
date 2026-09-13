# Documentation

## Start here

| Document | Purpose |
| --- | --- |
| [Project README](../README.md) | Product, live demo, screenshots, setup, and code entry points |
| [Architecture](ARCHITECTURE.md) | Runtime, data flow, trust boundaries, and tradeoffs |
| [Development](DEVELOPMENT.md) | Local configuration, tests, storage, and troubleshooting |
| [Contributing](../CONTRIBUTING.md) | Changes, validation, and review expectations |
| [Security](../SECURITY.md) | Private reporting and handling sensitive material |
| [Google authentication](GOOGLE-AUTH.md) | OAuth setup and identity/session design |
| [Hosting](HOSTING.md) | Container operation, public build configuration, and backups |

## Deployment and engineering evidence

[Deployment inventory](deployment-inventory.json) records the last inspected runtime and resource configuration. It is a dated record, not a live health probe. The [live app](https://rushes.onrender.com) and [CI](https://github.com/ryouol/rushes/actions/workflows/ci.yml) are linked separately.

Useful examples of investigated changes:

- [Export memory](EXPORT-MEMORY-REVIEW.md): production incident, measured encoder tradeoff, real-source verification.
- [Static frontend](STATIC-FRONTEND-REVIEW.md): removing the production Node process and testing HTTP/lifecycle behavior.
- [Search repair](SEARCH-REPAIR-REVIEW.md): retrieval behavior and regression evidence.
- [Google sign-in](validation/production-google-deployment.json): real provider connection and returning-login checks.

## Historical records

The remaining `*-REVIEW.md` files, [phase checklist](IMPLEMENTATION.md), [goal audit](GOAL-AUDIT.md), [production history](PRODUCTION.md), [design studies](design), and [validation artifacts](validation) preserve development decisions and evidence. Their model choices, plans, costs, pending work, and test counts describe the stated revision. Later records may supersede them; do not use an old report as current setup instructions or a current performance claim.

Design studies include concepts as well as implemented screenshots. The curated [README screenshots](screenshots/README.md) identify the actual application captures used on the public repository homepage.
