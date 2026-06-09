---
name: qa-agent
description: End-to-end QA workflow for Jira projects using Xray Cloud — plan, run, and report. Use whenever a QA needs to (1) generate test cases from sprint stories and push them to Xray as a full Test/Test Set/Test Plan/Test Execution hierarchy, (2) execute test cases against a running app with screenshots and pass/fail assessment, or (3) file well-formed bug tickets manually or auto-filled from Xray Test Execution failures. Triggered by /qa-agent, /plan, /run, /bug, "generate test cases", "execute tests", "run manual tests", "report a bug", "log a bug", or any natural-language QA task that involves Jira issue keys (e.g. ABC-123), test cases, test executions, or bug reports.
---

# Xray QA Workflow

One skill that covers the QA loop on Jira projects backed by Xray Cloud — from sprint planning through test execution to bug filing. Designed so a QA on any project, in any company, can install it, point it at their Jira and Xray, and get a complete workflow.

## How to invoke

Three modes, picked by the argument or the user's words:

| Invocation | Mode | What it does |
|------------|------|--------------|
| `/plan <PROJECT>` or "generate test cases for the active sprint in PROJ" | **plan** | Reads active sprint stories, asks clarifying questions per story, generates positive + negative test cases, creates Test / Test Set / Test Plan / Test Execution in Xray, links everything |
| `/run --from-xray <STORY_KEY>` or "execute tests for PROJ-123 against staging" | **run** | Pulls test cases from Xray (or a JSON file), launches a browser, executes step-by-step with before/after screenshots, files bugs on failures, uploads results back to Xray |
| `/bug` (natural language) or `/bug <EXEC_KEY>` or `/bug <EXEC_KEY> --tcs A-1,A-2` or `/bug all` | **bug** | Files one or many bug tickets — from a free-form description, or auto-filled from Xray Test Execution failures |

Natural language works without the slash command — the dispatcher infers the mode from what the user says.

## Tooling

This skill needs the ability to talk to Jira and to Xray Cloud. It does not specify how — that's up to whatever the user has connected:

- **Jira** — use whatever Jira tooling is available. The skill describes operations by intent ("create a Jira issue", "fetch issue links", "add a comment") and relies on the agent to pick the right tool from what's connected.
- **Xray Cloud** — use whatever Xray Cloud tooling is available. The skill uses Xray's standard vocabulary (Test, Test Set, Test Plan, Test Execution; add step, link tests, fetch execution failures). The agent picks the appropriate tool for each operation.
- **Playwright** — needed only for run mode. Installable via `pip install playwright && python -m playwright install chromium`.

Before doing anything, check that the necessary tooling is connected. If something is missing, stop and tell the user — for example:

> I can't run the planner yet — I don't see any Jira tooling connected. Connect a Jira/Atlassian provider in your settings, then run this again.

Do not fall back to raw HTTP for Jira or Xray. If a connected provider doesn't expose a needed operation (e.g. attachment upload), tell the user; don't paper over it.

## How this skill is organised

This file is the dispatcher: it identifies the mode, verifies tooling, and routes. Detail lives in `references/`:

### Always-load

| File | What's in it |
|------|--------------|
| `references/conventions.md` | ADF shape (the 6-section bug description, the test-case ADF), link types, Xray vocabulary, the operations the skill needs |
| `references/jira-helpers.md` | Duplicate guard, assignee resolution, status transitions — shared by all modes |

### Mode-specific (load only when its mode is active)

| File | Mode |
|------|------|
| `references/audit.md` | bug mode (every invocation runs the audit first) |
| `references/bug-mode.md` | bug mode dispatcher (manual / explicit / auto / all sub-modes) |
| `references/bug-creation.md` | bug mode — the actual create → link → transition flow + subagent template |
| `references/plan-mode.md` | plan mode dispatcher |
| `references/plan-clarity-check.md` | plan mode — story clarity scoring and flag-and-skip |
| `references/plan-implementation-dialogue.md` | plan mode — generic questions to gather app-specific detail before writing TCs |
| `references/plan-xray-artifacts.md` | plan mode — create the Test / Test Set / Test Plan / Test Execution hierarchy |
| `references/run-mode.md` | run mode dispatcher |
| `references/run-playwright-runner.md` | run mode — the universal Playwright runner skeleton |
| `references/run-app-profile.md` | run mode — how to capture and use a per-app selector profile |

Read references on demand. Do not preload anything except `conventions.md` and `jira-helpers.md`.

## Step 1 — Detect mode

Look at the user's message:

- Contains "test case", "test plan", "active sprint", "generate", or starts with `/plan` → **plan mode**
- Contains "execute", "run tests", "manual tests", "playwright", or starts with `/run` → **run mode**
- Contains "bug", "report", "log", or starts with `/bug`, OR mentions an issue key with no other context → **bug mode**

If the user mentions a Jira key like `PROJ-123`, capture it — that's the project key (prefix) for subsequent calls. If no project is mentioned, ask once before proceeding.

When ambiguous, ask the user once which mode they want.

## Step 2 — Verify tooling for the chosen mode

| Mode | Needs |
|------|-------|
| plan | Jira tooling + Xray tooling |
| run  | Jira tooling + Xray tooling + Playwright installed |
| bug  | Jira tooling (always) + Xray tooling (only for explicit/auto/all sub-modes) |

If anything is missing, stop with a clear message naming what's missing and how the user can connect it.

## Step 3 — Route to the mode's reference

After tooling check passes:

- **plan** → read `references/plan-mode.md` and follow it
- **run** → read `references/run-mode.md` and follow it
- **bug** → read `references/audit.md` (every bug-mode invocation runs the audit first), then `references/bug-mode.md`

Each mode produces its own structured final report. Reports are designed to chain — e.g. run mode produces a `results.json` that bug mode can enrich descriptions from.

## How the modes connect

This is one workflow, not three unrelated tools:

```
┌─────────┐      ┌────────┐      ┌────────┐
│  plan   │ ───→ │  run   │ ───→ │  bug   │
└─────────┘      └────────┘      └────────┘
  Xray TCs        results.json    bugs filed,
  Test Plan       run-report.json linked to TCs,
  Test Exec                       Story moved
                                  to In Progress
```

- **plan** writes Test Cases into Xray. The Test Execution it creates is what **run** updates later.
- **run** writes `output/results/RUN-*/results.json`. When a step fails, run mode spawns a background bug-mode call with the failure context.
- **bug** reads `results.json` (when present) to enrich Actual/Expected. It links every bug to the failing Test Case (Defect link) and the parent Story (Relates link), and transitions both Bug and Story to In Progress.

## Universal rules

Apply across every mode:

- **Use whatever Jira and Xray tooling is connected.** Describe operations by intent and let the agent pick the right tool. Never fall back to raw HTTP for these services.
- **No hardcoded credentials, emails, cloud IDs, or project keys** — everything is resolved at runtime or asked from the user.
- **Project key always comes from the argument or a key mentioned in the message**, never guessed. Ask if missing.
- **Cloud ID** (or workspace identifier, depending on the tooling) — resolved once per session and reused.
- **Numeric IDs** are used for all Xray operations (steps, linking tests to test sets, etc.); issue keys are used for Jira links and most Jira operations. Capture both when creating any issue.
- **Subagents are self-contained** — when spawning a subagent, the prompt must include the absolute paths to the reference files the subagent needs to read. Subagents don't share the dispatcher's context.
- **Parallelism rule** — when 2+ independent tasks need doing (multiple bugs, multiple stories, multiple browser groups), spawn one subagent per task in a **single message**. Single-message parallelism is the only way they run concurrently.
- **Severity field** — don't set a Severity custom field unless the user confirms the project has one. Most projects don't, and setting it returns HTTP 400.
- **Honour the 6-section bug ADF** — Description, Steps to Reproduce, Actual Result, Expected Result, Environment, Root Cause Analysis. All h2 headings. Never level 3. See `conventions.md`.
- **One bug per failing test** in run/bug auto modes — never merge failures into one ticket.
- **Duplicate guard before every bug** — never re-create a bug for a TC that already has an open Defect-linked Bug.
