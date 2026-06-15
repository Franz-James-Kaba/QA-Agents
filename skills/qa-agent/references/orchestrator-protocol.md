# Orchestrator Protocol — Power Model + Worker Models

The qa-agent skill runs as a **two-tier system** for token efficiency:

```
┌────────────────────────────────────────────────────────┐
│  ORCHESTRATOR  — the dispatcher (run on a power model)   │
│  judgment · synthesis · user dialogue · final decisions  │
└───────────┬───────────────┬───────────────┬────────────┘
            ▼               ▼               ▼
      [Sonnet worker] [Sonnet worker] [Sonnet worker]
        one unit        one unit        one unit
       (TC / role /     mechanical,     returns
        bug)            self-contained  structured output
```

- **Orchestrator** = the main session running `SKILL.md`. Intended to run on a **power model (Opus)**. It never does bulk mechanical generation itself.
- **Workers** = subagents spawned via the Agent tool with `model: "sonnet"`. Each does **one** self-contained, templated unit of work and returns structured output.

This protocol is shared by all three modes. Each mode's reference file has a short **Delegation** section that points back here.

---

## The split rule (constant across modes)

| Orchestrator (Opus) keeps | Worker (Sonnet) does |
|---------------------------|----------------------|
| Reading stories / sprint, scoring clarity | Writing TC steps + ADF for one story |
| Clarifying dialogue with the user | Executing one role's TCs in the browser |
| Coverage strategy, TC-count decisions | Writing one 6-section ADF bug |
| Dedupe guard, severity, link/transition decisions | Straightforward pass/fail vision on a clear screenshot |
| Merging worker results, final report | — |
| Re-assessing escalated low-confidence items | Flagging low-confidence items for escalation |

**Rule of thumb:** if the work is templated, single-item, parallelizable, and verifiable from a fixed schema → it's a worker job. If it needs cross-item judgment, user interaction, or a final call → the orchestrator keeps it.

---

## Delegation policy: always delegate (strict)

Every mechanical unit goes to a Sonnet worker — **even a single story, single role, or single bug.** The orchestrator does not do the mechanical generation inline "because it's only one." This keeps the cost profile predictable and the orchestrator's context lean.

The only work the orchestrator does directly is the judgment/synthesis column above.

---

## The handoff contract

Every worker spawn MUST satisfy all four:

1. **Self-contained prompt.** The worker shares none of the orchestrator's context. The prompt must inline:
   - Absolute paths to every reference file the worker needs to read
   - All input data for this unit (story text, TC JSON, failure context — inline, not "see above")
   - Pre-resolved shared values (cloud_id, project key, account IDs) so the worker makes zero discovery calls
2. **Explicit output schema.** State the exact return format. Workers return **structured output only** (JSON or the named artifact) — never prose, never commentary.
3. **`model: "sonnet"`.** Pass it on the Agent call. (Vision-heavy run workers may use Sonnet too — it handles clear screenshots; ambiguous ones escalate.)
4. **Single-message parallelism.** When there are N units, spawn all N workers in **one message** so they run concurrently. One unit = one worker.

### Worker prompt skeleton

```
You are a worker for one <unit> of a qa-agent <mode> run.
Do NOT ask questions. Do the work and return ONLY the structured result below.

## Required reading (read first)
- <ABSOLUTE_PATH_TO_SKILL>/references/<files this unit needs>

## Pre-resolved shared values
- Cloud/workspace ID: <CLOUD_ID>
- Project key: <PROJECT_KEY>
- <other pre-resolved IDs>

## This unit's data
<all input for THIS unit, inline>

## Output schema (return EXACTLY this, nothing else)
<JSON schema or artifact format>

## Escalation
If you cannot complete a part with confidence, set "needs_orchestrator_review": true
and include "review_reason". Do not guess — flag it.
```

---

## Escalation path (quality guard)

Strict delegation does not mean blind delegation. A worker that hits a low-confidence
decision sets `needs_orchestrator_review: true` with a `review_reason` and returns what
it has. The orchestrator (Opus) then handles **only** those flagged items itself.

Typical escalations:
- **run:** an ambiguous after-screenshot where pass/fail isn't clear-cut
- **plan:** a story whose acceptance criteria contradict the implementation dialogue
- **bug:** a failure that may duplicate an existing open bug the worker can't fully verify

This keeps Opus spend proportional to genuine difficulty — the easy 90% stays on Sonnet,
the hard 10% gets power-model judgment.

---

## Per-mode delegation map

| Mode | Worker unit | What the worker produces | What the orchestrator keeps |
|------|-------------|--------------------------|------------------------------|
| **plan** | one story | TC steps + ADF (P4.2) and Xray artefacts (P5) | clarity check (P3), dialogue (P4.1), coverage strategy, final report |
| **run** | one role | executed TCs + raw results + confidence flags (R6) | TC resolution, SSO pre-auth, merge, escalated screenshots, early-abort |
| **bug** | one bug | created+linked+transitioned Bug (bug-creation template) | audit, dedupe guard, severity, which bugs to file |

Each mode reference file's **Delegation** section restates this with the concrete spawn details.

---

## Rules

- **The orchestrator never bulk-generates** TC steps, ADF bodies, or executes browser steps itself — always a worker.
- **Workers always get `model: "sonnet"`** and a fully self-contained prompt.
- **Strict delegation** — delegate even single units; do not inline "because it's just one."
- **Escalate, don't guess** — workers flag low-confidence items; the orchestrator resolves them on the power model.
- **One unit = one worker; spawn all in one message** for concurrency.
- **Workers return structured output only** — the orchestrator consumes without re-parsing prose.
