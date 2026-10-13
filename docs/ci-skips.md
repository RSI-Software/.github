# CI skips

Every job that starts a self-hosted runner pod writes to rsi-k3s consumer SSDs ([infra#204](https://github.com/RSI-Software/infra/issues/204)).
Skip work a change cannot affect, but keep one check that succeeds.

## Rules

| Change | Pattern | Runner pod |
| --- | --- | --- |
| Newer PR push | cancel the superseded run | freed mid-run |
| Draft PR | every job: job `if:` | none |
| Lower stack layer | code jobs: job `if:` | none |
| PR title or body edit | no `edited` in CI types | none |
| Docs only, one job | step `if:` on scope | one, no toolchain |
| Docs only, several jobs | light gate job, job `if:` on scope | gate only |
| Docs only, `main` push | `push.paths-ignore` | none |
| Any job | smallest lane that fits | lane-sized |

## Merges

`ghb pr merge` lands a head only when a check succeeded.

- **All skipped:** refused; lower layers excepted
- **No checks:** refused unless triggers exclude it
- **`workflow_run` trigger:** that proof fails
- **Required checks:** unenforced on GitHub Free

A `rerun-lost-runner.yml` caller is a `workflow_run` trigger.
So one cheap job runs on every ready PR and succeeds; never path-filter its `pull_request` trigger.

## Cost

- **Workflow filter, job `if:` false:** no pod
- **Step `if:` false:** pod starts, step skipped
- **Cancel:** pod freed when the run stops

Prefer job-level skips; step-level only inside the always-on job.

## Snippets

### Triggers and cancel

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

- **`ready_for_review`:** reruns draft-skipped jobs
- **No `edited`:** title lint runs elsewhere
- **Workflow in group:** no cross-workflow cancels
- **`main`:** never cancels

### Draft and stack skip

```yaml
  verify:
    if: >-
      !github.event.pull_request.draft &&
      (github.event.pull_request.stack == null ||
       github.event.pull_request.stack.position == github.event.pull_request.stack.size)
```

- **Stack:** the top layer runs for every layer
- **Push, dispatch:** no `pull_request`, so they run
- **Existing `if:`:** AND it, in parentheses

Policy: [infra decisions](https://github.com/RSI-Software/infra/blob/main/docs/decisions.md).

### Docs-only scope

One step in the always-on job decides; `code=true` means run everything.

```yaml
  verify:
    runs-on: ${{ vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
    outputs:
      code: ${{ steps.scope.outputs.code }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 2
      # The whole change: a stack from its base, a PR from its base, a push from
      # its previous head. A missing base or a git error runs everything.
      - id: scope
        env:
          BASE: ${{ github.event.pull_request.stack.base.sha || github.event.pull_request.base.sha || github.event.before }}
        run: |
          code() { echo "code=true" >> "$GITHUB_OUTPUT"; exit 0; }
          [ "$GITHUB_EVENT_NAME" != workflow_dispatch ] && [ -n "${BASE//0/}" ] || code
          git cat-file -e "$BASE^{commit}" 2>/dev/null ||
            git fetch -q --no-tags --depth=1 origin "$BASE" || code
          git diff --quiet --no-renames "$BASE" HEAD -- . ':(exclude)docs/' ':(exclude)*.md' || code
      # Always-on checks here, such as the secret scan and commit lint.
      - if: steps.scope.outputs.code
        run: bun install --frozen-lockfile
```

Further jobs skip without a pod:

```yaml
  test:
    needs: verify
    if: needs.verify.outputs.code == 'true'
```

- **Tested docs:** code; narrow the exclude
- **Shipped prompts:** code too
- **Moved base:** over-includes; fails open

### `main` push

```yaml
  push:
    branches: [main]
    paths-ignore: [docs/**, '*.md']
```

Keep it in step with the scope excludes.

### PR title lint

Its own `pr-title.yml` runs on `edited`, so prose fixes never rerun CI.
Call the shared workflow: [PR title](pr-title.md).

### Lanes

| Lane | When | `runs-on` |
| --- | --- | --- |
| `ci` | default | `${{ vars.RSI_CI_RUNNER \|\| 'ubuntu-latest' }}` |
| `ci-docker` | job runs Docker | `${{ vars.RSI_CI_RUNNER == 'ci' && 'ci-docker' \|\| vars.RSI_CI_RUNNER \|\| 'ubuntu-latest' }}` |
| `ci-heavy` | over 4 GiB | `${{ vars.RSI_CI_RUNNER == 'ci' && 'ci-heavy' \|\| vars.RSI_CI_RUNNER \|\| 'ubuntu-latest' }}` |
| `ci-urgent` | fixes or unblocks CI | `${{ vars.RSI_CI_URGENT \|\| vars.RSI_CI_RUNNER \|\| 'ubuntu-latest' }}` |

- **Docker-in-Docker:** only `ci-docker`, `ci-heavy`
- **Slots:** `ci-docker` 2, `ci-heavy` 5

Detail: [rsi-k3s routing](https://github.com/RSI-Software/infra/blob/main/docs/rsi-k3s.md#routing).

## In use

| Repo | Pattern |
| --- | --- |
| [infra](https://github.com/RSI-Software/infra/blob/main/.github/workflows/ci.yml) | step skip in one `verify` job |
| [vtwo-proto](https://github.com/RSI-Software/vtwo-proto/blob/main/.github/workflows/ci.yml) | one `verify` job, stack skip |
| [vone](https://github.com/RSI-Software/vone/blob/main/.github/workflows/ci.yml) | gate job, job skips |
| [rsi-pr-agent](https://github.com/RSI-Software/rsi-pr-agent/blob/main/.github/workflows/ci.yml) | step skip, `main` paths-ignore |
