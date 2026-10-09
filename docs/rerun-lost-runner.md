# Rerun lost runners

`rerun-lost-runner.yml` reruns each failed job that lost its self-hosted runner.
An evicted, OOM-killed or drained runner pod is lost; a failing test is not.

## Rules

### Lost

- **Gone:** "lost communication with the server"
- **Shutdown:** "received a shutdown signal"
- **Drained:** "canceled", without a timeout

### Rerun

- **Per job:** only lost jobs rerun
- **Real failure:** never rerun; the run stays red
- **Cap:** attempt 3 is the last
- **Summary:** each decision, in the step summary

### Mixed runs

GitHub reruns one job per request, only once the run finishes.

1. All failed jobs lost: one `--failed` rerun
2. Lost beside real: one lost job per attempt
3. Carried-over job: judged where it last ran

## Why

- **Pressure kills:** CI yields to services
- **Not the change's fault:** so a rerun is safe
- **OOM counts as lost:** the annotation can't tell
- **Cap:** a job that always OOMs stops at 3
- **Runner:** GitHub-hosted; skips bill nothing
- **Real failures:** a rerun never hides them

### Gap

A runner killed without grace times out instead.
That run ends `cancelled` and is not rerun.

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
