"""Run actionlint.yml's real CI policy script with Bun against in-memory caller repositories."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/actionlint.yml").read_text()
SCRIPT = "\n".join(line[10:] for line in WORKFLOW.split("<<'JS'\n", 1)[1].split("\n          JS\n", 1)[0].splitlines())
SHARED = "RSI-Software/.github/.github/workflows/"


def caller(name, reusable, on=None):
    return {"name": name, "on": on or {"pull_request": None}, "jobs": {"call": {"uses": SHARED + reusable + "@main"}}}


ALIGNED = {
    # The org starter, beside the callers it names, warns nothing.
    "ci.yml": (ROOT / "workflow-templates/ci.yml").read_text(),
    "pr-title.yml": caller("PR title", "pr-title.yml", {"pull_request": {"types": ["opened", "edited"]}}),
    "actionlint.yml": caller("actionlint", "actionlint.yml"),
    "rerun-lost-runner.yml": {
        "name": "Rerun lost runners",
        "on": {"workflow_run": {"workflows": ["CI", "PR title", "actionlint"], "types": ["completed"]}},
        "jobs": {"rerun": {"uses": SHARED + "rerun-lost-runner.yml@main"}},
    },
    "hosted.yml": "# ci-policy: allow hosted needs macOS\n" + json.dumps(
        {"on": {"schedule": [{"cron": "0 0 * * *"}]},
         "jobs": {"mac": {"runs-on": "macos-15", "timeout-minutes": 5, "steps": [{"run": "true"}]}}}),
}

DRIFTED = {
    "ci.yml": {
        "on": {"pull_request": {"types": ["opened", "edited"]}, "push": None},
        "concurrency": {"group": "ci", "cancel-in-progress": True},
        "jobs": {
            "lint": {"runs-on": "ci", "steps": [
                {"uses": "actions/checkout@v5", "with": {"fetch-depth": 0}},
                {"uses": "actions/setup-node@v6", "with": {"node-version": 24}},
                {"run": "npm ci && npx commitlint --from HEAD~1"}]},
            "test": {"if": "!github.event.pull_request.draft", "runs-on": "ci", "timeout-minutes": 5,
                     "steps": [{"uses": "oven-sh/setup-bun@v2"}, {"run": "bun install"}]},
            "mac": {"runs-on": "macos-15", "timeout-minutes": 5, "steps": [{"run": "true"}]},
            "box": {"runs-on": ["self-hosted", "box"], "timeout-minutes": 5, "steps": [{"run": "true"}]},
            "deploy": {"uses": SHARED + "k3s-deploy.yml@main"},
        },
    },
}
RULES = {"runner-var", "one-job", "lane", "hosted", "host", "timeout", "no-edited", "main-cancel",
         "skip-draft-stack", "shallow", "rerun", "pr-title", "commitlint", "actionlint",
         "stack-lint", "k3s-pin"}


def policy(workflows, runner="ci"):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".github/workflows").mkdir(parents=True)
        for name, body in workflows.items():
            (root / ".github/workflows" / name).write_text(body if isinstance(body, str) else json.dumps(body))
        (root / "vite.config.ts").write_text("export default {}\n")
        script = root / "ci-policy.js"
        script.write_text(SCRIPT)
        env = {"PATH": os.environ["PATH"], "RSI_CI_RUNNER": runner, "GITHUB_REPOSITORY": "RSI-Software/example"}
        run = subprocess.run(["bun", str(script)], cwd=root, env=env, capture_output=True, text=True)
        return run.returncode, run.stdout + run.stderr


class CiPolicy(unittest.TestCase):
    def test_aligned_caller_warns_nothing(self):
        code, out = policy(ALIGNED)
        self.assertEqual((code, re.findall(r"^::\w+.*$", out, re.M)), (0, []), out)

    def test_each_rule_warns_on_drift_and_never_fails(self):
        code, out = policy(DRIFTED, runner="")
        self.assertEqual(code, 0, out)
        self.assertNotIn("::error", out)
        self.assertEqual(set(re.findall(r"^::warning.*title=ci-policy ([\w-]+)::", out, re.M)), RULES, out)


if __name__ == "__main__":
    unittest.main()
