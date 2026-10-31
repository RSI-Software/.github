# k3s deploy

[`k3s-deploy.yml`](../.github/workflows/k3s-deploy.yml) releases one app from `main` through k3s-hq.

1. **Build** each image on `ci`, zot layer cache
2. **Push** it to zot as `<repository>:<commit>`
3. **Render** the manifests with the pushed digests
4. **Post** them to k3s-hq, OIDC-signed
5. **Red** on any result but `released`

Route: `https://k3s.rsi.nz/api/releases`, LAN.
k3s-hq then pins, migrates, rolls out, checks and undoes: [Releases](https://github.com/RSI-Software/rsi/blob/main/apps/k3s-hq/README.md#releases).

## Caller

```yaml
  deploy:
    needs: verify
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: read
      id-token: write
    uses: RSI-Software/.github/.github/workflows/k3s-deploy.yml@<full SHA>
    with:
      app: shop
      images: '[{"repository": "shop", "dockerfile": "deploy/Dockerfile", "build-args": "COMMIT=${{ github.sha }}"}]'
      manifests: cp deploy/k3s/*.yaml "$K3S_DEPLOY_OUT"
```

- **`app`:** a k3s-hq record owned by the caller
- **Pin:** a full SHA; k3s-hq admits SHA or main
- **Other images:** by digest, or k3s-hq refuses
- **Rerun:** reposts; same commit attaches
- **Old pins:** keep their buildah, kubectl path
