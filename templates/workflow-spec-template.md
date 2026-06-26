# Workflow Specification: {WORKFLOW_NAME}

*Copy this template for every new workflow. Fill in all fields before building.*
*Incomplete fields are not acceptable — "TBD" is not a plan.*

---

## Identity

| Field | Value |
|---|---|
| **Workflow name** | |
| **Owner agent** | |
| **Deliverable** | *What must be produced* |
| **Recipient** | *Who receives it — third party, internal, Terence* |
| **Hard deadline** | *Exact time or "none"* |
| **Frequency** | *Daily / weekly / on-demand / etc* |
| **Outward deliverable** | *Yes / No* |
| **Quality standard** | *What defines a valid deliverable* |

---

## Source-to-Outcome Map

*List every step from data source to delivered output.*
*"Step exists" is not documentation. All fields are required.*

| Step | Input | Action | Output artifact (exact path) | Fail-closed verifier | Failure classes | Repair primitive | Fallback | Owner |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |

---

## Independent Verifier

| Field | Value |
|---|---|
| **Script path** | |
| **Cron schedule** | *Fires at what time, relative to deadline* |
| **Session key** | *Must be distinct from main workflow session key* |
| **Repair primitives** | *One per failure class — self-contained, no main workflow calls* |
| **Fallback inputs path** | |
| **Fallback update trigger** | *What event updates last-known-good* |
| **Independence verified** | *Yes/No — have you run the independence test?* |

---

## Failure Classes and Repair Primitives

*For each failure class that can occur in this workflow:*

| Failure class | Step where it occurs | Repair primitive | Repair location | Fallback if repair fails |
|---|---|---|---|---|
| | | | | |

---

## Commitments and ETAs

*Register every ETA in the commitment watchdog:*
```bash
python3 scripts/commitment_watchdog.py --workspace {WORKSPACE} \
  --add --workflow "{workflow-id}" --milestone "{milestone}" --deadline "{ISO timestamp}"
```

| Milestone | Deadline | Commitment registered (Y/N) |
|---|---|---|
| | | |

---

## Failure-Injection Tests

*One test per failure class. "Tests exist" is not enough — list them.*

| Failure class | Inject command | Expected outcome | Test result |
|---|---|---|---|
| | | | |

---

## Audit Sign-Off

Complete before the workflow goes live:

- [ ] All steps documented with artifact contracts and fail-closed verifiers
- [ ] All failure classes identified with repair primitives at the correct layer
- [ ] All repair primitives are self-contained (verified: do not call main workflow scripts)
- [ ] Independent verifier built and independence test passed
- [ ] Fallback inputs pre-populated
- [ ] Failure-injection tests written and passing
- [ ] Commitment watchdog entries created for all ETAs
- [ ] Gap registry checked — no open gaps from decomposition

**Signed off by:** *agent-id*
**Date:** *date*
