# Resilience Patterns

## Overview

These are proven patterns for making workflow steps resilient. Apply the appropriate
pattern at each step during process decomposition.

---

## Pattern 1: Fail-Closed Verifier

**Use when:** A step must produce a specific artifact before downstream steps can proceed.

**Structure:**
```python
def verify_{step}_contract(date: str, slot: str) -> tuple[bool, str]:
    """
    Fail-closed verifier for {step}.
    Returns (passed: bool, details: str).
    On failure, caller must invoke repair primitive — not retry the step.
    """
    artifact_path = resolve_artifact_path(date, slot)
    
    if not artifact_path.exists():
        return False, f"MISSING: {artifact_path}"
    
    if artifact_path.stat().st_size == 0:
        return False, f"EMPTY: {artifact_path}"
    
    # Validity check specific to this artifact type
    content = artifact_path.read_text()
    if not passes_validity_check(content):
        return False, f"INVALID: {artifact_path} — {describe_invalidity(content)}"
    
    return True, f"OK: {artifact_path} ({artifact_path.stat().st_size} bytes)"
```

**Rules:**
- Returns a tuple, never raises — caller decides what to do with the result
- Describes exactly what failed and where
- Does not attempt repair — that is the repair primitive's job
- Is fast enough to run after every step without slowing the workflow

---

## Pattern 2: Rectification Request

**Use when:** A step's output fails validation and the fix requires agent judgment or rewriting.

**Structure:**
```python
def write_rectification_request(
    failure_class: str,
    exact_failure: str,
    suggested_fix: str,
    section_name: str,
    artifact_path: str,
    deadline: str,
    slot: str,
    date: str
) -> Path:
    """
    Write a rectification request and kick the owner cron.
    This replaces raising an exception or writing a blocked state.
    """
    request = {
        "id": str(uuid.uuid4()),
        "createdAt": now_iso(),
        "failureClass": failure_class,
        "exactFailure": exact_failure,
        "suggestedFix": suggested_fix,
        "sectionName": section_name,
        "artifactPath": artifact_path,
        "deadline": deadline,
        "slot": slot,
        "date": date,
        "status": "pending",
        "owner": "qin"  # or agent-id
    }
    
    request_path = RECTIFICATION_DIR / f"rectification-{date}-{slot}.json"
    request_path.write_text(json.dumps(request, indent=2))
    
    # Kick owner cron immediately — do not wait for next scheduled run
    kick_owner_cron(slot=slot)
    
    return request_path
```

**Critical fields:**
- `exactFailure` — the specific text, marker, or value that triggered the failure
- `suggestedFix` — what to change, precisely. Not "fix the commentary" — "remove the word 'handoff' from line 3 of the Global Markets section"

**Rules:**
- Do NOT write a blocked delivery state — write `status: rectification-pending`
- Do NOT stop the workflow — continue generating unaffected sections
- Do kick the owner cron immediately — do not wait for the next scheduled heartbeat
- The owner must have enough context to fix without re-reading the full artifact

---

## Pattern 3: Retryable Error State

**Use when:** A failure is temporary and the step should be retried after a repair.

**Structure:**
```python
RETRYABLE_STATES = {
    "rectification-pending": "rectify-and-rerun-now",
    "attestation-pending": "attest-and-resend-now",
    "send-retry": "retry-send-now",
}

TERMINAL_STATES = {
    "missing-source-data": True,   # Cannot generate without source
    "all-channels-failed": True,   # Cannot send
}

def classify_delivery_state(state: dict) -> str:
    reason = state.get("reason", "unknown")
    if reason in RETRYABLE_STATES:
        return "retryable"
    if reason in TERMINAL_STATES:
        return "terminal"
    return "unknown"
```

**Rules:**
- Retryable states must have a `requestedAction` field saying exactly what to do
- Terminal states must be truly terminal — not just hard to fix
- The `status: blocked` state should be reserved for genuinely terminal failures
- Most failures that look terminal are actually retryable with the right repair primitive

---

## Pattern 4: Fallback Chain

**Use when:** A step can produce valid output from multiple sources of decreasing quality.

**Structure:**
```python
FALLBACK_CHAIN = [
    ("primary", generate_from_live_data),
    ("cached", generate_from_cached_data),
    ("last-known-good", generate_from_lkg_inputs),
    ("minimal", generate_minimal_with_flag),
]

def produce_with_fallback(date: str, slot: str) -> tuple[str, str]:
    """
    Try each source in the fallback chain.
    Returns (artifact_path, source_used).
    """
    errors = []
    for source_name, source_fn in FALLBACK_CHAIN:
        try:
            result = source_fn(date, slot)
            if result and validate_result(result):
                if source_name != "primary":
                    annotate_with_fallback_flag(result, source_name)
                return result, source_name
        except Exception as e:
            errors.append(f"{source_name}: {e}")
            continue
    
    # This should never be reached if minimal fallback is properly implemented
    raise RuntimeError(f"All fallback sources exhausted: {errors}")
```

**Rules:**
- The minimal fallback must always succeed — it generates a valid-but-minimal output
- Every non-primary source must annotate the output with a fallback flag
- The fallback flag must be visible in the deliverable — recipients should know
- Last-known-good must be populated after every successful primary delivery

---

## Pattern 5: Repair-and-Continue

**Use when:** A section of a workflow fails but other sections can proceed independently.

**Structure:**
```python
def build_workflow_output(sections: list, date: str, slot: str) -> dict:
    """
    Build output from all sections. Failed sections get repair requests,
    not workflow termination. Unaffected sections continue.
    """
    results = {}
    pending_repairs = []
    
    for section in sections:
        try:
            result = build_section(section, date, slot)
            validate_section(result, section)
            results[section.name] = result
        except QCFailure as e:
            # Write rectification request — do not stop
            request = write_rectification_request(
                failure_class=e.failure_class,
                exact_failure=e.exact_text,
                suggested_fix=e.suggested_fix,
                section_name=section.name,
                artifact_path=section.output_path,
                deadline=section.repair_deadline,
                slot=slot,
                date=date
            )
            pending_repairs.append(request)
            results[section.name] = None  # Park this section
        except FatalError as e:
            # Only truly fatal errors stop the section
            results[section.name] = None
            log_fatal(section.name, e)
    
    return {
        "sections": results,
        "pendingRepairs": pending_repairs,
        "status": "complete" if not pending_repairs else "rectification-pending"
    }
```

**Rules:**
- QC failures are not fatal — they are repair triggers
- Only genuinely unrecoverable failures (missing source data with no fallback) stop a section
- Parked sections must be clearly marked — downstream steps must handle `None` sections
- The workflow continues to build unaffected sections

---

## Pattern 6: Production-Context Verification

**Use when:** Verifying that a fix or script works correctly before declaring it done.

**Structure:**
```bash
# Always run from the production working directory
cd {production_working_directory}

# Run with the production interpreter and environment
{production_venv}/bin/python3 {script_path} --verify

# Expected output format:
# [script-name] Verification mode
# [script-name] All checks passed.
# [script-name] status: ok
```

```python
def add_verify_mode(script):
    """Every script should have a --verify flag for production-context testing."""
    if args.verify:
        print(f"[{SCRIPT_NAME}] Verification mode")
        
        # Check 1: Can we import all dependencies?
        try:
            import_all_dependencies()
            print(f"[{SCRIPT_NAME}] Imports: OK")
        except ImportError as e:
            print(f"[{SCRIPT_NAME}] FAIL: Import error: {e}")
            sys.exit(1)
        
        # Check 2: Can we reach all required paths?
        for path in REQUIRED_PATHS:
            if not Path(path).exists():
                print(f"[{SCRIPT_NAME}] FAIL: Required path missing: {path}")
                sys.exit(1)
        print(f"[{SCRIPT_NAME}] Required paths: OK")
        
        # Check 3: Can we write to output paths?
        test_write_path = OUTPUT_DIR / ".verify-test"
        try:
            test_write_path.write_text("test")
            test_write_path.unlink()
            print(f"[{SCRIPT_NAME}] Write access: OK")
        except Exception as e:
            print(f"[{SCRIPT_NAME}] FAIL: Cannot write to output: {e}")
            sys.exit(1)
        
        print(f"[{SCRIPT_NAME}] status: ok")
        sys.exit(0)
```

**Rules:**
- Every script must have a `--verify` flag
- Verification must run from the production directory, not the project root or test directory
- Verification must test imports, path access, and write access
- Verification output must be verbatim-pasteable as proof in the gap registry

---

## Pattern 7: Delivery Confirmation and LKG Update

**Use when:** A delivery has been confirmed and fallback inputs should be updated.

**Structure:**
```python
def confirm_delivery_and_update_lkg(
    delivery_artifacts: list,
    input_artifacts: list,
    slot: str,
    date: str
):
    """
    Called after EVERY successful delivery — primary or verifier.
    Updates last-known-good inputs for future fallback use.
    """
    # Write delivery state
    state = {
        "status": "sent",
        "sentAt": now_iso(),
        "receiptProved": True,
        "artifacts": [str(Path(a).name) for a in delivery_artifacts]
    }
    delivery_state_path(slot, date).write_text(json.dumps(state, indent=2))
    
    # Update last-known-good
    lkg = LKG_PATH
    lkg.mkdir(parents=True, exist_ok=True)
    
    for artifact in delivery_artifacts + input_artifacts:
        artifact_path = Path(artifact)
        if artifact_path.exists():
            shutil.copy(artifact_path, lkg / artifact_path.name)
    
    (lkg / "metadata.json").write_text(json.dumps({
        "updatedAt": now_iso(),
        "slot": slot,
        "date": date,
        "artifacts": [Path(a).name for a in delivery_artifacts + input_artifacts
                     if Path(a).exists()]
    }))
    
    print(f"[delivery] Confirmed and LKG updated for {date} {slot}")
```

**Rules:**
- This function must be called after EVERY successful delivery, not just primary deliveries
- If the verifier delivers using fallback inputs, it must still update LKG with what it used
- LKG must never be updated with failed or partial artifacts
