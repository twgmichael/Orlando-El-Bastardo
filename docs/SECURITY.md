# Security and Privacy Policy

This repo is public. Everything committed is visible to the world. These rules
are non-negotiable and enforced by an automated pre-commit sweep.

## Rules

### No absolute paths in code

All file paths in committed code must be relative or resolved via environment
variables. Never hardcode `/Users/…`, `/home/…`, or `/Volumes/…` in any
`.py`, `.sh`, `.json`, `.yaml`, or other code/config file.

Use env vars instead:

| Purpose | Env var |
|---|---|
| Asset library root | `OEB_ASSET_ROOT` |
| Config file path | `OEB_CONFIG_PATH` |
| Harness server URL | `OEB_HARNESS_URL` |
| Output/render root | configured per-worker in `output_root` (worker config only) |

Worker config-example files (`oeb-studio-harness/worker/config-examples/`)
may show real path formats as documentation — those lines carry `# sweep:ok`.

### No PII

No real names, email addresses, usernames, or any personally identifying
information in committed files. The git author email is already set to a
GitHub noreply address.

### No credentials or secrets

No API keys, tokens, passwords, or private key material. Secrets live in:
- `.secrets/` — gitignored, never committed
- Ansible Vault — injected at deploy time, never in plaintext

### No private infrastructure details

Pi IP addresses, internal hostnames, Ansible vault names, and private role
names stay in `docs/local/` (gitignored) and Ansible inventory (not
committed). Public docs use role names only (orchestrator, mac-mini worker,
gaming-pc worker).

---

## Automated sweep

**`tools/security_sweep.py`** runs before every commit via a pre-commit hook.

```sh
# Manual full scan
.venv/bin/python tools/security_sweep.py

# Staged files only (what the pre-commit hook runs)
.venv/bin/python tools/security_sweep.py --staged
```

### What it checks

| Pattern | Applies to |
|---|---|
| `/Users/<name>/` (excluding `/Users/Shared/`) | all text files |
| `/home/<name>/` | all text files |
| Private IPs: 192.168.x.x, 10.x.x.x, 172.16–31.x.x | all text files |
| Private key material (`-----BEGIN … PRIVATE KEY-----`) | all text files |
| Hardcoded credentials (`password=`, `api_key=`, etc.) | all text files |
| API key prefixes (`sk-`, `ghp_`, `xoxb-`) | all text files |
| Absolute `/Volumes/` paths | code/config files only |
| Private terms from `docs/local/sweep-privates.txt` | all text files |

Binary files and `docs/local/` are skipped automatically.

### Private terms file

`docs/local/sweep-privates.txt` is gitignored. Add one term per line:
Pi hostnames, internal IPs, your real name, drive UUIDs, etc. The sweep
loads it automatically if it exists.

### Suppressing a known-safe line

If a line is intentionally safe (e.g. a config example showing path format),
append `# sweep:ok` with a brief reason:

```yaml
output_root: /Volumes/OEB-PROJECT/OEB-PRODUCTION  # sweep:ok — intentional config example path
```

Agents must never use `# sweep:ok` without a written justification on the
same line.

### Installing the pre-commit hook

```sh
printf '#!/bin/sh\n.venv/bin/python tools/security_sweep.py --staged\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

---

## Audit history

| Date | Result | Notes |
|---|---|---|
| 2026-07-05 | PASSED | First audit before repo went public |
| 2026-07-11 | PASSED (2 findings resolved) | Volume names in PROJECT-DONE scrubbed; model fields in agent frontmatter accepted as exception (see DECISIONS.md) |
| 2026-07-14 | PASSED | Automated sweep introduced; 160 files, 0 findings at baseline |
