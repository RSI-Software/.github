"""Execute the workflow's real Bash, jq and Bun with fixture docker and curl."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/k3s-deploy.yml"
REGISTRY = "192.168.1.231:5002"
SHA = "a" * 40
DIGEST = "sha256:" + "d" * 64


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
stdin = "" if sys.stdin.isatty() else sys.stdin.read()
s["calls"].append({"tool": tool, "args": args, "stdin": stdin})
def finish(code=0):
    p.write_text(json.dumps(s))
    sys.exit(code)
if tool == "docker":
    if args[:2] == ["buildx", "build"]:
        meta = args[args.index("--metadata-file") + 1]
        pathlib.Path(meta).write_text(json.dumps({"containerimage.digest": s["digest"]}))
    finish()
if "audience=k3s-hq" in args[-1]:
    print(json.dumps({"value": "oidc-token"}))
    finish()
pathlib.Path(args[args.index("-D") + 1]).write_text(f"HTTP/1.1 100 Continue\\r\\n\\r\\nHTTP/1.1 {s['status']} X\\r\\n")
for line in s["reply"]:
    print(json.dumps(line))
finish(s.get("exit", 0))
'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="k3s-test-")
        self.dir = Path(self.tmp.name)
        self.fixture = self.dir / "fixture.json"
        self.state = {"calls": [], "digest": DIGEST, "status": 200, "reply": []}
        mock = self.dir / "docker"
        mock.write_text(MOCK)
        mock.chmod(0o755)
        (self.dir / "curl").symlink_to(mock)
        (self.dir / "registry").mkdir()
        (self.dir / "registry/config.json").write_text("{}")
        self.env = dict(os.environ, PATH=str(self.dir) + ":" + os.environ["PATH"], FIXTURE=str(self.fixture),
                        RUNNER_TEMP=str(self.dir), REGISTRY=REGISTRY, APP="shop", SHA=SHA,
                        GITHUB_REF="refs/heads/main", GITHUB_STEP_SUMMARY=str(self.dir / "summary"),
                        RSI_REGISTRY_CONFIG=str(self.dir / "registry"), RELEASES="https://k3s.example/api/releases",
                        ACTIONS_ID_TOKEN_REQUEST_URL="https://token.example/?v=1",
                        ACTIONS_ID_TOKEN_REQUEST_TOKEN="request-token")

    def tearDown(self):
        self.tmp.cleanup()

    def run_step(self, name, expected=0):
        self.fixture.write_text(json.dumps(self.state))
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", script(name)], env=self.env,
                                capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        self.state = json.loads(self.fixture.read_text())
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def check(self, images, expected=0):
        self.env["IMAGES"] = json.dumps(images)
        out = self.run_step("Check the inputs", expected)
        return out if expected else json.loads((self.dir / "k3s-images.json").read_text())

    def test_inputs(self):
        for repo in ("shop", "docker.io/library/shop", f"{REGISTRY}/shop"):
            self.assertEqual(self.check([{"repository": repo}])[0]["repository"], "shop")
        self.assertIn("carries no tag", self.check([{"repository": "shop:latest"}], 2))
        self.env["GITHUB_REF"] = "refs/heads/feature"
        self.assertIn("only refs/heads/main", self.check([{"repository": "shop"}], 2))

    def test_build_pushes_the_commit_tag_with_the_registry_cache(self):
        self.check([{"repository": "shop", "dockerfile": "deploy/Dockerfile", "context": "src",
                     "build-args": "COMMIT=x\nMODE=prod"}])
        self.run_step("Build and push the images")
        build = next(c["args"] for c in self.state["calls"] if c["args"][:2] == ["buildx", "build"])
        ref = f"{REGISTRY}/shop"
        self.assertEqual(build[2:9], ["src", "--file", "deploy/Dockerfile", "--build-arg", "COMMIT=x",
                                      "--build-arg", "MODE=prod"])
        self.assertIn(f"type=registry,ref={ref}:cache,registry.insecure=true", build)
        self.assertIn(f"type=registry,ref={ref}:cache,mode=max,image-manifest=true,oci-mediatypes=true,"
                      "registry.insecure=true,ignore-error=true", build)
        self.assertIn(f"type=image,name={ref}:{SHA},push=true,registry.insecure=true", build)
        self.assertEqual(json.loads((self.dir / "k3s-built.jsonl").read_text()),
                         {"repository": "shop", "digest": DIGEST})

    def render(self, manifests, expected=0):
        self.env["MANIFESTS"] = textwrap.dedent(manifests)
        (self.dir / "k3s-built.jsonl").write_text(json.dumps({"repository": "shop", "digest": DIGEST}) + "\n")
        return self.run_step("Render the manifests", expected)

    def body(self):
        return json.loads((self.dir / "k3s-release.json").read_text())

    def test_render_pins_built_images_by_digest(self):
        pinned = "postgres@sha256:" + "e" * 64
        self.render(f"""
            cat > "$K3S_DEPLOY_OUT/web.yaml" <<YAML
            apiVersion: apps/v1
            kind: Deployment
            metadata: {{name: web}}
            spec:
              template:
                spec:
                  initContainers: [{{name: migrate, image: shop:old}}]
                  containers: [{{name: web, image: {REGISTRY}/shop}}, {{name: db, image: {pinned}}}]
            ---
            kind: List
            items: [{{kind: Service, metadata: {{name: web}}}}]
            YAML
            echo "{{\"kind\": \"ConfigMap\", \"metadata\": {{\"name\": \"$K3S_DEPLOY_SHA\"}}}}" > "$K3S_DEPLOY_OUT/z.json"
        """)
        body = self.body()
        self.assertEqual(body["app"], "shop")
        self.assertEqual([o["kind"] for o in body["objects"]], ["Deployment", "Service", "ConfigMap"])
        self.assertEqual(body["objects"][2]["metadata"]["name"], SHA)
        spec = body["objects"][0]["spec"]["template"]["spec"]
        self.assertEqual([c["image"] for c in spec["initContainers"] + spec["containers"]],
                         [f"{REGISTRY}/shop@{DIGEST}", f"{REGISTRY}/shop@{DIGEST}", pinned])

    def test_render_refuses_no_manifests_and_warns_on_unused_builds(self):
        self.assertIn("wrote no manifests", self.render("true", 1))
        out = self.render('echo "{kind: Service, metadata: {name: web}}" > "$K3S_DEPLOY_OUT/s.yaml"')
        self.assertIn(f"::warning::no manifest runs {REGISTRY}/shop@{DIGEST}", out)

    def release(self, reply, status=200, exit=0, expected=1):
        (self.dir / "k3s-release.json").write_text('{"app": "shop", "objects": []}')
        self.state.update(reply=reply, status=status, exit=exit)
        return self.run_step("Release through k3s-hq", expected)

    def test_release_success_sends_one_call_with_the_token_off_argv(self):
        running = {"app": "shop", "commit": SHA, "state": "running"}
        self.release([running] * 3 + [{"app": "shop", "commit": SHA, "state": "released", "stage": None,
                                       "undo": "none"}], expected=0)
        token, post = self.state["calls"]
        self.assertTrue(token["args"][-1].endswith("&audience=k3s-hq"))
        self.assertEqual(post["args"][-1], "https://k3s.example/api/releases")
        self.assertEqual(post["stdin"].strip(), "Authorization: Bearer oidc-token")
        self.assertNotIn("oidc-token", " ".join(post["args"]))
        self.assertIn("Released shop", (self.dir / "summary").read_text())

    def test_release_without_a_released_result_is_red(self):
        running = {"app": "shop", "commit": SHA, "state": "running"}
        cases = [
            ([running, {"state": "failed", "stage": "checks", "undo": "done", "error": "health"}], 200, 0,
             "failed at checks, undo done: health"),
            ([{"error": "token repository does not own this app"}], 403, 0, "refused (HTTP 403)"),
            ([running, {"error": "release status unavailable"}], 200, 0, "lost the release status"),
            ([running], 200, 0, "ended without a result;"),
            ([running], 200, 28, "curl exit 28"),
        ]
        for reply, status, code, why in cases:
            with self.subTest(why=why):
                self.assertIn(why, self.release(reply, status, code))

    def test_release_needs_an_oidc_grant(self):
        del self.env["ACTIONS_ID_TOKEN_REQUEST_URL"]
        self.assertIn("id-token: write", self.release([]))


if __name__ == "__main__":
    unittest.main()
