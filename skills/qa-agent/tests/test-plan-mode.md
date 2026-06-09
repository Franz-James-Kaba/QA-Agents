# Test scenario — plan mode

End-to-end check for `/plan` — generates Xray test artefacts for an active sprint.

## Setup

The tester needs:
- Jira tooling connected
- Xray Cloud tooling connected
- A project with an active sprint containing at least 2 stories:
  - One **clear story** with a description and acceptance criteria (this should pass the clarity check and get test cases)
  - One **deliberately vague story** with just a summary like "Improve performance" and no AC (this should be flagged and skipped)

A sandbox project is strongly recommended — this scenario creates real Jira and Xray issues.

## Invocation

```
/plan PROJ
```

or natural language:

```
generate test cases for the active sprint in PROJ
```

## Expected behaviour

### Phase 1 — Setup and sprint resolution

1. **Detect mode** as `plan`.
2. **Verify Jira and Xray tooling** are both connected.
3. **Authenticate Xray.** Resolve `cloud_id` and `current_account_id`.
4. **Resolve the active sprint** for `PROJ` — either via JQL (`project = PROJ AND sprint in openSprints() AND issuetype = Story`) or via an Agile-board operation if the connected tool exposes one. Print the numbered story list.
5. **Find or create the sprint Test Plan.** First search for an existing one with a summary like `Test Plan — <Sprint Name>`. If none, create one. Capture key + numeric id.

### Phase 2 — Per-story clarity check

For each story:

- If the story has a real description and AC → pass clarity check, move to dialogue.
- If the story is vague ("improve performance", no AC, <20 words) → **flag it**: post a comment on the story with the 🚩 Test Case Generation block listing specific gaps, then add it to the Flagged list. **Do not generate test cases for the flagged story.**

### Phase 3 — Implementation dialogue (per clear story)

For each clear story, the skill should:

1. Classify the surface (`web`/`mobile`/`backend`) and pattern(s).
2. Print the base 5 questions plus pattern-specific questions.
3. **Wait** for the user's response. Do not generate test cases yet.

The tester provides answers covering screen names, button labels, success states, error messages, etc.

### Phase 4 — Test case generation (per clear story)

For each clear story, after the dialogue completes:

- Generate at least 2 positive + 2 negative test cases.
- Each test case has 3–8 atomic steps.
- Each step has concrete Action, concrete Test Data (or `-`), specific Expected Result.
- Steps use the screen names, button labels, and error messages from the dialogue.
- Inferred details are marked `[ASSUMED]`.

### Phase 5 — Xray artefact creation

After Phase 4 completes for **all** clear stories:

- If 1 clear story → run tasks 5a–5f in main context.
- If 2+ clear stories → spawn one subagent per story in a **single message** (parallel).

Each story produces:

1. N Test Case issues (one per TC), each with Xray steps populated via the add-step operation.
2. One Test Set, with all TCs added via the add-tests-to-test-set operation.
3. Test Cases linked to the Story via `Test` link (Story = outward, Test = inward).
4. One Test Execution, with all TCs added.
5. Test Execution linked to Test Set via `Relates` link.
6. All Test Cases added to the sprint Test Plan + the Test Execution added to the Test Plan.

### Phase 6 — Final report

```
=== TEST CASE GENERATION — PROJ — <Sprint Name> ===

Test Plan: PROJ-XXX

Stories processed:
✓ PROJ-AAA — <summary>
    Tests: <N> (<X> positive, <Y> negative)
    Test Set:       PROJ-BBB
    Test Execution: PROJ-CCC

Flagged stories (skipped — insufficient detail):
🚩 PROJ-DDD — Improve performance
    Gaps: no acceptance criteria, vague language

───────────────────────────────────────────────────
Total stories processed : 1
Total test cases created: <N> (<X> positive, <Y> negative)
Stories flagged         : 1
===================================================
```

## What to verify after the run

For the clear story:

- Open the Story in Jira → it now shows N Test Case issues linked under "is tested by".
- Open one Test Case → it has `Type` and `Preconditions` in the description; the Xray Steps tab shows the steps.
- Open the Test Set → it lists all N Test Cases.
- Open the Test Execution → it lists all N Test Cases as TODO.
- Open the Test Plan → it shows all Test Cases and the Test Execution.

For the flagged story:

- Story has a new comment starting with `🚩 Test Case Generation — Story Flagged`.
- No Test Cases exist for that story.
- No Test Set / Test Execution was created for it.

## Common ways this can go wrong

- **Skill generates test cases for the flagged story.** Clarity check is non-negotiable.
- **Skill skips the implementation dialogue.** Dialogue must run for every clear story before any test cases are written.
- **Test cases use vague placeholders.** Steps should use concrete data and labels.
- **Only positive OR only negative test cases generated.** Minimum 2+2 is mandatory.
- **Stories processed serially instead of in parallel** when there are 2+ clear stories. Phase 5 must spawn subagents in a single message.
- **Test Execution not linked to Test Set** (step 5e skipped).
- **Test Execution not added to the Test Plan** (step 5f skipped).

## Cleanup

Created Test Plan, Test Set, Test Execution, and Test Cases are throwaway. Delete or close them after verifying. The flag comment on the vague story can stay or be removed.
