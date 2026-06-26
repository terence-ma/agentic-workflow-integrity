# Process Decomposition Guide

## Overview

Process decomposition is the foundational step before building or auditing any
workflow. It means tracing every step from the data source to the final delivered
output, identifying failure points at each step, and wiring repair paths before
the workflow goes live.

The most common reason workflows fail repeatedly is that decomposition was done
at the checkpoint layer rather than the source layer. Checkpoints can observe
failures upstream of them but cannot repair them. Decomposition must start at
the source.

---

## The Decomposition Template

For every workflow, complete this template before writing code.

### Workflow: {name}
**Owner agent:** {agent-id}
**Deliverable:** {what must be produced}
**Hard deadline:** {time or none}
**Outward deliverable:** {yes/no — does this go to third parties?}

---

### Step-by-step breakdown

For each step, fill in all fields. Do not skip fields.

```
Step N: {step name}
  Input: {what this step receives}
  Action: {what this step does}
  Output artifact: {exact file path or state that must exist after this step}
  Artifact contract: {how is the artifact's existence and validity verified?}
  Fail-closed verifier: {script or check that enforces the contract — "assumed" is not acceptable}
  Failure classes: {which failure modes can occur here?}
  Repair primitive: {what fixes each failure class directly at this step?}
  Fallback: {what produces a valid-enough output if repair fails?}
  Owner: {who is responsible for repair at this step?}
  Test: {failure-injection test that verifies the repair primitive works}
```

---

## Example Decomposition: Daily Brief Pipeline

### Step 1: Data fetch (06:00)
- **Input:** Portfolio holdings, market data APIs
- **Action:** warren-scout fetches prices, news, macro data
- **Output artifact:** `workspace-warren/market-data-{date}.json`
- **Artifact contract:** File exists, non-empty, timestamp within 2 hours
- **Fail-closed verifier:** `verify_market_data_contract.py --date {date}`
- **Failure classes:** API timeout, stale data, missing fields
- **Repair primitive:** Retry once; if fail, use cached data from previous session
- **Fallback:** `state/last-known-good/market-data.json` with staleness flag
- **Owner:** warren-scout, with independent verifier backup
- **Test:** `inject_failure.py --step data-fetch --class api-timeout`

### Step 2: Commentary draft generation (06:00–06:20)
- **Input:** Market data from step 1
- **Action:** warren-scout generates commentary draft
- **Output artifact:** `workspace-warren/commentary-draft-{date}-{slot}.md`
- **Artifact contract:** File exists, non-empty, passes commentary QC checks
- **Fail-closed verifier:** `verify_daily_brief_start_contract.py --date {date} --slot {slot}`
- **Failure classes:** Missing file, forbidden marker, recycled content, market numbers mismatch
- **Repair primitive:** Write rectification request → kick Qin cron → Qin rewrites flagged section
- **Fallback:** Minimal supervisor-generated commentary with staleness flag
- **Owner:** Qin (via rectification request pattern)
- **Test:** `inject_failure.py --step commentary --class forbidden-marker`

### Step 3: Brief generation (06:20)
- **Input:** Commentary draft, holdings, watch file, actionables
- **Action:** `generate_daily_brief.py` synthesises brief
- **Output artifact:** Canonical PDFs at `workspace-warren/output/briefs/`
- **Artifact contract:** Both PDFs exist, freshness gate passes, render gate passes
- **Fail-closed verifier:** Freshness gate + render gate scripts
- **Failure classes:** Import path failure, watch classifier false trigger, QC exception
- **Repair primitive:** Per failure class (see failure-modes.md)
- **Fallback:** Regenerate from last-known-good inputs with fallback flag
- **Owner:** Independent verifier (fires at 07:45)
- **Test:** `inject_failure.py --step generation --class import-path`

### Step 4: QC attestation (07:42)
- **Input:** Rendered PDFs
- **Action:** Qin reviews and attests
- **Output artifact:** Attestation file at `state/daily-brief-delivery/`
- **Artifact contract:** Attestation exists, fingerprints match current PDFs
- **Fail-closed verifier:** Send layer checks attestation before proceeding
- **Failure classes:** Missing attestation, fingerprint mismatch, Qin unavailable
- **Repair primitive:** Rectification request → Qin wakes → attests directly
- **Fallback:** Supervisor-generated attestation with note
- **Owner:** Independent verifier backup
- **Test:** `inject_failure.py --step attestation --class missing`

### Step 5: Send (07:52–08:00)
- **Input:** Attested PDFs
- **Action:** Send pair via Telegram bridge
- **Output artifact:** Delivery state file with `status: sent`
- **Artifact contract:** Receipt proved, delivery state confirmed
- **Fail-closed verifier:** `check_daily_brief_receipt.py`
- **Failure classes:** Bridge timeout, send failure, receipt not proved
- **Repair primitive:** Retry with longer timeout; retry via alternative channel
- **Fallback:** Send minimal text summary if PDF send fails repeatedly
- **Owner:** Independent verifier (fires at 07:45, forces send)
- **Test:** `inject_failure.py --step send --class bridge-timeout`

---

## Decomposition Rules

### Rule 1: Every step must have an artifact contract
"The step ran" is not an artifact contract. The artifact must exist at a specific
path and pass a validity check. If you cannot state the exact file path and the
exact validity check, the artifact contract is undefined.

### Rule 2: "Assumed" is not a verifier
If your verifier column says "assumed" or "checked by downstream step," the
contract is not enforced. Write a fail-closed verifier script.

### Rule 3: Repair primitives must be at the correct layer
A repair primitive that calls back into the same broken step is not a repair —
it is a retry of the failure. The repair primitive must fix the specific broken
component at the source, not re-run the whole step.

### Rule 4: Every fallback must be pre-populated
A fallback that generates from scratch is useful. A fallback that reads from
`last-known-good` is better. But `last-known-good` must be populated after
every successful run — not just assumed to exist.

### Rule 5: Failure-injection tests are mandatory
"The step exists and the job is registered" is not a test. Inject the actual
failure and verify the repair primitive fixes it. If you have not run the
failure-injection test, you do not know if the repair works.

### Rule 6: Decomposition must start at the data source
The most common decomposition error is starting at the checkpoint layer and
working outward. Always start at the first point where data enters the workflow
and work forward to the delivered output.

---

## Identifying Failure Points

For each step, ask:
1. What external dependency does this step have? (API, file, agent, classifier)
2. What happens if that dependency is unavailable or returns unexpected data?
3. What happens if the previous step's artifact is missing or invalid?
4. What happens if this step's process itself fails (import error, exception, timeout)?
5. What happens if this step succeeds but produces output that fails downstream?

Each answer is a failure class. Each failure class needs a repair primitive.

---

## The Wrong-Layer Trap

The most common decomposition mistake: identifying a failure at step N and wiring
a repair at step N+2.

Example: Commentary is missing (step 2 failure). Repair is wired at the QC
checkpoint (step 4). The checkpoint can detect the missing commentary but cannot
generate it — so the repair path observes the problem but does not fix it.

Fix: Wire the repair primitive at step 2 (the fail-closed verifier), not at
the checkpoint that observes the consequence.

---

## When to Re-decompose

Re-run the decomposition when:
- A workflow fails in a way that was not anticipated
- A new failure class is added to `failure-modes.md`
- An upstream dependency changes
- The workflow is extended with new steps
- An independent verifier fails to repair a failure it should have caught
