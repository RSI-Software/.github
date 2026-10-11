"""Execute the workflow's real Bash/jq with fixture Buildah, registry and kubectl."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/k3s-deploy.yml"
REGISTRY = "192.168.1.231:5002"
APP = "rsi-pr-agent"
REF = f"{REGISTRY}/{APP}:new"
OLD = f"{REGISTRY}/{APP}:old"


def script(name):
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index("      - name: " + name)
    start = next(i for i in range(start, len(lines)) if lines[i] == "        run: |") + 1
    body = []
    for line in lines[start:]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:])
    return "\n".join(body)


MOCK = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
tool = pathlib.Path(sys.argv[0]).name
p = pathlib.Path(os.environ["FIXTURE"])
s = json.loads(p.read_text())
s["calls"].append([tool] + args)
def finish(code=0):
    p.write_text(json.dumps(s))
    sys.exit(code)
if tool == "sudo":
    assert args[0] == "/usr/bin/buildah", args
    command = args[1]
    if command == "bud":
        s["store"].append(args[args.index("-t") + 1])
    elif command == "push":
        s["registry"].append(args[-2])
    elif args[2] == "--force":
        if args[-1] in s["store"]: s["store"].remove(args[-1])
    elif args[2] == "--prune":
        s["store"] = []
    if s.get("fail") == command or s.get("fail") == args[-1]: finish(1)
    finish()
if tool == "curl":
    repo, tag = args[-1].split("/v2/")[1].split("/manifests/")
    finish(0 if f"{os.environ['REGISTRY']}/{repo}:{tag}" in s["registry"] else 22)
if args[:2] == ["kubectl", "create"]:
    print(json.dumps({"kind": "List", "items": s["raw"]}))
    finish()
args = args[1:]
if args[:1] == ["-n"]: args = args[2:]
if args[0] == "get":
    if s.get("fail") == "get": finish(1)
    if args[1] == "deployment": print(json.dumps(s["deployment"]))
    elif args[1] == "replicasets": print(json.dumps({"items": s["replicasets"]}))
    elif args[1] == "pods": print(json.dumps({"items": s["pods"]}))
    else: finish(2)
elif args[0] == "patch": s["patch"] = json.loads(args[-1])
elif args[0] == "apply": s.setdefault("applied", []).append(sys.stdin.read())
elif args[:2] == ["rollout", "undo"]: s["undo"] = args[-1]
else: finish(2)
finish()
'''


def deployment(ref=REF, revision="12"):
    return {"kind": "Deployment", "metadata": {"name": "server", "uid": "server",
            "annotations": {"deployment.kubernetes.io/revision": revision}},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "server"}},
                     "template": {"spec": {"containers": [{"name": "server", "image": ref}]}}}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="k3s-test-")
        self.dir = Path(self.tmp.name)
        self.fixture = self.dir / "fixture.json"
        previous = deployment(OLD, "11")
        previous["metadata"]["ownerReferences"] = [{"uid": "server", "kind": "Deployment", "controller": True}]
        self.state = {"calls": [], "store": [], "registry": [OLD], "raw": [],
                      "deployment": deployment(), "replicasets": [previous]}
        binary = self.dir / "sudo"
        binary.write_text(MOCK)
        binary.chmod(0o755)
        for tool in ("k3s", "curl"):
            (self.dir / tool).symlink_to(binary)
        self.env = dict(os.environ, PATH=str(self.dir) + ":" + os.environ["PATH"],
                        FIXTURE=str(self.fixture), RUNNER_TEMP=str(self.dir), REGISTRY=REGISTRY,
                        SHA="new", NAMESPACE="ns", DEPLOYMENTS='["server"]', HEALTH="[]",
                        MANIFESTS="", HAS_MANIFESTS="false")
        (self.dir / "k3s-deployments.txt").write_text("ns server\n")
        (self.dir / "k3s-revisions.txt").write_text("ns server 11\n")
        (self.dir / "k3s-configmaps.jsonl").write_text('{"kind":"ConfigMap","metadata":{"name":"config"}}\n')
        self.resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def run_step(self, name, expected=0):
        self.fixture.write_text(json.dumps(self.state))
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", script(name)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.state = json.loads(self.fixture.read_text())
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def resolve(self, images=None):
        self.env["IMAGES"] = json.dumps(images or [{"repository": "docker.io/library/" + APP}])
        self.run_step("Resolve the images")
        return json.loads((self.dir / "k3s-images.json").read_text())

    def test_repository_aliases(self):
        for repo in (APP, "docker.io/library/" + APP, f"{REGISTRY}/{APP}", "ghcr.io/team/app"):
            with self.subTest(repo=repo):
                image = self.resolve([{"repository": repo}])[0]
                self.assertEqual(image["ref"], f"{REGISTRY}/{'team/app' if repo.startswith('ghcr.io') else APP}:new")

    def test_build_push_and_cleanup(self):
        self.resolve([{"repository": APP, "dockerfile": "deploy/Dockerfile", "context": "src",
                       "build-args": "COMMIT=new\nMODE=prod"}])
        self.run_step("Build and push the images")
        self.assertIn(REF, self.state["registry"])
        calls = [c[2:] for c in self.state["calls"] if c[0] == "sudo"]
        self.assertEqual(calls[1], ["push", "--authfile", "/etc/k3s-deploy/registry-auth.json", REF, "docker://" + REF])
        self.assertEqual(calls[0], ["bud", "--isolation=chroot", "--build-arg", "COMMIT=new",
                                  "--build-arg", "MODE=prod", "-f", "deploy/Dockerfile", "-t", REF, "src"])
        self.run_step("Clean the build store")
        self.assertEqual(self.state["store"], [])
        self.assertEqual([c[2:] for c in self.state["calls"][-2:]], [["rmi", "--force", REF], ["rmi", "--prune"]])

    def test_failed_build_or_push_still_cleans(self):
        for command in ("bud", "push"):
            with self.subTest(command=command):
                self.state["fail"] = command
                self.run_step("Build and push the images", 1)
                self.run_step("Clean the build store")
                self.assertEqual(self.state["store"], [])
        self.assertIn("if: always() && steps.build.outcome", WORKFLOW.read_text())

    def test_cleanup_failure_still_prunes(self):
        self.run_step("Build and push the images")
        self.state["fail"] = REF
        self.run_step("Clean the build store", 1)
        self.assertEqual(self.state["calls"][-1][2:], ["rmi", "--prune"])

    def test_explicit_tag_skip_and_missing_rebuild(self):
        self.resolve([{"repository": APP, "tag": "old"}])
        self.run_step("Build and push the images")
        self.assertFalse(any(c[0] == "sudo" for c in self.state["calls"]))
        self.assertIn("application/vnd.oci.image.manifest", self.state["calls"][-1][-2])
        self.state["registry"] = []
        self.run_step("Build and push the images")
        self.assertIn(OLD, self.state["registry"])

    def test_render_unpinned_aliases_and_explicit_tags(self):
        self.resolve([{"repository": APP}, {"repository": APP + "-sandbox", "tag": "old"}])
        obj = deployment()
        pod = obj["spec"]["template"]["spec"]
        pod["containers"] = [{"image": r + ":stale", "imagePullPolicy": "Never"}
                             for r in (APP, "docker.io/library/" + APP, f"{REGISTRY}/{APP}")]
        pod["containers"].append({"image": "other:old", "imagePullPolicy": "Never"})
        pod["initContainers"] = [{"image": APP + "-sandbox:any"}]
        self.state["raw"] = [obj]
        self.env["MANIFESTS"] = 'printf "{}" > "$K3S_DEPLOY_OUT/app.json"'
        self.run_step("Render the manifests")
        result = json.loads((self.dir / "k3s-all.json").read_text())[0]["spec"]["template"]["spec"]
        self.assertEqual(result["containers"][:3], [{"image": REF, "imagePullPolicy": "IfNotPresent"}] * 3)
        self.assertEqual(result["containers"][3], pod["containers"][3])
        self.assertEqual(result["initContainers"][0]["image"], f"{REGISTRY}/{APP}-sandbox:old")
        self.assertNotIn("nodeSelector", result)

    def test_deployment_only_apply_is_idempotent(self):
        self.run_step("Apply")
        self.assertEqual(self.state["patch"]["spec"]["template"]["spec"]["containers"][0],
                         {"name": "server", "image": REF, "imagePullPolicy": "IfNotPresent"})

    def test_rollback_registry_present_missing_and_legacy(self):
        self.run_step("Roll back on failure")
        self.assertEqual(self.state.pop("undo"), "--to-revision=11")
        self.state.pop("applied")
        for ref in (OLD, "docker.io/library/" + APP + ":old"):
            with self.subTest(ref=ref):
                self.state["registry"] = []
                self.state["replicasets"][0]["spec"]["template"]["spec"]["containers"][0]["image"] = ref
                result = self.run_step("Roll back on failure", 1)
                self.assertIn("unavailable in registry", result.stdout)
                self.assertNotIn("undo", self.state)
                self.assertNotIn("applied", self.state)

    def test_rollback_init_container_and_ambiguous_history(self):
        self.state["replicasets"][0]["spec"]["template"]["spec"]["initContainers"] = [{"image": REF}]
        self.run_step("Roll back on failure", 1)
        self.state["replicasets"] *= 2
        self.run_step("Roll back on failure", 1)
        self.assertNotIn("undo", self.state)

    def test_verify_ignores_terminal_pods(self):
        live = {"metadata": {}, "spec": {"containers": [{"image": REF}]},
                "status": {"phase": "Running", "containerStatuses": [{"ready": True}]}}
        self.state["pods"] = [live] + [{"status": {"phase": p}} for p in ("Failed", "Succeeded")]
        self.run_step("Verify the running pods")
        self.state["pods"][0]["status"]["containerStatuses"][0]["ready"] = False
        self.run_step("Verify the running pods", 1)

    def test_rollback_read_failure_preserves_configmaps(self):
        self.state["fail"] = "get"
        self.run_step("Roll back on failure", 1)
        self.assertNotIn("undo", self.state)
        self.assertNotIn("applied", self.state)

    def test_prune_failure_surfaces(self):
        self.run_step("Build and push the images")
        self.state["fail"] = "--prune"
        self.run_step("Clean the build store", 1)

    def test_verify_zero_replicas_and_explicit_tag(self):
        self.state["deployment"]["spec"]["replicas"] = 0
        self.run_step("Verify the running pods")
        self.resolve([{"repository": APP, "tag": "old"}])
        self.state["deployment"]["spec"]["replicas"] = 1
        self.state["deployment"]["spec"]["template"]["spec"]["containers"][0]["image"] = OLD
        self.state["pods"] = [{"metadata": {}, "spec": {"containers": [{"image": OLD}]},
                               "status": {"phase": "Running", "containerStatuses": [{"ready": True}]}}]
        self.run_step("Verify the running pods")

    def test_workflow_shell_syntax_and_no_node_route(self):
        text = WORKFLOW.read_text()
        for name in (line.removeprefix("      - name: ") for line in text.splitlines() if line.startswith("      - name:")):
            if name == "Check out the commit under deploy": continue
            result = subprocess.run(["bash", "-n"], input=script(name), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        for old in ("k3s ctr", "K3S_DEPLOY_NODE", "BUILDAH_ROOT", "io.cri-containerd.pinned"):
            self.assertNotIn(old, text)


if __name__ == "__main__":
    unittest.main()
