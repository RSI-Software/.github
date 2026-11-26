# CI

How to set up a workflow on rsi-k3s runners.
Lane sizes, slots, and memory live in [`capacity.yaml`][capacity], with the reasons beside each lane.
Live cost per job: HQ's [Jobs](https://hq.rsi.nz/jobs).

## Checklist

**A new repo starts** from the [`ci.yml` starter](../workflow-templates/ci.yml) on the org's New workflow page.
It meets this list beside the [actionlint](actionlint.md), [PR title](pr-title.md), and [rerun](rerun-lost-runner.md) callers.

Every workflow that starts a runner pod:

1. Repo variable **`RSI_CI_RUNNER=ci`**
2. **One job**, with one checkout and one install
3. The **smallest [lane](#lanes)** that fits
4. **`timeout-minutes`** about **3× the job's p50**
5. Triggers, cancel, skips from [**snippets**](#snippets)
6. **Baked [toolchain](#toolchain)** versions
7. **Shallow checkout**; fetch only the base
8. A [**rerun caller**](rerun-lost-runner.md)
9. Title lint by [**PR title**](pr-title.md), not CI
10. Workflow lint by [**actionlint**](actionlint.md)
11. The stack lint [**drift check**](stack-lint.md)
12. Test workers at the lane's [**cap**](#test-workers)
13. `runs-on` **starts with** [`inputs.runner`](#bench)

Org variables never reach private repos on GitHub Free, so each repo sets its own.
Split a job only when part of it needs a different lane.
The shared actionlint workflow **warns on drift** from this list: [policy](actionlint.md#policy).

## Lanes

| Lane | Use when | Docker |
| --- | --- | --- |
| `ci` | default | no |
| `ci-docker` | the job runs `docker` | yes |
| `ci-docker-heavy` | it outgrows `ci-docker`'s store | yes |
| `ci-heavy` | working set over 4 GiB | no |
| `ci-e2e` | a browser suite against a Docker stack | yes |
| `ci-urgent` | the job fixes or unblocks CI | no |

**Start on `ci`**; move a job only on **evidence** from its HQ job page.

- RAM p90 over 4 GiB: **`ci-heavy`**
- Killed at `ci`'s limit: **fix the leak first**
- Needs a Docker daemon: **`ci-docker`**
- Browsers and Docker: **`ci-e2e`**, that job alone
- Only builds an image: **`ci` and node BuildKit**

Every lane but `ci` has **few slots**: a long job there **queues every other repo**.
Keep lint, typecheck, and title checks out of heavy jobs.

## Memory

Pods have no swap, so a job over its limit dies.

- **Process RAM and tmpfs pages** both count
- **`_work`, `/tmp`, `~/.local`** are tmpfs
- So **checkout and `node_modules` cost RAM**
- Lane **limits and `_work` caps**: [capacity][capacity]

A killed pod reports "The self-hosted runner lost communication with the server", never an out-of-memory error.
Fix it at the cause:

- **Cap [test workers](#test-workers)** per lane
- **Close databases and servers** each test opens
- **Link or reuse `node_modules`**, never copy

## Test workers

Runners see the **whole node**: `nproc` prints the node's cores, not the pod's.
Test runners size their pool from it, so **set the cap**.

| Lane | Cap |
| --- | --- |
| `ci`, `ci-urgent` | 4 |
| `ci-docker` | 3 |
| `ci-heavy` | 8 |

- **RAM limit** sets the cap
- A worker costs **up to 1.5 GiB**
- **No CPU limit**, so extra workers **take others' cores**
- **Child processes** share the cap
- **Suites at once** split it

| Runner | Default | Set |
| --- | --- | --- |
| Vitest | cores − 1 | `maxWorkers: 4` |
| `bun test --parallel` | cores | `--parallel=4` |
| Playwright | cores ÷ 2 | `workers: process.env.CI ? 2 : undefined` |

## Disk

Runner nodes use **consumer SSDs**.
The lanes point caches at tmpfs; a job that overrides them writes to disk.

| Path | Where |
| --- | --- |
| `_work`, `/tmp`, `~/.local` | RAM |
| `XDG_CACHE_HOME`, npm, `GOPATH` | RAM, under `~/.local` |
| Python and Go toolcache, apt | RAM |
| Node toolcache, `~/.bun` | disk |
| dind `/var/lib/docker` | RAM |

- **Never override** Go and XDG cache paths
- **`no-cache: true` forces** a download
- **Unbaked versions download** to disk every run
- **`actions/cache` costs** RAM and time
- **Upload artifacts** on `main`, only if read

## Toolchain

The runner image's [`Dockerfile`](https://github.com/RSI-Software/rsi/blob/main/infra/managed/rsi-k3s/runner-image/Dockerfile) **pins what it bakes**.
Any other version **downloads every run**.

- `gh` is **not baked**
- A tool **every run installs** belongs in the [image]
- **Pin setup actions** to baked, or drop them
- `setup-bun` **reads `packageManager`**
- **`rsi dev toolchain`** lists every pin that misses it

`XDG_CACHE_HOME` alone hides the image's Chromium; keep `PLAYWRIGHT_BROWSERS_PATH`.

## Timeouts and reruns

The [rerun caller](rerun-lost-runner.md) retries lost runners and timeouts, up to 3 runs.

- With **no timeout**, a hang holds a slot **6 h, 3 times**
- A **deterministic failure** repeats on rerun
- **Fix or quarantine** a flaky test

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

- A **false or filtered job `if:`** starts **no pod**
- A **false step `if:`** still **starts the pod**
- A **cancel frees** the pod when the run stops

Prefer job-level skips; step-level only inside the always-on job.

### Merges

A head is green only when a check succeeded.

- **All skipped**, or no checks, is **not green**
- A **`workflow_run` check** is **not proof**
- **Required checks** are **unenforced** on GitHub Free

A rerun caller is a `workflow_run` trigger.
So one cheap job runs on every ready PR and succeeds; never path-filter its `pull_request` trigger.

## Footguns

- **Cancel on `main`** drops deploys mid-run
- **Any pushed branch** runs code on our runners
- **Secrets reach** any pushed branch
- A deploy **gates on CI status**, never reruns CI
- **Hosted runners bill** private repos
- **Rerun callers** run hosted, so **bill too**
- The next lane deploy **reverts a manual ARC patch**
- **Re-enabling** a disabled workflow **restores cost**
- **Workflow text in tests** breaks on CI edits

## Snippets

### Bench

A `runner` dispatch input, first in every `runs-on`, lets [`ci:bench`](https://github.com/RSI-Software/rsi/blob/main/infra/docs/rsi-k3s.md#ci-bench) time the same jobs on each machine:

```yaml
  workflow_dispatch:
    inputs:
      runner:
        description: Lane every job runs on, such as ci-exp-magma; empty keeps each job's own
        type: string
```

```yaml
    runs-on: ${{ inputs.runner || fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')['ci'] || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
```

- **Push and PR runs** leave the input **empty**
- A **dispatch deploy skips** given `inputs.runner`

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

- **`ready_for_review` reruns** draft-skipped jobs
- **No `edited`**, as title lint runs elsewhere
- The **workflow name** blocks **cross-workflow cancels**
- A **`main` push** never **cancels**

A job that reads the title keeps `edited`, unfiltered.
A body-edit skip cancels a real run and its skipped check hides an earlier failure.

### Draft and stack skip

```yaml
  verify:
    timeout-minutes: 10
    if: >-
      !github.event.pull_request.draft &&
      (github.event.pull_request.stack == null ||
       github.event.pull_request.stack.position == github.event.pull_request.stack.size)
```

- The **top stack layer** runs for every layer
- **Push and dispatch** carry no `pull_request`, so **run**
- **AND an existing `if:`**, in parentheses

### Docs-only scope

One step in the always-on job decides; `code=true` means run everything.

```yaml
  verify:
    runs-on: ${{ inputs.runner || fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')['ci'] || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
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

A job on another lane skips without a pod:

```yaml
  test:
    needs: verify
    if: needs.verify.outputs.code == 'true'
```

- **Tested docs are code**; narrow the exclude
- **Shipped prompts** are **code** too
- A **moved base over-includes**; it fails open

### `main` push

```yaml
  push:
    branches: [main]
    paths-ignore: [docs/**, '*.md']
```

Keep it in step with the scope excludes.

### `runs-on`

```yaml
ci:        ${{ fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')['ci'] || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-docker: ${{ fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')['ci-docker'] || vars.RSI_CI_RUNNER == 'ci' && 'ci-docker' || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-heavy:  ${{ fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')['ci-heavy'] || vars.RSI_CI_RUNNER == 'ci' && 'ci-heavy' || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
ci-urgent: ${{ fromJSON(vars.RSI_CI_RUNNER == 'ci' && vars.RSI_CI_ROUTE || '{}')[vars.RSI_CI_URGENT || vars.RSI_CI_RUNNER] || vars.RSI_CI_URGENT || vars.RSI_CI_RUNNER || 'ubuntu-latest' }}
```

Each lane reads its **overflow route first**; the [policy](actionlint.md#policy) fails a `runs-on` that skips it.
A repo overflows once k3s-hq's collector lists it in `REPOS`.

Detail: [rsi-k3s routing](https://github.com/RSI-Software/rsi/blob/main/infra/docs/rsi-k3s.md#routing).

### Image builds

Node BuildKit, no Docker daemon: [rsi-k3s BuildKit](https://github.com/RSI-Software/rsi/blob/main/infra/docs/rsi-k3s.md#buildkit).

[capacity]: https://github.com/RSI-Software/rsi/blob/main/infra/managed/rsi-k3s/capacity.yaml

[image]: https://github.com/RSI-Software/rsi/blob/main/infra/docs/rsi-k3s.md#runner-image
