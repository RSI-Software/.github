"""Exercise the real rerun Bash with GitHub API fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LINES = (ROOT / ".github/workflows/rerun-lost-runner.yml").read_text().splitlines()
SCRIPT = "\n".join(line[10:] for line in LINES[LINES.index("        run: |") + 1:])
LOST = "The self-hosted runner lost communication with the server"
SHUTDOWN = "The runner has received a shutdown signal"
TIMEOUT = "The job exceeded the maximum execution time"
DRAIN = "The operation was canceled."
MOCK = '''#!/usr/bin/env python3
import json, os, sys
s = json.loads(os.environ["FIXTURE"])
a = sys.argv[1:]
if a[0] == "run" or "POST" in a:
    print("RERUN " + " ".join(a))
    sys.exit()
path = next(arg for arg in a if arg.startswith("repos/"))
if "/annotations" in path:
    print(s["annotations"][path.split("/")[-2]])
else:
    attempt = path.split("/attempts/")[1].split("/")[0]
    rows = s["attempts"][attempt]
    if path.endswith("/jobs"):
        for row in rows: print("\t".join(row if ".conclusion" in a[-1] else row[:2]))
    else: print(attempt)
'''


class RerunLostRunner(unittest.TestCase):
    def run_workflow(self, signals, carried=False, mixed=False):
        attempts, annotations = {}, {}
        for index, signal in enumerate(signals, 1):
            conclusion = "cancelled" if signal == TIMEOUT else "failure"
            attempts[str(index)] = [[str(index), "verify", conclusion]]
            annotations[str(index)] = signal
        if carried:
            # The middle workflow attempt ran another job, not verify.
            attempts["2"] = []
            annotations.pop("2")
        if mixed:
            attempts[str(len(signals))].append(["99", "other", "failure"])
            annotations["99"] = "Test assertion failed"
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "gh"
            binary.write_text(MOCK)
            binary.chmod(0o755)
            env = dict(os.environ, PATH=tmp + ":" + os.environ["PATH"],
                       FIXTURE=json.dumps({"attempts": attempts, "annotations": annotations}),
                       REPO="org/repo", RUN="1", ATTEMPT=str(len(signals)),
                       CONCLUSION="failure", RUN_URL="https://example.test/run/1",
                       DRY_RUN="false", GITHUB_STEP_SUMMARY=tmp + "/summary")
            run = subprocess.run(["bash", "-c", "sleep() { :; };\n" + SCRIPT],
                                 env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout

    def test_first_loss_retries(self):
        self.assertIn("RERUN run rerun", self.run_workflow([LOST]))

    def test_consecutive_loss_combinations_stop(self):
        for previous in (LOST, SHUTDOWN):
            for current in (LOST, SHUTDOWN):
                with self.subTest(previous=previous, current=current):
                    out = self.run_workflow([previous, current])
                    self.assertIn("consecutive runner losses", out)
                    self.assertNotIn("RERUN", out)

    def test_carried_attempt_does_not_reset_guard(self):
        out = self.run_workflow([LOST, "unused", SHUTDOWN], carried=True)
        self.assertIn("consecutive runner losses", out)
        self.assertNotIn("RERUN", out)

    def test_timeout_and_drain_still_retry(self):
        for previous, current in ((TIMEOUT, LOST), (DRAIN, LOST),
                                  (LOST, TIMEOUT), (LOST, DRAIN),
                                  (TIMEOUT, TIMEOUT), (DRAIN, DRAIN)):
            with self.subTest(previous=previous, current=current):
                self.assertIn("RERUN", self.run_workflow([previous, current]))

    def test_cap_remains_three_actual_runs(self):
        out = self.run_workflow([DRAIN] * 3)
        self.assertIn("ran 3 times", out)
        self.assertNotIn("RERUN", out)

    def test_real_failure_is_not_retried_with_lost_job(self):
        out = self.run_workflow([LOST], mixed=True)
        self.assertIn("RERUN api -X POST repos/org/repo/actions/jobs/1/rerun", out)
        self.assertNotIn("RERUN run rerun", out)


if __name__ == "__main__":
    unittest.main()
