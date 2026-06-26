# Independent Verifier Design

## What an Independent Verifier Is

An independent verifier is a same-agent, separate-execution-context process that:
- Fires on its own schedule, outside the supervised workflow's cron stack
- Checks whether the workflow's deliverable was produced correctly
- Has its own repair primitives — never calls back into the supervised workflow
- Delivers the outcome even if the entire main workflow is broken

**Key distinction:** Independent of the process, not independent of the agent.
The same agent runs both. The independence is in the execution context and
the repair path, not in the agent identity.

---

## Startup Self-Check (mandatory)

At the start of every verifier run, before checking delivery state:
1. Verify your own cron job ID exists in the live runtime registry
2. If missing → reinstate it immediately
3. Verify all required lane jobs exist in live registry
4. If any missing → reinstate them and log
Only then proceed to delivery state check.
A verifier that cannot confirm its own liveness is not independent — it is theoretical.

---

## The Independence Test

Before declaring any verifier complete, run this test:

1. Disable ALL crons in the main workflow
2. Inject the target failure class
3. Wait for the verifier cron to fire on its own schedule
4. Confirm the verifier detects, diagnoses, repairs, and delivers
5. Re-enable the main workflow crons

If step 4 fails, the verifier is not independent. Find and remove the dependency.

Common hidden dependencies to check:
- Does the verifier import any script from the main workflow?
- Does the verifier call any function that calls a main workflow script?
- Does the verifier's repair primitive depend on a shared state file that the
  main workflow writes? (If the workflow didn't run, the state file may be absent)
- Does the verifier assume the main workflow's fallback inputs exist?

---

## Verifier Architecture

```
Independent Verifier
│
├── Delivery check (source of truth)
│   └── Read delivery state file — did the deliverable go out?
│       YES → exit cleanly
│       NO  → proceed
│
├── Diagnosis (from state files, not by re-running the workflow)
│   └── Read failure records, state files, artifact presence
│       → Identify failure class
│
├── Repair (verifier's own primitives)
│   └── Apply repair primitive for identified failure class
│       → Verify repair from production execution context
│       → If repair fails → use fallback inputs
│
├── Delivery (re-enter workflow only after repair confirmed)
│   └── Re-enter only the confirmed-healthy part of the workflow
│       → Confirm delivery
│       → Update last-known-good inputs
│       → Write receipt proof
│
└── Alert (informational only — not a request for direction)
    └── Alert agent owner that delivery occurred and what was repaired
        Never: "I cannot proceed" or "please advise"
        Always: "Delivered. Here is what was fixed."
```

---

## The "No Out" Rule

There is no failure class that results in the deliverable not being sent.

- If the canonical generation route is broken → use last-known-good inputs
- If last-known-good inputs are stale → produce a deliverable that says so
- If the primary send channel is broken → try the secondary channel
- If all send channels are broken → write to a known location and alert

A fallback deliverable is always better than no deliverable.

The only acceptable alert is: "Deliverable sent. Here is what I used."
Not: "I could not deliver because X."

---

## Repair Primitive Design

Each repair primitive must be self-contained:

```python
def repair_{failure_class}(failure_detail: dict) -> tuple[bool, str]:
    """
    Repair a specific failure class.
    
    Returns: (success: bool, proof: str)
    
    Rules:
    - Must not import or call any script from the main workflow
    - Must not depend on state files that the main workflow writes
    - Must verify its own repair from production execution context
    - proof must be verbatim output from that verification
    """
    # Direct repair logic here
    # ...
    return True, "verbatim proof of repair"
```

### Testing repair primitives

For each repair primitive, write a test that:
1. Creates the failure condition directly (do not use the main workflow to create it)
2. Calls the repair primitive
3. Verifies the repair worked from production execution context
4. Verifies the primitive did NOT call back into the main workflow

```python
def test_repair_primitive_is_self_contained():
    # Patch out any main workflow imports
    with mock.patch('main_workflow_script') as mocked:
        # Create failure condition
        # Run repair primitive
        # Assert repair succeeded
        # Assert main workflow script was never called
        mocked.assert_not_called()
```

---

## Fallback Input Management

The verifier's fallback inputs must be maintained:

```
state/last-known-good/
├── metadata.json          # When updated, what artifacts are here
├── {deliverable-artifacts} # Copies of the most recent successful output
└── {input-artifacts}       # Copies of the inputs used for that output
```

**Mandatory:** Update after every successful delivery:
```python
def update_last_known_good(delivery_artifacts: list, input_artifacts: list):
    """Call this after EVERY successful delivery — main workflow or verifier."""
    lkg = Path("state/last-known-good")
    lkg.mkdir(parents=True, exist_ok=True)
    
    all_artifacts = delivery_artifacts + input_artifacts
    for artifact in all_artifacts:
        shutil.copy(artifact, lkg / Path(artifact).name)
    
    (lkg / "metadata.json").write_text(json.dumps({
        "updatedAt": now_iso(),
        "updatedBy": "delivery-confirmation",
        "artifacts": [Path(a).name for a in all_artifacts]
    }))
```

If the verifier has to use fallback inputs, it must mark the deliverable:
```python
FALLBACK_FLAG = "\n\n---\n*Note: This {deliverable} was produced using cached inputs from {lkg_updated_at} because the primary generation route was unavailable. Review before treating as fully current.*\n"
```

---

## Cron Registration for Verifiers

Verifiers must be registered as isolated crons OUTSIDE the main workflow's cron stack.

### Timing principles
- Fire after the main workflow has had its full window to complete
- Fire before the hard deadline (not after)
- For morning deliverables due at 08:00: fire at 07:45
- For evening deliverables due at 21:00: fire at 20:45
- For internal milestones: fire at the committed checkpoint time

### OpenClaw cron registration
```json
{
  "name": "{workflow}-independent-verifier",
  "schedule": "45 7 * * *",
  "sessionKey": "agent:{agent-id}:verifier:{workflow}",
  "message": "Independent verifier run for {workflow}. Check delivery state first. Do not re-run the main workflow to diagnose.",
  "isolated": true,
  "heartbeat": { "enabled": false }
}
```

### Critical: session key must be different from main workflow
If the verifier uses the same session key as the main workflow, they share context
and the verifier inherits the main workflow's potentially corrupted state.
Always use a distinct session key: `agent:{id}:verifier:{workflow}` not `agent:{id}:main`.

---

## Verifier vs Fallback vs Escalation

| Scenario | Response |
|---|---|
| Main workflow delivered correctly | Verifier exits cleanly — no action |
| Main workflow failed — repairable | Verifier applies repair primitive, delivers |
| Main workflow failed — repair fails | Verifier uses fallback inputs, delivers with note |
| Fallback inputs missing/stale | Verifier generates minimal deliverable, delivers with note |
| All delivery channels unavailable | Verifier writes to known location, alerts with location |
| Verifier itself encounters an error | Verifier logs error, uses simpler delivery path, alerts |

**In every scenario, something is delivered and the owner is informed.**
There is no scenario where the verifier says "I cannot proceed."

---

## Verifier Quality Gates

After building a verifier, verify these properties before declaring it live:

- [ ] Independence test passed (main crons disabled, verifier still delivers)
- [ ] All repair primitives tested with failure injection
- [ ] No repair primitive calls back into main workflow scripts
- [ ] Last-known-good inputs populated and verified readable
- [ ] Fallback delivery path tested (last-known-good used, deliverable marked)
- [ ] Session key is distinct from main workflow session key
- [ ] Cron is registered outside main workflow cron stack
- [ ] Alert message is informational only (says what was done, not what it cannot do)
- [ ] Verifier handles the case where last-known-good is also missing
