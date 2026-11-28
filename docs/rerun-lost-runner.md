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

A **default-grace** `kubectl delete pod <runner>` gives the **drained signal**: step `cancelled`, job `failure`.
The match uses the **job conclusion**; a `cancelled` job with only the bare cancellation annotation is **not retried**.

### Not retried

- A **real failure**: the run stays red
- A **deliberate cancel** by a user or newer run
- A **fail-fast sibling**; it reruns with its run
- A job **lost or shut down twice** in a row

The guard compares the job's last two actual executions, ignoring carried-over workflow attempts.
Lost and shutdown signals count together; timeout and drain signals do not trigger this guard.

### Rerun

- At most **3 runs** per job
- **30 seconds** before each rerun
- The **step summary** lists each decision

### Mixed runs

GitHub reruns one job per request, only once the run finishes.

1. A failed run, **all lost**, gets one **`--failed` rerun**
2. Otherwise, **one lost job** per attempt
3. A **carried-over job** is judged where it last ran

`--failed` would also rerun a deliberate cancel.

## Why

- **Pressure kills** a runner first; a rerun is safe
- A **timeout** means a hung test or a hard-killed pod
- **Repeated loss** may be an **OOM kill**: stops at 2
- **Other retriable signals** stop at **3**
- Runs on **Blacksmith**, a minute per call
- A rerun **never hides** a real failure

## Caller

Add one file per repository and name each watched workflow:

```yaml
# .github/workflows/rerun-lost-runner.yml
name: Rerun lost runners
on:
  workflow_run:
    workflows: [CI, PR title, actionlint]
    types: [completed]
permissions:
  actions: write
  checks: read
jobs:
  rerun:
    uses: RSI-Software/.github/.github/workflows/rerun-lost-runner.yml@main
```

`workflow_run` reads the caller from the default branch only.
