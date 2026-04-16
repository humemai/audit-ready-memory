# Release Workflow

Documentation deployment is versioned with `mike`.

## Build checks

Non-tag pushes and pull requests build the docs site in CI to catch navigation and Markdown errors.

## Deployment

- Pushing a tag matching `v*` deploys a versioned docs build.
- Manual workflow dispatch can also deploy a selected version.
- The deployed site is published under `https://docs.humem.ai/audit-ready-memory/`.

## Version aliases

Tagged releases can be published as `latest` through the deploy workflow, matching the pattern used in other HumemAI docs repositories.