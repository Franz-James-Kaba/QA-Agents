# Bug Mode

Files Jira Bug tickets. Four sub-modes, distinguished by the argument shape:

| Argument | Sub-mode |
|----------|----------|
| no argument, just a project key, or natural-language description | manual |
| `<EXEC_KEY> --tcs TC1,TC2,...` | explicit |
| `<EXEC_KEY>` alone | auto |
| `all` (with project resolved separately) | all |

The audit (`audit.md`) has already run by the time you reach this file.

After resolving per-bug inputs in any sub-mode, the actual ticket creation always uses `bug-creation.md`. Explicit, auto, and all sub-modes also run results-file enrichment when a runner output file is available (see "Results-file enrichment" at the bottom).

> **Delegation (see `orchestrator-protocol.md`).** The orchestrator keeps the judgment work — the audit, results-file enrichment, dedupe guard, severity/priority inference, and *which* bugs to file. The actual ticket creation (write ADF → create → link → transition) is **delegated to a Sonnet worker per bug** (`model: "sonnet"`) using the subagent template in `bug-creation.md`. Strict delegation: even a single bug goes to a Sonnet worker, spawned via the template. The manual sub-mode keeps its confirmation gate with the orchestrator, then delegates creation to a worker after approval.

---

## Manual sub-mode — natural language intake

### Step M1 — Parse the user's input

Read the user's full message and extract every field that is present or inferable:

| Signal in user text | Maps to |
|---------------------|---------|
| Core problem described | Title (≤10 words) + Description narrative |
| "on iOS / Android", device name | Environment OS + Device |
| "TestFlight", "debug build", "release", "staging URL" | Environment Build type / URL |
| A `PROJ-N` key mentioned | TC key or Story key |
| "blocking", "can't proceed", "crash", "unusable" | Priority → High or Highest |
| "wrong", "incorrect", "doesn't show", "empty" | Priority → Medium |
| "cosmetic", "typo", "minor" | Priority → Low |
| VPN state, network condition | Steps context |

Pre-populate all extractable fields before asking the user for anything.

### Step M2 — Ask only for what's genuinely missing

Minimum required to create the ticket:

- Title
- Description (what is broken + impact)
- Steps to Reproduce
- Actual Result
- Expected Result

These all have fallbacks — **never block creation** waiting for them:

- TC key → optional; skip the Defect link
- Story key → optional; skip the Story link and Story transition
- Assignee → Story's assignee, else current user (see `jira-helpers.md`)
- Priority → `Medium` default
- Environment → placeholder bullets per `conventions.md`

### Step M3 — Confirm before creating

Show the final summary and wait for explicit user approval before calling `bug-creation.md`. **Manual is the only sub-mode with this confirmation gate.**

---

## Explicit sub-mode — execution key + `--tcs` list

User: `/bug <EXEC_KEY> --tcs TC1,TC2,...`. Use when the caller already knows which failures are genuine product bugs (vs runner/test-data issues). Bypasses Xray failure detection entirely.

1. Parse `--tcs` — split on commas, strip whitespace → list of TC keys.
2. For each TC: use the get-issue operation with `fields=["summary","issuelinks"]`. Capture numeric id, key, summary, issuelinks.
3. Resolve parent Story — use `get_parent_story_key` from `jira-helpers.md`. Then fetch the Story for its assignee.
4. Fetch Xray steps — run the Xray get-test-steps operation with `issue_id="<TC_NUMERIC_ID>"` per TC.
5. Run results-file enrichment (see bottom of this file).
6. Run duplicate guard (`has_open_defect_bug` from `jira-helpers.md`). Skip TCs with an existing open Defect-linked Bug.
7. Print pending list and proceed immediately (no confirmation):
   ```
   Creating <N> bug(s) from <EXEC_KEY> --tcs:
     <TC_KEY> — <tc summary> → story <STORY_KEY> → assignee <name>
     ...
   ```
8. Create bugs — spawn one **Sonnet worker** per bug (`model: "sonnet"`) using the `bug-creation.md` subagent template, all in a single message (strict delegation — even for a single bug).

---

## Auto sub-mode — single Test Execution

User: `/bug <EXEC_KEY>` (no `--tcs`) where `<EXEC_KEY>` is a Test Execution.

1. Resolve the execution's numeric ID — use the get-issue operation on the exec key.
2. Fetch FAILED test numeric IDs by running the Xray get-execution-failures operation with `issue_id="<EXEC_NUMERIC_ID>"`. Returns `[{"issueId": str, "status": "FAILED"}, ...]`.
3. Resolve each failing TC — use the JQL search operation with `jql="id = <tc_numeric_id>"`, fields `["summary","issuelinks"]`.
4. Resolve parent Story key and Story assignee (same pattern as explicit).
5. Fetch Xray steps for each failing TC.
6. Run results-file enrichment.
7. Run duplicate guard.
8. Print pending list and proceed immediately.
9. Create bugs — one **Sonnet worker** per bug (`model: "sonnet"`) via the `bug-creation.md` template, all in a single message (even for a single bug).

---

## All sub-mode — every Test Execution in the project

User: `/bug all` (project already resolved by the dispatcher).

1. Fetch all Test Execution issues:
   ```
   jql:       project = <PROJECT_KEY> AND issuetype = "Test Execution"
   fields:    ["summary"]
   maxResults: 100
   ```
2. For each execution, fetch FAILED test numeric IDs by running the Xray get-execution-failures operation.
3. Deduplicate across executions — a TC can fail in multiple executions; keep the first occurrence.
4. For each unique failing TC — resolve key, summary, issuelinks, parent Story key, Story assignee, Xray steps.
5. Run results-file enrichment.
6. Run duplicate guard.
7. Print pending list and proceed immediately.
8. Create bugs — one **Sonnet worker** per bug (`model: "sonnet"`) via the `bug-creation.md` template, all in a single message (even for a single bug).

---

## Results-file enrichment

Explicit, auto, and all sub-modes optionally enrich Actual/Expected from a runner output file. Run mode (`run-mode.md`) writes this file at `output/results/<RUN_ID>/results.json`.

### Locate the file

In order of preference:

1. **Explicit path** — user passed `--results <path>`.
2. **Extracted run ID** — search the execution's `summary` for `RUN-YYYYMMDD-NNN`; if found, try `output/results/<RUN_ID>/results.json`.
3. **Latest run folder** — `glob.glob("output/results/RUN-*/results.json")` sorted by mtime, take the newest.
4. **Skip** — none of the above match; proceed with Xray-only enrichment.

```python
import os, json, glob, re

def load_results(explicit_path=None, exec_summary=""):
    candidates = []
    if explicit_path and os.path.exists(explicit_path):
        candidates.append(explicit_path)
    else:
        m = re.search(r'RUN-\d{8}-\d{3}', exec_summary or "")
        if m:
            p = f"output/results/{m.group()}/results.json"
            if os.path.exists(p):
                candidates.append(p)
        if not candidates:
            folders = sorted(
                glob.glob("output/results/RUN-*/results.json"),
                key=os.path.getmtime, reverse=True,
            )
            candidates = folders[:1]

    if not candidates:
        return {}

    results_map = {}
    with open(candidates[0], encoding="utf-8") as f:
        for entry in json.load(f):
            if "tcId" in entry:
                results_map[entry["tcId"]] = entry
    return results_map
```

### Per-TC extraction

```python
def get_enrichment(tc_key, results_map, xray_steps):
    """Returns (actual_result, expected_result, description_suffix)."""
    entry = results_map.get(tc_key, {})

    fail_step = next(
        (s for s in entry.get("steps", []) if s.get("status") in ("FAIL", "ERROR")),
        None,
    )

    if fail_step:
        actual   = fail_step.get("actual", "").strip()   or "See runner output"
        expected = fail_step.get("expected", "").strip() or "See test case"
    elif xray_steps:
        actual   = "TBD — see screenshots"
        expected = (xray_steps[-1].get("result") or "").strip() or "See test case"
    else:
        actual   = "TBD"
        expected = "TBD"

    notes = " | ".join(n for n in entry.get("notes", []) if n)
    description_suffix = f"\n\nRunner notes: {notes}" if notes else ""
    return actual, expected, description_suffix
```

Pass `actual`, `expected`, and `description_suffix` into `bug-creation.md` (append the suffix to the description narrative).
