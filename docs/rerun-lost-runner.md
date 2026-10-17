# Rerun lost runners

`rerun-lost-runner.yml` reruns each job that lost its self-hosted runner or timed out.
An evicted, drained or hard-killed runner pod is lost; a failing test is not.

## Rules

### Retried

| Signal | Job ends | Annotation |
| --- | --- | --- |
| **Gone** | `failure` | "lost communication with the server" |
| **Shutdown** | `failure` | "received a shutdown signal" |
| **Drained or default-grace pod delete** | `failure` | "The operation was canceled." |
| **Timeout** | `cancelled` | "exceeded the maximum execution time" |

Default-grace `kubectl delete pod <runner>` reproduced the drained signal in [infra run 38125850620](https://github.com/RSI-Software/infra/actions/runs/38125850620/job/114429940060): step `cancelled`, job `failure`.
The match uses the job conclusion; a `cancelled` job with only the bare cancellation annotation is not retried.

### Not retried

- **Real failure:** the run stays red
- **Deliberate cancel:** a user or newer run
- **Fail-fast sibling:** reruns with its run
- **Consecutive losses:** lost/shutdown twice

The guard compares the job's last two actual executions, ignoring carried-over workflow attempts.
Lost and shutdown signals count together; timeout and drain signals do not trigger this guard.

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
- **OOM:** repeated lost/shutdown stops at 2
- **Cap:** other retriable signals stop at 3
- **Runner:** GitHub-hosted, a minute per call
- **Real failures:** a rerun never hides them

A single node loss still gets a retry.
Repeated loss can instead mean a deterministic memory-limit kill: [promptletariat run 38997884442](https://github.com/RSI-Software/promptletariat/actions/runs/38997884442) lost `verify` on all three attempts at the 8 GiB `ci` limit.
Timeouts and drained pods retain their existing retries because their annotations do not identify this repeated lost/shutdown pattern.

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
