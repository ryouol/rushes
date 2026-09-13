# Contributing and reviewing

Start with the [README](README.md) and [architecture guide](docs/ARCHITECTURE.md). Use the [development guide](docs/DEVELOPMENT.md) for local services and tests. There is no shared account or production credential for contributors.

## Proposing a change

For a bug, include the expected behavior, actual result, reproduction steps, environment, and a small synthetic fixture when possible. Avoid uploading private footage, `.env` files, database dumps, session cookies, or raw provider responses. Use [private reporting](SECURITY.md) for vulnerabilities.

Keep changes focused on one behavior. Describe the concrete before/after result, relevant validation, and remaining limits in the pull request. Separate unrelated refactors from the fix. Include migration and recovery implications when changing persisted state or external effects.

## Boundaries to preserve

- Authenticate access and maintain workspace isolation in both routes and database operations.
- Preserve original media and source timing; keep derived files and exports separate.
- Retain provider provenance and human corrections. Do not silently convert uncertain external outcomes into safe retries.
- Bound model inputs, job concurrency, and resource use. Do not add paid calls to ordinary CI.
- Use generated local configuration and the non-owner runtime database role.

Run the checks relevant to your change and report what you actually ran. Frontend routing/layout changes should include a browser check; media/timing changes need representative boundary fixtures. See [CI](.github/workflows/ci.yml) and [test instructions](docs/DEVELOPMENT.md#verification).

`web/AGENTS.md` contains repository-specific frontend guidance. Historical review documents are evidence, not instructions to override a contributor's task or access permissions.

## License status

No general reuse license has been selected. Do not assume that public visibility grants permission to redistribute the code, screenshots, or source footage. Contributions and any future licensing terms should be agreed with the repository owner before submitting substantial work.
