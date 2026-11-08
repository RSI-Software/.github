# k3s deploy

[`k3s-deploy.yml`](../.github/workflows/k3s-deploy.yml) releases one app from `main` through k3s-hq.

1. **Tag** the commit `<prefix><N>`, its own job
2. **Build** each image on `ci`, zot layer cache
3. **Push** it to zot as `<repository>:<commit>`
4. **Render** the manifests with the pushed digests
5. **Post** them to k3s-hq, OIDC-signed
6. **Red** on any result but `released`

Route: `https://k3s.rsi.nz/api/releases`, LAN.
k3s-hq then pins, migrates, rolls out, checks and undoes: [Releases](https://github.com/RSI-Software/rsi/blob/main/apps/k3s-hq/README.md#releases).

## Caller

```yaml
  deploy:
    needs: verify
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: write
      actions: write
      id-token: write
    uses: RSI-Software/.github/.github/workflows/k3s-deploy.yml@<full SHA>
    with:
      app: shop
      images: '[{"repository": "shop", "dockerfile": "deploy/Dockerfile", "build-args": "COMMIT=${{ github.sha }}"}]'
      manifests: cp deploy/k3s/*.yaml "$K3S_DEPLOY_OUT"
```

- `app` is a **k3s-hq record** the caller owns
- `prefix` sets the **tag namespace**, default `r`
- `revision` **output**: the tag, e.g. `r12`
- **Revision in**: build-arg and manifests env `K3S_DEPLOY_REVISION`, full tag
- **Write grants** reach only the tag job
- The caller takes **`workflow_dispatch`**
- **Pin a full SHA**; k3s-hq admits SHA or main
- **Other images by digest**, or k3s-hq refuses
- **Old pins keep** their buildah, kubectl path

## Revisions

- A **rerun reuses** the commit's tag and reposts
- A **new commit takes** the highest number plus one
- A **taken number** rereads the tags and **retries**
- A **rolled-back number** is **never reused**

## Overtaken commits

`GITHUB_TOKEN` cannot tag a commit whose workflow files differ from main's head: the tag call gets a 403.

- **Main past the commit** dispatches the caller on main
- **That run** releases main's head and this change
- **This run** ends green with no `revision`
- **Any other 403** fails red

A caller's path filters may never start a run for the newer commit, so skipping alone would strand the change.
