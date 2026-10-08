# Rerun lost runners

`rerun-lost-runner.yml` reruns a failed run's failed jobs when every one lost its self-hosted runner.
An evicted, OOM-killed or drained runner pod is lost; a failing test is not.

## Rules

- **Trigger:** a watched workflow fails
- **Lost:** "lost communication with the server"
- **Also lost:** "received a shutdown signal"
- **Mixed failures:** no rerun; a human reads it
- **Cap:** attempt 3 is the last
- **Runner:** GitHub-hosted; skips bill nothing

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
