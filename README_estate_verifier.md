# OpenClaw Estate Parity Verifier

A generalised tool that verifies your OpenClaw agent estate matches your specification. Catches the gap between what you *intended* to implement and what is *actually* running.

## The Problem

When implementing or changing OpenClaw agent pipelines, three failure modes recur:

1. **Wrong surface** — changes made to a file that isn't what the gateway actually reads (e.g. editing `jobs.json` when the gateway reads SQLite)
2. **Partial implementation** — instructions partially followed, some surfaces updated and others missed
3. **Regression** — a later change re-introduces something that was deliberately removed (e.g. a legacy flag or broken routing pattern)

Standard parity sweeps fail because they depend on the agent remembering to run them, knowing which surfaces to check, and correctly interpreting what they find. This tool makes the sweep automatic, deterministic, and config-driven.

## How It Works

Define your spec in `estate-config.json`. Run `verify_estate.py`. Get `PASS` or `FAIL` with specific gaps.

```
RESULT: FAIL  (11/14 checks passed, 3 gaps)

❌ GAPS (3):
  • ANTI-PATTERN [Legacy send-window gate]: found in [converge_delivery.py]
  • CRONTAB MISSING: Evening convergence wake (20:45 SGT weekdays)
  • SHOULD BE DISABLED but ENABLED: qin-evening-brief-final-send-checkpoint
```

## What It Checks

| Check | Description |
|-------|-------------|
| **Anti-patterns** | Grep the entire estate for forbidden patterns — legacy flags, broken routing, deprecated fields |
| **System crontab** | Verify expected crontab entries are installed with the right expressions |
| **OpenClaw SQLite** | Verify cron jobs are enabled or disabled as specified — reads the live gateway state, not JSON files |
| **Required files** | Verify scripts and config files exist |
| **Source-of-truth content** | Verify documentation contains required terms and is clean of forbidden ones |
| **Custom commands** | Run arbitrary shell checks with expected exit codes |

## Installation

```bash
# Clone into your OpenClaw workspace or anywhere on the host
git clone https://github.com/terence-ma/agentic-workflow-integrity
cd agentic-workflow-integrity

# Copy and edit the example config
cp estate-config.example.json estate-config.json
# Edit estate-config.json for your paths, job names, and patterns

# Run
python3 verify_estate.py

# Or with a custom config path
python3 verify_estate.py --config /path/to/my-config.json

# Quiet mode (PASS/FAIL only, good for cron)
python3 verify_estate.py --quiet

# Log to file
python3 verify_estate.py --log /path/to/integrity.log
```

## Scheduling

Add to system crontab to run automatically after every implementation window:

```bash
# Run daily at 03:00 local time — results appear in morning brief
0 3 * * * /usr/bin/python3 /path/to/verify_estate.py --quiet --log /path/to/integrity.log
```

Or trigger after any cron estate change:

```bash
# After making changes, run immediately
openclaw cron edit ... && python3 verify_estate.py
```

## Config Reference

```json
{
  "name": "My Pipeline",
  "version": "1.0",
  "openclaw_sqlite": "/home/user/.openclaw/state/openclaw.sqlite",
  "log_file": "/path/to/integrity.log",
  "search_roots": ["/path/to/scripts", "/path/to/state"],
  "search_extensions": ["*.py", "*.json", "*.md", "*.sh"],

  "anti_patterns": [
    {
      "pattern": "forbidden-string",
      "description": "Why this is forbidden",
      "exclude_if_in": ["archive", "example"]
    }
  ],

  "expected_crontab": [
    {
      "expr": "45 7 * * 1-5",
      "label": "Morning job",
      "must_contain": "openclaw"
    }
  ],

  "cron_must_be_disabled": ["job-name-1", "job-name-2"],
  "cron_must_be_enabled":  [{"name": "job-name-3"}],

  "required_files": [
    {"path": "/path/to/file.py", "label": "Description"}
  ],

  "source_of_truth_checks": [
    {
      "path": "/path/to/SOT.md",
      "label": "My SOT",
      "must_contain": ["required-term"],
      "must_not_contain": ["forbidden-term"]
    }
  ],

  "custom_checks": [
    {
      "label": "Gateway running",
      "command": "openclaw gateway status 2>&1 | grep -q running",
      "expect_exit_code": 0
    }
  ]
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | PASS — estate matches spec |
| `1` | FAIL — gaps found |
| `2` | ERROR — could not run checks |

## Integration with Morning Brief

Have your agent append the integrity log to the morning brief:

```python
# In your brief generator
integrity_log = Path("/path/to/integrity.log")
if integrity_log.exists():
    lines = integrity_log.read_text().splitlines()
    # Find the most recent result block and include it
```

## Why OpenClaw SQLite, Not jobs.json

OpenClaw 2026.5+ stores cron job state in SQLite, not `~/.openclaw/cron/jobs.json`. The JSON file is legacy. This tool reads SQLite directly so checks reflect the live gateway state, not a potentially stale file.

## Requirements

- Python 3.8+
- OpenClaw gateway installed (for SQLite checks)
- `grep` available (standard on Linux/macOS)

## Related

Part of [agentic-workflow-integrity](https://github.com/terence-ma/agentic-workflow-integrity) — tools for maintaining integrity in multi-agent AI workflows.

See also: `agent-brutus` — adversarial pre-flight validator for agent plans.
