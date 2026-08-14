# Release Workflow

Documentation deployment is versioned with `mike`.

## Build checks

Non-tag pushes and pull requests build the docs site in CI to catch navigation and Markdown errors.

## Deployment

- Pushing a tag matching `v*` deploys a versioned docs build and points the `latest` alias at
  it. Nothing on the published site changes until a tag is pushed.
- Manual workflow dispatch can also deploy a selected version, with `latest` as a choice.
- The deployed site is published under `https://docs.humem.ai/audit-ready-memory/`, and the
  current version is at [`/latest/`](https://docs.humem.ai/audit-ready-memory/latest/). Link
  to the `latest` path from outside the docs; the bare prefix redirects, but paths below it
  such as `/audit-ready-memory/guide/memory-model/` do not resolve.

## Version aliases

Tagged releases can be published as `latest` through the deploy workflow, matching the pattern used in other HumemAI docs repositories.