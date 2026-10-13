# PR title

`pr-title.yml` lints a pull-request title as its squash commit header.
One `github-script` step: no checkout, no install.

## Rule

`type(scope)!: subject`; scope and `!` are optional.

- **Types:** build, ci, chore, docs, feat, fix
- **More types:** perf, refactor, revert, test
- **Scopes:** the caller's `scopes` input, if set
- **Subject:** no trailing period or space
- **Length:** `<title> (#N)` at most 72 characters

A set `scopes` input makes a scope required.
`!` marks a breaking change; no body footer is linted.

## Runs

- **Runner:** `RSI_CI_RUNNER`, else `ubuntu-latest`
- **Drafts:** skipped, no runner
- **Edits:** run only when the title changed
- **Stacks:** every layer; it is cheap

## Caller

The workflow name must stay `PR title`: `rerun-lost-runner.yml` matches it.

```yaml
name: PR title
on:
  pull_request:
    types: [opened, edited, reopened, synchronize, ready_for_review]
permissions: {}
concurrency:
  group: pr-title-${{ github.event.pull_request.number }}${{ github.event.action == 'edited' && github.event.changes.title.from == null && '-skipped' || '' }}
  cancel-in-progress: true
jobs:
  pr-title:
    uses: RSI-Software/.github/.github/workflows/pr-title.yml@main
    with:
      scopes: api ci deps docs ui
```

The `-skipped` group keeps a body edit from cancelling a running check.
Omit `with:` to allow any scope or none.
