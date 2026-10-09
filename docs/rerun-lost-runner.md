# Rerun lost runners

`rerun-lost-runner.yml` reruns each job that lost its self-hosted runner or timed out.
An evicted, drained or hard-killed runner pod is lost; a failing test is not.

## Rules

### Retried

| Signal | Job ends | Annotation |
| --- | --- | --- |
| **Gone** | `failure` | "lost communication with the server" |
| **Shutdown** | `failure` | "received a shutdown signal" |
| **Drained** | `failure` | "The operation was canceled." |
| **Timeout** | `cancelled` | "exceeded the maximum execution time" |

### Not retried

- **Real failure:** the run stays red
- **Deliberate cancel:** a user or newer run
- **Fail-fast sibling:** reruns with its run

### Rerun

- **Cap:** 3 runs per job
- **Delay:** 30 seconds before each rerun
- **Summary:** each decision, in the step summary

### Mixed runs

GitHub reruns one job per request, only once the run finishes.

1. Failed run, all lost: one `--failed` rerun
2. Otherwise: one lost job per attempt
3. Carried-over job: judged where it last ran

`--failed` would also rerun a deliberate cancel.

## Why

- **Pressure kills:** CI yields; a rerun is safe
- **Timeout:** a hung test or a hard-killed pod
- **OOM:** no filter; judged by its signal
- **Cap:** an always-lost job stops at 3
- **Runner:** GitHub-hosted, a minute per call
- **Real failures:** a rerun never hides them

## Caller

Add one file per repository and name each watched workflow:

```yaml
# .github/workflows/rerun-lost-runner.yml
name: Rerun lost runners
on:
  workflow_run:
    workflows: [CI]
    types: [completed]
permissions:
  actions: write
  checks: read
jobs:
  rerun:
    uses: RSI-Software/.github/.github/workflows/rerun-lost-runner.yml@main
```

`workflow_run` reads the caller from the default branch only.
