# CI

How to set up a workflow on rsi-k3s runners.
Lane sizes and the reasons behind them live in infra: [`capacity.yaml`](https://github.com/RSI-Software/infra/blob/main/managed/rsi-k3s/capacity.yaml), [decisions](https://github.com/RSI-Software/infra/blob/main/docs/decisions.md).
Live cost per job: [ci-ledger](https://k3s.rsi.nz).

## Checklist

Every workflow that starts a runner pod:

1. **Repo variable:** `RSI_CI_RUNNER=ci`
2. **One job:** one checkout, one install
3. **Lane:** smallest that fits; [Lanes](#lanes)
4. **`timeout-minutes`:** about 3× the job's p50
5. **Triggers, cancel, skips:** [Snippets](#snippets)
6. **Toolchain:** baked versions; [here](#toolchain)
7. **Checkout:** shallow; fetch only the base
8. **Rerun caller:** [rerun](rerun-lost-runner.md)
9. **Title lint:** [PR title](pr-title.md), not CI
10. **Workflow lint:** [actionlint](actionlint.md)

Org variables never reach private repos on GitHub Free, so each repo sets its own.
Split a job only when part of it needs a different lane.

## Lanes

| Lane | Use when | Slots | Docker |
| --- | --- | --- | --- |
| `ci` | default | 24 | no |
| `ci-docker` | the job runs `docker` | 2 | yes |
| `ci-heavy` | working set over 4 GiB | 5 | yes |
| `ci-urgent` | the job fixes or unblocks CI | 2 | no |

Start on `ci`; move a job only on evidence from its ledger page.

- **RAM p90 over 4 GiB:** `ci-heavy`
- **Killed at the 8 GiB limit:** fix the leak first
- **Needs a Docker daemon:** `ci-docker`
- **Needs both:** `ci-heavy`
- **Only builds an image:** `ci` and node BuildKit

`ci-docker` and `ci-heavy` have few slots: a long job there queues every other repo.
Keep lint, typecheck, and title checks out of heavy jobs.

## Memory

Pods have no swap, so a job over its limit dies.

- **Counted:** process RAM and tmpfs pages
- **tmpfs:** `_work`, `/tmp`, `~/.local`
- **So:** checkout and `node_modules` cost RAM
- **`ci`:** 2 GiB request, 8 GiB limit
- **`ci-heavy`:** 5.5 GiB request, 18 GiB limit
- **`_work` cap:** 3 GiB `ci`, 8 GiB `ci-heavy`

A killed pod reports "The self-hosted runner lost communication with the server", never an out-of-memory error.
Fix it at the cause:

- **Test workers:** cap them, child processes too
- **Engines per test:** close databases, servers
- **`node_modules`:** link or reuse, never copy

## Disk

Runner nodes use consumer SSDs ([infra#204](https://github.com/RSI-Software/infra/issues/204)).
The lanes point caches at tmpfs; a job that overrides them writes to disk.

| Path | Where |
| --- | --- |
| `_work`, `/tmp`, `~/.local` | RAM |
| `XDG_CACHE_HOME`, npm, `GOPATH` | RAM, under `~/.local` |
| Python and Go toolcache, apt | RAM |
| Node toolcache, `~/.bun` | disk |
| dind `/var/lib/docker` | RAM |

- **Never override:** Go and XDG cache paths
- **`no-cache: true`:** forces a download
- **Unbaked versions:** download to disk every run
- **`actions/cache`:** costs RAM and time
- **Artifacts:** upload on `main`, only if read

## Toolchain

The runner image bakes these; any other version downloads every run:

- **Node:** 24.21.0
- **Bun:** 1.4.2
- **Playwright:** 1.63.0, with Chromium
- **Docker Compose**

Not baked: `gh`, `bzip2`, `ffmpeg`, `tmux`.
A tool every run installs belongs in the [image](https://github.com/RSI-Software/infra/blob/main/docs/runbooks/rsi-k3s.md#runner-image).
Pin setup actions to the baked version, or drop them.
`XDG_CACHE_HOME` alone hides the image's Chromium; keep `PLAYWRIGHT_BROWSERS_PATH`.

## Timeouts and reruns

The [rerun caller](rerun-lost-runner.md) retries lost runners and timeouts, up to 3 runs.

- **No timeout:** a hang holds a slot 6 h, 3 times
- **Deterministic failure:** reruns repeat it
- **Flaky test:** fix or quarantine it

## Skips

Skip work a change cannot affect, but keep one check that succeeds.

| Change | Pattern | Runner pod |
| --- | --- | --- |
| Newer PR push | cancel the superseded run | freed mid-run |
| Draft PR | every job: job `if:` | none |
| Lower stack layer | code jobs: job `if:` | none |
| PR title or body edit | no `edited` in CI types | none |
| Docs only, one job | step `if:` on scope | one, no toolchain |
| Docs only, several jobs | gate job, job `if:` on scope | gate only |
| Docs only, `main` push | `push.paths-ignore` | none |

- **Job `if:` false or filtered:** no pod
- **Step `if:` false:** pod starts anyway
- **Cancel:** pod freed when the run stops

Prefer job-level skips; step-level only inside the always-on job.

### Merges

`ghb pr merge` lands a head only when a check succeeded.

- **All skipped:** refused; lower layers excepted
- **No checks:** refused unless triggers exclude it
- **`workflow_run` trigger:** that proof fails
- **Required checks:** unenforced on GitHub Free

A rerun caller is a `workflow_run` trigger.
So one cheap job runs on every ready PR and succeeds; never path-filter its `pull_request` trigger.

## Footguns

- **Cancel on `main`:** drops deploys mid-run
- **Any pushed branch:** runs code on our runners
- **Secrets:** reach any pushed branch
- **Deploy re-running CI:** gate on CI status
- **Hosted runners:** bill private repos
- **Rerun callers:** run hosted, so bill too
- **Manual ARC patch:** next lane deploy reverts it
- **Disabled workflow:** re-enabling restores cost
- **Workflow text in tests:** breaks on CI edits

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
    timeout-minutes: 10
    if: >-
      !github.event.pull_request.draft &&
      (github.event.pull_request.stack == null ||
       github.event.pull_request.stack.position == github.event.pull_request.stack.size)
```

- **Stack:** the top layer runs for every layer
- **Push, dispatch:** no `pull_request`, so they run
- **Existing `if:`:** AND it, in parentheses

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
      # Always-on checks here, such as the secret scan.
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

### `runs-on`

```yaml
ci:        ${{ vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-docker: ${{ vars.RSI_CI_RUNNER == 'ci' && 'ci-docker' || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-heavy:  ${{ vars.RSI_CI_RUNNER == 'ci' && 'ci-heavy' || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-urgent: ${{ vars.RSI_CI_URGENT || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
```

Detail: [rsi-k3s routing](https://github.com/RSI-Software/infra/blob/main/docs/rsi-k3s.md#routing).

### Image builds

Node BuildKit, no Docker daemon: [rsi-k3s BuildKit](https://github.com/RSI-Software/infra/blob/main/docs/runbooks/rsi-k3s.md#buildkit).

## In use

Each repo's `.github/workflows/ci.yml`:

- **infra:** step skip in one `verify` job
- **rsi-pr-agent:** step skip, `main` paths-ignore
- **vone:** gate job, job skips
- **web-tools:** one small job, baked toolchain

