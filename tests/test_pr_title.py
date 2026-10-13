"""Run pr-title.yml's real github-script rule under Node with a stub `core`."""
import os
from pathlib import Path
import subprocess
import unittest

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/pr-title.yml").read_text()
LINES = WORKFLOW.splitlines()
START = LINES.index("          script: |") + 1
SCRIPT = "\n".join(line[12:] for line in LINES[START:] if not line or line.startswith(" " * 12))
HARNESS = """
const core = {
  setFailed: (message) => { console.log(message); process.exitCode = 1; },
  info: (message) => console.log(message),
};
(async () => {
%s
})();
"""


def lint(title, number=12, scopes=""):
    env = {"TITLE": title, "NUMBER": str(number), "SCOPES": scopes, "PATH": os.environ["PATH"]}
    run = subprocess.run(["node", "-e", HARNESS % SCRIPT], env=env, capture_output=True, text=True)
    return run.returncode, run.stdout.strip()


class PrTitle(unittest.TestCase):
    def test_passes(self):
        for title, scopes in [
            ("fix: keep the queue warm", ""),
            ("feat(ui)!: drop the legacy grid", ""),
            ("ci(deps): pin bun", "deps, ci"),
            ("revert: undo the cache", ""),
        ]:
            with self.subTest(title=title):
                self.assertEqual(lint(title, scopes=scopes)[0], 0)

    def test_refuses(self):
        for title, scopes, reason in [
            ("Fix the queue", "", "expected `type(scope)!: subject`"),
            ("fix:missing space", "", "expected"),
            ("fix: trailing space ", "", "expected"),
            ("style: tabs", "", "type `style`"),
            ("fix(): empty", "", "scope is empty"),
            ("fix: no scope", "ui api", "scope must be one of: ui, api"),
            ("fix(db): wrong scope", "ui,api", "scope must be one of"),
            ("fix: ends with a period.", "", "period"),
        ]:
            with self.subTest(title=title):
                code, out = lint(title, scopes=scopes)
                self.assertEqual(code, 1)
                self.assertIn(reason, out)

    def test_header_counts_the_pr_number(self):
        title = "fix: " + "x" * 61  # 66 characters
        self.assertEqual(lint(title, number=1)[0], 0)  # 66 + " (#1)" = 71
        code, out = lint(title, number=1234)  # 66 + " (#1234)" = 74
        self.assertEqual(code, 1)
        self.assertIn("is 74 characters", out)

    def test_title_arrives_through_env(self):
        self.assertIn("TITLE: ${{ github.event.pull_request.title }}", WORKFLOW)
        self.assertNotIn("${{", SCRIPT)


if __name__ == "__main__":
    unittest.main()
