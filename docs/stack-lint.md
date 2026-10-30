# Stack lint drift

**`actions/stack-lint` checks root lint rules** against `RSI-Software/rsi`'s `stack.oxlintrc.json` on `main` at run time.
It reads the authoritative file, never a bundled snapshot.

Run it inside the existing checks job, **after checkout and `bun install`**:

```yaml
- uses: RSI-Software/.github/actions/stack-lint@main
  with:
    token: ${{ secrets.RSI_STACK_READ_TOKEN }}
```

**The token needs contents read access to private `RSI-Software/rsi`.**
The caller's `GITHUB_TOKEN` cannot read another private repository.
Never run untrusted fork code with this secret through `pull_request_target`.

**Bun loads a static `vite.config.ts`** by default; `config:` selects another Vite+ or Oxlint JSON config.
Inline and relative JSON `extends` are resolved in order, then root rules override them.
Unsupported dynamic configs and unreadable files fail the job.

**Every authoritative rule must match severity and contain its options.**
Rule aliases, option order, diagnostic messages and additional local restrictions do not cause drift.
Existing per-file overrides remain local: this checks the shared root rules, not baseline exemptions.
Future authoritative rules are checked automatically.

**Local verification:** `python3 -m unittest discover -s tests -v` runs the action's comparison script with passing and drifted copies.
Set `RSI_STACK_CONFIG` to an authoritative JSON file to run the same controls against that file.
