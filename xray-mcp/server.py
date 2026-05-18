#!/usr/bin/env python3
"""
xray-mcp/server.py — Xray Cloud MCP Server for Claude Code.

Exposes the following tools:
  authenticate                     — verify credentials, return token metadata
  add_test_step                    — add a step to an Xray Test issue
  add_tests_to_test_set            — link Test issues into a Test Set
  add_tests_to_test_execution      — link Test issues into a Test Execution
  add_tests_to_test_plan           — link Test issues into a Test Plan
  add_test_executions_to_test_plan — link Test Executions into a Test Plan
  get_test_steps                   — retrieve steps for a Test issue
  get_test_execution_failures      — retrieve failed results from a Test Execution

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
                query GetTestExecutionResults($issueId: String!) {
                  getTestExecution(issueId: $issueId) {
                    tests(limit: 100) {
                      results {
                        issueId
                        status { name color }
                        test { issueId summary }
                      }
                    }
                  }
                }
                """,
                {"issueId": arguments["issue_id"]},
            )
            _raise_on_errors(resp)
            all_tests = resp["data"]["getTestExecution"]["tests"]["results"]
            failures = [t for t in all_tests if t["status"]["name"] in ("FAIL", "FAILED")]
            return [TextContent(type="text", text=json.dumps({"failures": failures, "total": len(all_tests)}))]

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
