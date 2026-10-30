"""Execute the shared action's comparison script, without a config snapshot."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACTION = (ROOT / "actions/stack-lint/action.yml").read_text()
SCRIPT = ACTION.split("        script: |\n", 1)[1]
SCRIPT = "\n".join(line[10:] for line in SCRIPT.splitlines())
# Synthetic policy exercises behavior; no copied RSI rules live in this repo.
CANONICAL = json.loads(Path(os.environ["RSI_STACK_CONFIG"]).read_text()) if "RSI_STACK_CONFIG" in os.environ else {
    "rules": {
        "no-restricted-globals": ["error", {"name": "ExampleRuntime", "message": "policy"}],
        "no-restricted-imports": ["error", {"paths": [{"name": "example-api", "message": "policy"}],
                                              "patterns": [{"group": ["@example/*"], "message": "policy"}]}],
        "example/future-rule": "error",
    }
}


def compare(local, inherited=None):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "stack-lint.json").write_text(json.dumps(local))
        (folder / "base.json").write_text(json.dumps(inherited or {}))
        harness = """
const canonical = %s;
const github = {rest: {repos: {getContent: async (request) => {
  if (JSON.stringify(request) !== JSON.stringify({owner: "RSI-Software", repo: "rsi", path: "stack.oxlintrc.json", ref: "main"})) throw Error("wrong source");
  return {data: {sha: "test-source", content: Buffer.from(JSON.stringify(canonical)).toString("base64")}};
}}}};
const core = {info: console.log, setFailed: message => {console.error(message); process.exitCode = 1;}};
(async () => { %s })().catch(error => {console.error(error); process.exitCode = 1;});
""" % (json.dumps(CANONICAL), SCRIPT)
        return subprocess.run(["node", "-e", harness], capture_output=True, text=True,
                              env={**os.environ, "RUNNER_TEMP": directory, "STACK_CONFIG": str(folder / "vite.config.ts")})


class StackLint(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bun"), "Bun is required by caller repositories")
    def test_loads_caller_config(self):
        loader = ACTION.split("      run: |\n", 1)[1].split("    - name:", 1)[0]
        loader = "\n".join(line[8:] for line in loader.splitlines())
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"lint": CANONICAL}))
            result = subprocess.run(["bash", "-euo", "pipefail", "-c", loader], capture_output=True, text=True,
                                    env={**os.environ, "STACK_CONFIG": str(config), "RUNNER_TEMP": directory})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((Path(directory) / "stack-lint.json").read_text()), CANONICAL)

    def test_aligned_and_inherited(self):
        for local, inherited in [(CANONICAL, None), ({"extends": [CANONICAL]}, None),
                                 ({"extends": ["./base.json"]}, CANONICAL)]:
            with self.subTest(local=local):
                result = compare(local, inherited)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Stack lint aligned:", result.stdout)

    def test_drift_fails(self):
        local = copy.deepcopy(CANONICAL)
        del local["rules"]["no-restricted-imports"]
        result = compare(local)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Stack lint drift: no-restricted-imports", result.stderr)
        print(result.stderr.strip())

    def test_weakened_or_removed_options_fail(self):
        for replacement in ["off", "warn", ["error", {"paths": [], "patterns": []}]]:
            local = copy.deepcopy(CANONICAL)
            local["rules"]["no-restricted-imports"] = replacement
            self.assertEqual(compare(local).returncode, 1)

        local = copy.deepcopy(CANONICAL)
        local["rules"]["no-restricted-imports"][1]["paths"][0]["importNames"] = ["only-one-export"]
        self.assertEqual(compare(local).returncode, 1)

    def test_local_bans_messages_aliases_and_exemptions(self):
        local = copy.deepcopy(CANONICAL)
        imports = local["rules"].pop("no-restricted-imports")
        imports[0] = 2
        imports[1]["paths"] = [item["name"] for item in imports[1]["paths"]] + ["local-only"]
        for pattern in imports[1]["patterns"]:
            pattern["message"] = "local wording"
            pattern["group"].append("@local/*")
        local["rules"]["eslint/no-restricted-imports"] = imports
        local["overrides"] = [{"files": ["cli/**"], "rules": {"no-restricted-imports": "off"}}]
        result = compare(local)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_future_rule_and_inherited_override(self):
        name = next(iter(CANONICAL["rules"]))
        local = {"extends": [CANONICAL], "rules": {name: "off"}}
        self.assertEqual(compare(local).returncode, 1)
        local = copy.deepcopy(CANONICAL)
        del local["rules"][name]
        self.assertEqual(compare(local).returncode, 1)


if __name__ == "__main__":
    unittest.main()
