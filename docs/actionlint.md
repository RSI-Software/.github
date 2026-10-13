# actionlint

`actionlint.yml` lints a repository's workflows with [actionlint](https://github.com/rhysd/actionlint).

## Rules

- **Pin:** v1.7.12, sha256-verified
- **shellcheck:** v0.11.0, on each `run:` script
- **SC2016:** off; single quotes are intended
- **Runner:** `RSI_CI_RUNNER`, else `ubuntu-latest`
- **Scope:** `.github/workflows/` of the caller
- **Skips:** drafts and lower native-stack layers

## Caller

Each repository calls it from its own file, never a job in `ci.yml`.

- **Path:** `.github/workflows/actionlint.yml`
- **Trigger:** workflow file changes only
- **`ready_for_review`:** runs a draft-skipped lint
- **Required check:** never
- **Branch:** the repository's default

```yaml
name: actionlint
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths: [.github/workflows/**, .github/actionlint.yaml]
  push:
    branches: [main]
    paths: [.github/workflows/**, .github/actionlint.yaml]
permissions: {}
jobs:
  actionlint:
    uses: RSI-Software/.github/.github/workflows/actionlint.yml@main
    permissions:
      contents: read
```

This repository holds the reusable at that path, so its `ci.yml` is the caller.

## Self-hosted labels

actionlint refuses unknown runner labels.
List the repository's own labels in `.github/actionlint.yaml`:

```yaml
self-hosted-runner:
  labels: [ci, ci-heavy]
```
