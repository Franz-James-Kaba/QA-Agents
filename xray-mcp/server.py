#!/usr/bin/env python3
"""
xray-mcp/server.py — Xray Cloud MCP Server for Claude Code.

Exposes the following tools:
  authenticate                     — verify credentials, return token metadata
  add_test_step                    — add a step to an Xray Test issue
  update_test_step                 — edit an existing step (action/data/result) by its ID
  remove_test_step                 — delete a step from a Test issue by its ID
  add_tests_to_test_set            — link Test issues into a Test Set
  add_tests_to_test_execution      — link Test issues into a Test Execution
  add_tests_to_test_plan           — link Test issues into a Test Plan
  add_test_executions_to_test_plan — link Test Executions into a Test Plan
  get_test_steps                   — retrieve steps for a Test issue
  get_test_execution_failures      — retrieve failed results from a Test Execution
  get_test_runs                    — retrieve all test runs (with run IDs) from a Test Execution
  update_test_run_status           — set PASS/FAIL/TODO/EXECUTING on a test run by its run ID

Authentication: Xray Cloud client-credentials flow (no manual token management needed).
All issue IDs must be numeric Jira IDs (e.g. "113080"), NOT keys (e.g. "TBL-131").
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Xray Cloud endpoints ────────────────────────────────────────────────────
XRAY_AUTH_URL    = "https://xray.cloud.getxray.app/api/v2/authenticate"
XRAY_GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"

# ── Credentials ─────────────────────────────────────────────────────────────
# Replace with your Xray Cloud API key pair.
# Generate at: https://docs.getxray.app/display/XRAYCLOUD/Global+Settings%3A+API+Keys
import os
CLIENT_ID     = os.environ.get("XRAY_CLIENT_ID", "YOUR_XRAY_CLIENT_ID_HERE")
CLIENT_SECRET = os.environ.get("XRAY_CLIENT_SECRET", "YOUR_XRAY_CLIENT_SECRET_HERE")

# ── Token cache ──────────────────────────────────────────────────────────────
_cache: dict = {"token": None, "expires_at": 0.0}


def _get_token() -> str:
    """Return a valid Bearer token, refreshing ~2 min before expiry."""
    now = time.time()
    if _cache["token"] and _cache["expires_at"] > now + 120:
        return _cache["token"]

    payload = json.dumps({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()

    req = urllib.request.Request(
        XRAY_AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()

    # Xray returns the token as a bare JSON string (with surrounding quotes)
    token = raw.strip().strip('"')
    _cache["token"] = token
    _cache["expires_at"] = now + 82_800  # 23 h
    return token


def _gql(query: str, variables: dict) -> dict:
    """Execute a GraphQL request against the Xray Cloud API."""
    token = _get_token()
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        XRAY_GRAPHQL_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ── MCP server ───────────────────────────────────────────────────────────────
app = Server("xray-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="authenticate",
            description="Verify Xray Cloud credentials. Returns token length and TTL.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="add_test_step",
            description=(
                "Add one step to an Xray Test issue. "
                "issue_id must be the numeric Jira ID, not the key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Numeric Jira issue ID of the Test (e.g. '113080')",
                    },
                    "action":  {"type": "string", "description": "What the tester does"},
                    "data":    {"type": "string", "description": "Test data / inputs (use '-' if none)"},
                    "result":  {"type": "string", "description": "Expected observable outcome"},
                },
                "required": ["issue_id", "action", "result"],
            },
        ),
        Tool(
            name="update_test_step",
            description=(
                "Edit an existing step on an Xray Test issue. "
                "Requires the numeric issue_id and the step_id returned by add_test_step or get_test_steps. "
                "Only the fields provided are updated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Numeric Jira issue ID of the Test (e.g. '113080')",
                    },
                    "step_id": {
                        "type": "string",
                        "description": "ID of the step to update (returned by get_test_steps)",
                    },
                    "action":  {"type": "string", "description": "Updated action text"},
                    "data":    {"type": "string", "description": "Updated test data (use '-' if none)"},
                    "result":  {"type": "string", "description": "Updated expected result"},
                },
                "required": ["issue_id", "step_id"],
            },
        ),
        Tool(
            name="remove_test_step",
            description=(
                "Delete a step from an Xray Test issue by its step ID. "
                "Use get_test_steps first to find the step ID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Numeric Jira issue ID of the Test",
                    },
                    "step_id": {
                        "type": "string",
                        "description": "ID of the step to remove",
                    },
                },
                "required": ["issue_id", "step_id"],
            },
        ),
        Tool(
            name="get_test_runs",
            description=(
                "Retrieve all test runs from a Test Execution, including their run IDs, "
                "test issue IDs, and current status. Use the run ID with update_test_run_status "
                "to record PASS/FAIL results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Numeric Jira issue ID of the Test Execution",
                    },
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="update_test_run_status",
            description=(
                "Set the status of a specific test run inside a Test Execution. "
                "Valid statuses: TODO, EXECUTING, PASSED, FAILED, ABORTED. "
                "Call get_test_runs first to obtain the run ID for each test."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The test run ID (from get_test_runs, not the issue key)",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["TODO", "EXECUTING", "PASSED", "FAILED", "ABORTED"],
                        "description": "New status to set on the test run",
                    },
                },
                "required": ["run_id", "status"],
            },
        ),
        Tool(
            name="add_tests_to_test_set",
            description="Link one or more Test issues into a Test Set.",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_set_issue_id": {"type": "string"},
                    "test_issue_ids":    {"type": "array", "items": {"type": "string"}},
                },
                "required": ["test_set_issue_id", "test_issue_ids"],
            },
        ),
        Tool(
            name="add_tests_to_test_execution",
            description="Link one or more Test issues into a Test Execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_exec_issue_id": {"type": "string"},
                    "test_issue_ids":     {"type": "array", "items": {"type": "string"}},
                },
                "required": ["test_exec_issue_id", "test_issue_ids"],
            },
        ),
        Tool(
            name="add_tests_to_test_plan",
            description="Link one or more Test issues into a Test Plan.",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_plan_issue_id": {"type": "string"},
                    "test_issue_ids":     {"type": "array", "items": {"type": "string"}},
                },
                "required": ["test_plan_issue_id", "test_issue_ids"],
            },
        ),
        Tool(
            name="add_test_executions_to_test_plan",
            description="Link one or more Test Execution issues into a Test Plan.",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_plan_issue_id":  {"type": "string"},
                    "test_exec_issue_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["test_plan_issue_id", "test_exec_issue_ids"],
            },
        ),
        Tool(
            name="get_test_steps",
            description="Retrieve all steps attached to a Test issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="get_test_execution_failures",
            description="Retrieve failed test results from a Test Execution issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                },
                "required": ["issue_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        # ── authenticate ────────────────────────────────────────────────────
        if name == "authenticate":
            token = _get_token()
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "token_length": len(token),
                "expires_in_seconds": int(_cache["expires_at"] - time.time()),
            }))]

        # ── add_test_step ────────────────────────────────────────────────────
        elif name == "add_test_step":
            resp = _gql(
                """
                mutation AddTestStep($issueId: String!, $step: CreateStepInput!) {
                  addTestStep(issueId: $issueId, step: $step) {
                    id
                    action
                    data
                    result
                  }
                }
                """,
                {
                    "issueId": arguments["issue_id"],
                    "step": {
                        "action": arguments["action"],
                        "data":   arguments.get("data", "-"),
                        "result": arguments["result"],
                    },
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["addTestStep"]))]

        # ── add_tests_to_test_set ────────────────────────────────────────────
        elif name == "add_tests_to_test_set":
            resp = _gql(
                """
                mutation AddTestsToTestSet($issueId: String!, $testIssueIds: [String!]!) {
                  addTestsToTestSet(issueId: $issueId, testIssueIds: $testIssueIds) {
                    addedTests
                    warning
                  }
                }
                """,
                {
                    "issueId":       arguments["test_set_issue_id"],
                    "testIssueIds":  arguments["test_issue_ids"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["addTestsToTestSet"]))]

        # ── add_tests_to_test_execution ──────────────────────────────────────
        elif name == "add_tests_to_test_execution":
            resp = _gql(
                """
                mutation AddTestsToTestExecution($issueId: String!, $testIssueIds: [String!]!) {
                  addTestsToTestExecution(issueId: $issueId, testIssueIds: $testIssueIds) {
                    addedTests
                    warning
                  }
                }
                """,
                {
                    "issueId":      arguments["test_exec_issue_id"],
                    "testIssueIds": arguments["test_issue_ids"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["addTestsToTestExecution"]))]

        # ── add_tests_to_test_plan ───────────────────────────────────────────
        elif name == "add_tests_to_test_plan":
            resp = _gql(
                """
                mutation AddTestsToTestPlan($issueId: String!, $testIssueIds: [String!]!) {
                  addTestsToTestPlan(issueId: $issueId, testIssueIds: $testIssueIds) {
                    addedTests
                    warning
                  }
                }
                """,
                {
                    "issueId":      arguments["test_plan_issue_id"],
                    "testIssueIds": arguments["test_issue_ids"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["addTestsToTestPlan"]))]

        # ── add_test_executions_to_test_plan ─────────────────────────────────
        elif name == "add_test_executions_to_test_plan":
            resp = _gql(
                """
                mutation AddTestExecutionsToTestPlan($issueId: String!, $testExecIssueIds: [String!]!) {
                  addTestExecutionsToTestPlan(issueId: $issueId, testExecIssueIds: $testExecIssueIds) {
                    addedTestExecutions
                    warning
                  }
                }
                """,
                {
                    "issueId":           arguments["test_plan_issue_id"],
                    "testExecIssueIds":  arguments["test_exec_issue_ids"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["addTestExecutionsToTestPlan"]))]

        # ── update_test_step ─────────────────────────────────────────────────
        elif name == "update_test_step":
            step_fields: dict = {}
            if "action" in arguments:
                step_fields["action"] = arguments["action"]
            if "data" in arguments:
                step_fields["data"] = arguments["data"]
            if "result" in arguments:
                step_fields["result"] = arguments["result"]
            resp = _gql(
                """
                mutation UpdateTestStep($issueId: String!, $stepId: String!, $step: UpdateStepInput!) {
                  updateTestStep(issueId: $issueId, stepId: $stepId, step: $step) {
                    id
                    action
                    data
                    result
                  }
                }
                """,
                {
                    "issueId": arguments["issue_id"],
                    "stepId":  arguments["step_id"],
                    "step":    step_fields,
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps(resp["data"]["updateTestStep"]))]

        # ── remove_test_step ─────────────────────────────────────────────────
        elif name == "remove_test_step":
            resp = _gql(
                """
                mutation RemoveTestStep($issueId: String!, $stepId: String!) {
                  removeTestStep(issueId: $issueId, stepId: $stepId)
                }
                """,
                {
                    "issueId": arguments["issue_id"],
                    "stepId":  arguments["step_id"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps({"removed": True, "step_id": arguments["step_id"]}))]

        # ── get_test_runs ────────────────────────────────────────────────────
        elif name == "get_test_runs":
            resp = _gql(
                """
                query GetTestRuns($testExecIssueIds: [String], $limit: Int!) {
                  getTestRuns(testExecIssueIds: $testExecIssueIds, limit: $limit) {
                    total
                    results {
                      id
                      status { name color }
                      test { issueId jira(fields: ["key", "summary"]) }
                      testExecution { issueId }
                    }
                  }
                }
                """,
                {"testExecIssueIds": [arguments["issue_id"]], "limit": 100},
            )
            _raise_on_errors(resp)
            data = resp.get("data", {}).get("getTestRuns") or {}
            runs = data.get("results") or []
            return [TextContent(type="text", text=json.dumps({"runs": runs, "total": data.get("total", len(runs))}))]

        # ── update_test_run_status ───────────────────────────────────────────
        elif name == "update_test_run_status":
            resp = _gql(
                """
                mutation UpdateTestRunStatus($id: String!, $status: String!) {
                  updateTestRunStatus(id: $id, status: $status)
                }
                """,
                {
                    "id":     arguments["run_id"],
                    "status": arguments["status"],
                },
            )
            _raise_on_errors(resp)
            return [TextContent(type="text", text=json.dumps({
                "updated": True,
                "run_id": arguments["run_id"],
                "status": arguments["status"],
            }))]

        # ── get_test_steps ───────────────────────────────────────────────────
        elif name == "get_test_steps":
            resp = _gql(
                """
                query GetTestSteps($issueId: String!) {
                  getTest(issueId: $issueId) {
                    steps {
                      id
                      action
                      data
                      result
                    }
                  }
                }
                """,
                {"issueId": arguments["issue_id"]},
            )
            _raise_on_errors(resp)
            steps = (resp.get("data", {}).get("getTest") or {}).get("steps") or []
            return [TextContent(type="text", text=json.dumps({"results": steps}))]

        # ── get_test_execution_failures ──────────────────────────────────────
        elif name == "get_test_execution_failures":
            resp = _gql(
                """
                query GetTestExecutionResults($testExecIssueIds: [String], $limit: Int!) {
                  getTestRuns(testExecIssueIds: $testExecIssueIds, limit: $limit) {
                    total
                    results {
                      id
                      status { name color }
                      test { issueId jira(fields: ["key", "summary"]) }
                    }
                  }
                }
                """,
                {"testExecIssueIds": [arguments["issue_id"]], "limit": 100},
            )
            _raise_on_errors(resp)
            data = resp.get("data", {}).get("getTestRuns") or {}
            all_runs = data.get("results") or []
            failures = [t for t in all_runs if t["status"]["name"] in ("FAIL", "FAILED")]
            return [TextContent(type="text", text=json.dumps({"failures": failures, "total": data.get("total", len(all_runs))}))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as exc:
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


def _raise_on_errors(resp: dict) -> None:
    """Raise RuntimeError if the GraphQL response contains errors."""
    if "errors" in resp:
        raise RuntimeError(json.dumps(resp["errors"]))


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
