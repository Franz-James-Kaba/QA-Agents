# Implementation Dialogue

Before writing test cases for a story, capture the real implementation detail from the user so test steps use exact screen names, field labels, button text, API endpoints, and error messages — not inferred placeholders.

Runs for every story that passes the clarity check.

## Step 1 — Classify the story by surface and pattern

Read the story summary and description. Pick a surface and one or more patterns:

**Surface:** `web | mobile | backend | desktop | mixed`

**Patterns (pick all that apply):**
- **form** — user fills fields and submits (create, search, login, signup)
- **list-or-detail** — app fetches and renders data (list, table, detail page)
- **auth** — login, signup, password reset, biometric, SSO, session management
- **navigation** — multi-step flow, back navigation, deep links, redirects
- **toggle-or-setting** — user enables/disables a feature or changes a preference
- **realtime-or-poll** — notifications, websocket events, polling, push
- **upload-or-download** — file in or file out
- **integration** — third-party API call, webhook, payment, OAuth
- **state-or-connectivity** — offline mode, VPN required, background/foreground

If you can't tell from the story, ask the user before going further.

## Step 2 — Ask base questions (always)

Print verbatim, substituting the story key and summary, then wait for the user's reply:

```
Implementation details for <STORY_KEY> — <story summary>
────────────────────────────────────────────────────────
Please answer so the test cases reflect the real app:

1. What is the exact name of the screen / page / route where this feature lives?
2. Walk through the user journey step by step — what does the user do from entry to completion?
3. What are the exact labels of any buttons, tabs, or navigation items the user interacts with?
4. What happens on success? (navigation destination, success message text, state change)
5. What error messages or error states are shown when something goes wrong?
```

## Step 3 — Append pattern-specific questions

For each pattern matched in Step 1, append the relevant block. Number them sequentially starting from 6.

**form**:
```
6. List every field with its type (text, dropdown, date picker, checkbox, etc.) and whether it is required.
7. When is inline validation shown — on blur, on submit, or real-time as the user types?
8. What API endpoint and HTTP method does submit call?
```

**list-or-detail**:
```
6. What API endpoint and HTTP method fetches the data?
7. What fields or columns are shown per item?
8. Is there pull-to-refresh, pagination, infinite scroll, or auto-refresh?
9. What is the empty state? (text, illustration, call-to-action)
```

**auth**:
```
6. What triggers auth — app launch, route guard, explicit user action, or session timeout?
7. What is the fallback when the primary method fails or is unavailable?
8. How many failed attempts are allowed before lockout or fallback?
9. Where does the user land after successful auth?
```

**navigation**:
```
6. Is back navigation allowed at every step? If not, where is it blocked?
7. Are there guards / redirects (e.g. unsaved-changes prompt, auth required)?
8. What URL or deep-link pattern represents each step?
```

**toggle-or-setting**:
```
6. Where is the toggle / setting located in the UI?
7. Is the change applied immediately, or after a save action?
8. What is the visual confirmation when the change is saved?
```

**realtime-or-poll**:
```
6. What triggers the realtime event — websocket message, polling interval, push notification?
7. How quickly should the UI update after the trigger? (target latency)
8. What does the UI look like before vs after the event?
```

**upload-or-download**:
```
6. What file types and size limits are accepted?
7. What endpoint handles the transfer, and is it multipart / chunked / direct?
8. What is the progress / completion / error UI?
```

**integration**:
```
6. Which third-party service or API is involved?
7. What is the integration's failure mode visible to the user? (error code, retry UI, fallback)
8. Are there idempotency keys or duplicate-call protections?
```

**state-or-connectivity**:
```
6. What conditions are checked — internet only, VPN required, specific service reachable, or all?
7. How often is the check re-run — on app open, on every API call, on foreground resume?
8. What is the exact on-screen message when connectivity / state is insufficient?
```

## Step 4 — Wait for the user's answers

**Do not proceed** to test case generation until the user has replied. If a critical answer is missing or ambiguous (e.g. "the form has some fields"), ask one targeted follow-up and wait again before continuing.

## Step 5 — Store as Implementation Context for this story

Hold the answers in memory as **Implementation Context: `<STORY_KEY>`**. The test case generator (back in `plan-mode.md` Step P4) uses this context to:

- Use the real screen name, field labels, and button text in every action step
- Use the real API endpoint in negative test cases (e.g. "Mock POST `/api/leave` to return 500")
- Use the real error message text in expected results
- Use the real navigation destination in success expected results
- Use the real field list (with required flags) in form-validation test cases

If a detail was not provided by the user, make the best inference from the story description but mark it with `[ASSUMED]` in the step text so it can be corrected after review.
