# actionlint

`actionlint.yml` lints a repository's workflows with [actionlint](https://github.com/rhysd/actionlint).

## Rules

- **Pinned, sha256-verified** actionlint and shellcheck
- **shellcheck** lints each **`run:` script**
- **SC2016 off**, as single quotes are intended
- Runs on the **`ci` [lane](ci.md#runs-on)**
- Lints the caller's **`.github/workflows/`**
- **Skips drafts** and lower native-stack layers

The pins live in [`actionlint.yml`](../.github/workflows/actionlint.yml).

## Caller

Each repository calls it from its own file, never a job in `ci.yml`.

- Lives at **`.github/workflows/actionlint.yml`**
- Triggers on **workflow file changes** only
- **`ready_for_review`** runs a draft-skipped lint
- **Never** a **required check**
- Pushes on the **default branch**

```yaml
name: actionlint
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths: [.github/workflows/**, .github/actionlint.yaml]
  push:
    branches: [main]
    paths: [.github/workflows/**, .github/actionlint.yaml]
permissions: {}
jobs:
  actionlint:
    uses: RSI-Software/.github/.github/workflows/actionlint.yml@main
    permissions:
      contents: read
```

This repository holds the reusable at that path, so its `ci.yml` is the caller.

## Self-hosted labels

actionlint refuses unknown runner labels.
List the repository's own labels in `.github/actionlint.yaml`:

```yaml
self-hosted-runner:
  labels: [ci, ci-heavy]
```

## Policy

After the lint, a Bun script **warns on drift** from the [CI checklist](ci.md#checklist).
It reads parsed workflows and **evaluates job `if:` and `cancel-in-progress`** under a draft PR, a lower stack layer, and a `main` push.

| Rule | Item | Warns when |
| --- | --- | --- |
| `runner-var` | 1 | `RSI_CI_RUNNER` is not `ci` |
| `one-job` | 2 | two jobs install on one lane |
| `lane` | 3 | `runs-on` hard-codes a lane |
| `route` | 3 | a lane skips its overflow route |
| `hosted` | 3 | GitHub-hosted, no exception |
| `host` | 3 | outside rsi-k3s, no exception |
| `timeout` | 4 | a job lacks `timeout-minutes` |
| `no-edited` | 5 | `edited` without a title read |
| `main-cancel` | 5 | a `main` push cancels |
| `skip-draft-stack` | 5 | a draft or lower layer starts a pod |
| `shallow` | 7 | `fetch-depth: 0` or `--unshallow` |
| `rerun` | 8 | the rerun caller misses a workflow |
| `pr-title` | 9 | no shared PR title caller |
| `commitlint` | 9 | a step, config, or dependency |
| `actionlint` | 10 | no shared actionlint caller |
| `stack-lint` | 11 | lint config, no stack-lint step |
| `k3s-pin` | | k3s-deploy below the minimum SHA |

- **Fails** only on a rule in `FAIL`
- **A crash** never fails a caller
- The **script** holds **`FAIL`** and the k3s pin floor

A **written exception** is a comment anywhere in the workflow file:

```yaml
# ci-policy: allow host reruns must start when every rsi-k3s runner is lost
```

Only `hosted` and `host` take one.
