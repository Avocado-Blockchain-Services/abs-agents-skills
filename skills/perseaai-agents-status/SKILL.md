---
name: perseaai-agents-status
description: >-
  Use when the user wants to check whether a project's logcore integration is
  actually working after setup, or wants the current state of a project on the
  Persea AI agents platform — logs arriving, issues grouped, classifier
  verdicts, debugger runs, PRs awaiting review. Requires the platform MCP
  server to be connected.
license: Apache-2.0
metadata:
  author: Avocado Blockchain Services
  version: "0.1.0"
---

<!-- The counters come from persea-agents-api:src/services/stats_service.py
     (ProjectStatsResponse) and are exposed over MCP by
     src/mcp/tools/project_status.py. The diagnosis below lives here, not
     there, so the criteria can change without an API deploy. Keep the field
     names in sync. -->

# Persea AI Agents Platform — Project Status

Answer two questions: *is the integration working?* and *how is the project
doing?* Which one gets answered is decided from the data, not by asking.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`list_projects`, `get_project_status`, `get_project_issue`, and
`list_debugger_runs`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

This skill never writes. It cannot retry a run, close an issue, or toggle a
module. When the fix is a setup step, hand back to `perseaai-agents-setup`.

## Phase 0: Identify the project

1. Call `list_projects`.
2. Read the local remote with `git remote -v` and match it against each
   service's `repo_full_name`.
3. Exactly one match: continue with that project. Zero or several: ask the
   user which project they mean. Do not guess.

## Choosing the phase

Call `get_project_status` with the project id. Then decide, without asking:

- any service with `status: "NO_DATA"`, **or** `stats.logs` is `null`, **or**
  `stats.logs.errors_received == 0` → **Phase 1**
- otherwise → **Phase 2**

Read `stats.logs` for existence before reading its counter. The object is
`null` when the logs module is off, and reading the counter first breaks this
skill on exactly the project that has the least data.

Phase 1 is not "something is broken". It can end at "all good, no errors yet"
— see row 6.

## Phase 1: Diagnose

Walk the table in order and **stop at the first link that fails**. Reporting
three problems when the second is a consequence of the first is how a skill
becomes noise.

| # | Condition | Reading | What to tell the user |
|---|---|---|---|
| 1 | `pr_url` is null | The integration was never completed | Hand back to `perseaai-agents-setup` |
| 2 | `infra_status: "NOT_CONFIGURED"` (backends only) | The Cloud Logging sink is missing | The sink was never created — resume `perseaai-agents-setup` |
| 3 | `infra_status: "PENDING_AUTH"` | Sink created, writer identity not authorized in GCP | The `gcloud` grant from setup never ran — resume `perseaai-agents-setup` |
| 4 | `status: "NO_DATA"` and `last_activity_at` is null | Not one log ever arrived | The PR may be unmerged or undeployed, or the API key or endpoint is wrong. Resume `perseaai-agents-setup` to re-validate against a **real emitted line**, not a hand-written sample |
| 5 | `status: "ACTIVE"` but `last_activity_at` older than 24h | Logs were arriving and stopped | Check the most recent deploy |
| 6 | `errors_received: 0`, service active and recent | **Healthy.** No errors yet | Say so as good news. Offer to trigger a real error if they want an end-to-end proof |
| 7 | `errors_received > 0`, `issues_grouped: 0` | Logs arrive but nothing groups | Severity below ERROR, or the entry shape does not validate. Resume `perseaai-agents-setup` to check the wire format |
| 8 | `stats.classifier` is `null` | **Off, not broken** | Say it is disabled. Do not diagnose further down |
| 9 | `classified: 0` with `unidentified > 0` | The classifier runs but cannot classify | Missing repo context or code snippet |
| 10 | `stats.debugger` is `null` | **Off, not broken** | Same as row 8 |
| 11 | `classified > 0`, `approved: 0`, `needs_attention: 0` | May be legitimate: the debugger skips `complex` issues | Call `list_debugger_runs` to confirm whether any run happened at all |
| 12 | `needs_attention > 0` | Runs ended without a fix | Call `list_debugger_runs` and read `termination_reason` |

A frontend service (`service_type: "WEB_APP_FRONTEND"`) posts to the gateway
over HTTP and has no Cloud Logging sink, so rows 2 and 3 never apply to it.
`infra_status` being null on a frontend is normal, not a finding.

## Phase 2: Report

Narrate the funnel in order: errors received → issues grouped → classified →
debugger runs → PRs awaiting review → resolved. Close with `summary`
(`auto_resolve_rate`, `mean_time_to_fix_hours`, `awaiting_review`) and with
`agents[]`: what is running right now.

If the user then asks about one specific case, drill down: call
`get_project_issue` for an error's full history, or call `list_debugger_runs`
for what the debugger has been doing.

**`awaiting_review` is the actionable number, not a statistic.** Those are pull
requests the debugger opened that are waiting on a human. End the report
pointing there, not at whichever number is largest.

## Three traps

1. **A disabled module reports `null`, not `0`.** `classifier: null` means off;
   `classifier: {"classified": 0}` means on and having classified nothing.
   Confusing them produces exactly the wrong diagnosis. Check `module_flags`
   before reading any counter as a failure.
2. **`agents[].state` is the truth, not `last_event_at`.** The platform already
   applies a 30-minute staleness cut so an abandoned run does not report as
   working. Read `state`; do not recompute it from the timestamp.
3. **Counters are cached for 60 seconds.** If the user just deployed,
   re-polling every few seconds tells them nothing new. Wait, and say that is
   what you are doing.
