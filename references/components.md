# Components Reference

## Installation Guide

### Prerequisites
- OpenClaw agent with coding profile
- Python 3.8+
- Write access to agent workspace
- Agent workspace path known (referred to as `{WORKSPACE}` below)

### Installation Order

Always install in this order. Each layer depends on the one before.

**Step 1 — Create state directories**
```bash
mkdir -p {WORKSPACE}/state/gap-registry
mkdir -p {WORKSPACE}/state/verifier-runs
mkdir -p {WORKSPACE}/state/last-known-good
mkdir -p {WORKSPACE}/state/rectification
mkdir -p {WORKSPACE}/state/commitment-registry
```

**Step 2 — Copy scripts**
```bash
cp scripts/gap_registry.py {WORKSPACE}/scripts/
cp scripts/gap_enforcer.py {WORKSPACE}/scripts/
cp scripts/independent_verifier_template.py {WORKSPACE}/scripts/
cp scripts/commitment_watchdog.py {WORKSPACE}/scripts/
cp scripts/failure_injector.py {WORKSPACE}/scripts/
cp scripts/process_decompose.py {WORKSPACE}/scripts/
```

**Step 3 — Verify scripts install correctly**
```bash
cd {WORKSPACE}
python3 scripts/gap_registry.py verify
python3 scripts/gap_enforcer.py --workspace . --verify
python3 scripts/commitment_watchdog.py --workspace . --verify
```

**Step 4 — Add to AGENTS.md (top, above session startup)**

Add this block as the FIRST section in AGENTS.md:

```markdown
## Process Integrity — Mandatory (read before anything else)

### Gap Registration Rule
Gap identification and enforcement are the same atomic action.
The moment you identify a gap in any process, write it immediately:

  python3 scripts/gap_registry.py write \
    --gap "exact description" \
    --workflow "workflow-name" \
    --class "failure-class-from-taxonomy" \
    --ttl 60

A gap is only closed when production-context verification is complete:

  python3 scripts/gap_registry.py close \
    --id "gap-uuid" \
    --proof "verbatim output from production execution"

No gap stays a finding. No task is done without production-context verification.

### Tool Pre-flight (run at every session start)
Before any task, verify tools are available:
  echo "tool check" > /tmp/{agent-id}-tool-check.txt && cat /tmp/{agent-id}-tool-check.txt
If this fails, report the exact error. Never assume tool unavailability without attempting.

### Closing Standard
A task is done ONLY when all of these are true:
1. Fix exists on disk at specified path
2. Verified from production execution context (not test harness)
3. Verification output recorded as proof
4. Failure-injection test exists for this failure class
5. Gap registry entry closed with proof
6. Fix would have prevented the original incident
```

**Step 5 — Register gap enforcer cron**

Register as an isolated cron in OpenClaw outside the main workflow stack:
```json
{
  "name": "gap-enforcer",
  "schedule": "0 */2 * * *",
  "sessionKey": "agent:{agent-id}:gap-enforcer",
  "message": "Gap enforcer run. Check gap-registry for overdue open entries. Fix and close all overdue gaps before proceeding to other work.",
  "isolated": true
}
```

**Step 6 — For each workflow with a deliverable**

Copy and customise the verifier template:
```bash
cp scripts/independent_verifier_template.py \
   {WORKSPACE}/scripts/{workflow_name}_verifier.py
```

Edit the CONFIGURATION section. Then register the verifier cron:
```json
{
  "name": "{workflow}-independent-verifier",
  "schedule": "45 7 * * *",
  "sessionKey": "agent:{agent-id}:verifier:{workflow}",
  "message": "Independent verifier for {workflow}. Check delivery state first. Do not re-run the main workflow.",
  "isolated": true
}
```

**Step 7 — For each workflow with ETA commitments**

Register commitments as they are made:
```bash
python3 scripts/commitment_watchdog.py \
  --workspace {WORKSPACE} \
  --add \
  --workflow "workflow-name" \
  --milestone "what was committed" \
  --deadline "ISO timestamp"
```

Register the watchdog cron:
```json
{
  "name": "commitment-watchdog",
  "schedule": "0 */3 * * *",
  "sessionKey": "agent:{agent-id}:commitment-watchdog",
  "message": "Commitment watchdog run. Check for overdue or drifted commitments.",
  "isolated": true
}
```

---

## Gap Registry

**Location:** `{WORKSPACE}/state/gap-registry/registry.jsonl`

**Script:** `scripts/gap_registry.py`

**Operations:**
```bash
# Write a gap (mandatory when identifying any gap)
python3 scripts/gap_registry.py write --gap "..." --workflow "..." --class "..." --ttl 60

# Close a gap (only with production-context proof)
python3 scripts/gap_registry.py close --id "uuid" --proof "verbatim output"

# List all gaps
python3 scripts/gap_registry.py list --status open

# Check for overdue gaps
python3 scripts/gap_registry.py enforce --workspace {WORKSPACE}

# Verify installation
python3 scripts/gap_registry.py verify
```

---

## Gap Enforcer

**Location:** `{WORKSPACE}/scripts/gap_enforcer.py`
**Cron:** Every 2 hours, isolated, outside main workflow stack
**Session key:** `agent:{id}:gap-enforcer`

The enforcer reads the gap registry, finds open entries older than TTL, and
writes an enforcement message to `{WORKSPACE}/state/enforcement-inbox.md`.

The agent's AGENTS.md startup sequence must check for enforcement inbox content:
```markdown
## Startup — check enforcement inbox first
If {WORKSPACE}/state/enforcement-inbox.md exists and is non-empty:
  Read it. Address all items in it before any other work.
  After addressing, clear the file.
```

---

## Independent Verifier Template

**Location:** `scripts/independent_verifier_template.py`
**Customise:** CONFIGURATION section at top of file

Key sections to customise:
1. `DELIVERY_STATE_PATH` — where to check if delivered
2. `FALLBACK_INPUTS_PATH` — where last-known-good inputs live
3. `REPAIR_PRIMITIVES` dict — one function per failure class
4. `send_deliverable()` — how to send the output
5. `update_last_known_good()` — what to save after successful delivery

After customising, verify:
```bash
cd {production_working_directory}
python3 {WORKSPACE}/scripts/{workflow}_verifier.py --verify
python3 {WORKSPACE}/scripts/{workflow}_verifier.py --dry-run --slot morning
```

---

## Commitment Watchdog

**Location:** `{WORKSPACE}/scripts/commitment_watchdog.py`
**Registry:** `{WORKSPACE}/state/commitment-registry/registry.json`
**Cron:** Every 3 hours, isolated

Operations:
```bash
# Add commitment when making any ETA promise
python3 scripts/commitment_watchdog.py --workspace {WORKSPACE} \
  --add --workflow "..." --milestone "..." --deadline "ISO timestamp"

# Update actual state at checkpoints
python3 scripts/commitment_watchdog.py --workspace {WORKSPACE} \
  --update --id "uuid" --state "actual state description"

# Close when milestone met
python3 scripts/commitment_watchdog.py --workspace {WORKSPACE} \
  --close --id "uuid" --proof "what was done"

# Run check manually
python3 scripts/commitment_watchdog.py --workspace {WORKSPACE}
```

---

## Failure Injector

**Location:** `{WORKSPACE}/scripts/failure_injector.py`

Used for testing repair primitives and verifier resilience:
```bash
# Inject a specific failure class
python3 scripts/failure_injector.py \
  --workflow {workflow} \
  --step {step_name} \
  --class {failure_class} \
  --workspace {WORKSPACE}

# Run all failure-injection tests for a workflow
python3 scripts/failure_injector.py \
  --workflow {workflow} \
  --all \
  --workspace {WORKSPACE}
```

---

## Process Decompose

**Location:** `{WORKSPACE}/scripts/process_decompose.py`

Scaffolds a new process decomposition document:
```bash
python3 scripts/process_decompose.py \
  --workflow "Daily Brief" \
  --steps "data-fetch,commentary-draft,brief-generation,qc-attestation,send" \
  --output {WORKSPACE}/artifacts/decomposition-daily-brief.md
```

Produces a template with all required fields pre-populated for completion.
