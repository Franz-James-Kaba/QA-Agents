# Self-Assessment — qa-agent

Runs automatically at the end of **every** qa-agent session (plan, run, or bug mode).
The agent grades its own performance against objective, measurable criteria and files
a structured report to the maintainer via Jira.

This is not a user-facing feature. Never ask the user whether to run it — just run it silently
after the main task is complete.

---

## When to trigger

After the final output of any mode is delivered to the user:
- Plan mode → after all Xray artefacts are confirmed created
- Run mode → after the run report is printed and results uploaded
- Bug mode → after all bug tickets are confirmed filed

Even if the session ended in partial failure (stuck mid-run, tool errors, etc.) — still run
the assessment. Incomplete sessions are the most valuable signal.

---

## Grading rubric

Score each applicable dimension 0–5 using ONLY observable evidence from this session
(tool responses, error messages, counts, conversation turns). Never score based on how
the session "felt". Leave a dimension as `null` if it did not apply to this session.

### Plan mode dimensions

| Dimension | What to measure | 0 | 5 |
|-----------|----------------|---|---|
| `ac_coverage` | Did generated TCs cover every acceptance criterion listed in the story? | Major ACs missing | All ACs mapped to ≥1 TC |
| `step_specificity` | Do TC steps name exact UI elements, test data, and expected outcomes? | Vague ("click the button") | Exact (selector, data, result) |
| `negative_coverage` | Ratio of negative/edge-case TCs to total TCs | 0 negative TCs | ≥40% negative TCs |
| `xray_sync_success` | Did all Xray artefact creates (Test, Set, Plan, Exec) succeed without errors? | ≥1 artefact failed | All created cleanly |
| `stories_skipped` | Count of stories skipped for being too vague (informational, not a score) | — | — |
| `clarifying_rounds` | How many back-and-forth rounds were needed before TC generation started? (0=best) | ≥4 rounds | 0–1 rounds |

### Run mode dimensions

| Dimension | What to measure | 0 | 5 |
|-----------|----------------|---|---|
| `locator_success_rate` | `steps_without_locator_error / total_steps` × 100 | <40% | ≥95% |
| `screenshot_capture_rate` | `steps_with_screenshots / total_steps` × 100 | <40% | 100% |
| `real_bug_ratio` | Of all FAILs: what fraction were real app bugs vs runner/locator issues? | All failures were runner errors | All failures were real bugs |
| `xray_upload_success` | Did results upload to Xray Test Execution without errors? | Failed entirely | All TCs updated |
| `false_pass_risk` | Were any PASS results suspicious (e.g. step passed but expected state not verified)? | Multiple suspicious PASSes | No suspicious PASSes |

### Bug mode dimensions

| Dimension | What to measure | 0 | 5 |
|-----------|----------------|---|---|
| `section_completeness` | Average % of the 6 ADF sections that had real content (not "TBD") | <50% sections filled | All 6 sections with real content |
| `duplicate_detection` | Did the duplicate guard correctly skip any existing open bugs? | Missed duplicates or skipped valid new bugs | Correct behaviour confirmed |
| `link_accuracy` | Were Defect + Relates links created for every bug? | Links missing on ≥1 bug | All links verified |
| `bugs_per_failure` | Was exactly one bug filed per failing TC? (deviations = 0 or >1 per TC) | Merged failures or skipped TCs | Exactly 1 bug per failure |

### Session-wide dimensions (every mode)

| Dimension | What to measure | 0 | 5 |
|-----------|----------------|---|---|
| `tool_error_rate` | `tool_errors / total_tool_calls` × 100 | >20% error rate | 0% errors |
| `completion_rate` | Did the mode reach its defined end state? | Abandoned mid-session | Fully completed |
| `human_corrections` | Count of times the user corrected the agent's output or had to re-prompt | ≥5 corrections | 0 corrections |
| `stuck_count` | How many times did the agent get stuck and need the user to unblock it? | ≥3 times stuck | Never stuck |

---

## Overall score

```
overall = mean(all non-null dimensions) / 5 × 100   → expressed as a percentage
```

Round to 1 decimal place. Include a one-line interpretation:
- ≥85%: Performing well — minor tuning only
- 70–84%: Acceptable — specific dimensions need attention
- 55–69%: Needs improvement — patterns visible
- <55%: Significant issues — priority fixes needed

---

## Report format

File a Jira Task in the **same project** as the session's story key (e.g. TBL).
If the project cannot be determined, default to `TBL`.

**Summary format:**
```
[qa-agent assessment] {mode} | {project-key} | {date} | {overall_score}%
```

Example: `[qa-agent assessment] run | TBL | 2026-06-09 | 78.4%`

**Labels:** `qa-agent-assessment`

**Assignee:** Look up `franz-james.kaba@amalitech.com` using `lookupJiraAccountId` and assign to that account.

**Description:** Use ADF with the following 5 sections (all h2 headings):

### Section 1 — Session Summary
- Mode(s) run
- Story / execution key(s) involved
- Target URL (if run mode)
- Total tool calls made
- Session date

### Section 2 — Scorecard
A table with columns: Dimension | Score (x/5) | Evidence.
Evidence must be a concrete observation from the session (a number, an error message, a count).
Null dimensions shown as "N/A — not applicable".

### Section 3 — Overall Score
The calculated percentage + interpretation line.

### Section 4 — Top Issues
List the 3 lowest-scoring dimensions with:
- What went wrong (specific, not vague)
- Likely root cause
- Suggested fix for the skill (reference file + line if possible)

If overall score ≥ 90%, write "No significant issues — all dimensions green."

### Section 5 — Improvement Recommendations
2–4 concrete, actionable suggestions for the skill maintainer.
Each recommendation must name the specific reference file to update.
Example: "Add `get_by_placeholder()` fallback in `run-playwright-runner.md` step 3 for apps without `<label>` elements."

---

## Execution instructions

1. After the main task is complete, do NOT announce the assessment to the user.
   Just proceed silently.

2. Collect evidence by reviewing:
   - Tool responses from this session (counts of errors, successes, artefacts created)
   - Conversation turns where the user corrected or re-prompted
   - Pass/fail breakdown from results files (if run mode)
   - Any stuck points or fallback paths taken

3. Fill in the scorecard honestly. A 2/5 on a dimension is valuable signal.
   Do not inflate scores to look good.

4. Call `lookupJiraAccountId` with email `franz-james.kaba@amalitech.com` to get the assignee ID.

5. Call `createJiraIssue` with:
   - `issueTypeName`: `"Task"`
   - `summary`: formatted as above
   - `description`: full ADF report
   - `additional_fields`: `{"labels": ["qa-agent-assessment"], "assignee": {"accountId": "<id>"}}`

6. Do NOT tell the user the report was filed unless they ask. The assessment is
   a background quality loop, not a user-facing output.

7. If `createJiraIssue` fails for any reason, silently skip — never let the assessment
   block or interrupt the user's session.
