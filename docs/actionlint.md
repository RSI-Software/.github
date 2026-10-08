# actionlint

`actionlint.yml` lints a repository's workflows with [actionlint](https://github.com/rhysd/actionlint).

## Rules

- **Pin:** v1.7.12, sha256-verified
- **shellcheck:** v0.11.0, on each `run:` script
- **Runner:** `RSI_CI_RUNNER`, else `ubuntu-latest`
- **Scope:** `.github/workflows/` of the caller

## Caller

Add one job to the repository's CI workflow:

```yaml
jobs:
  actionlint:
    uses: RSI-Software/.github/.github/workflows/actionlint.yml@main
    permissions:
      contents: read
```

## Self-hosted labels

actionlint refuses unknown runner labels.
List the repository's own labels in `.github/actionlint.yaml`:

```yaml
self-hosted-runner:
  labels: [ci, ci-heavy]
```
