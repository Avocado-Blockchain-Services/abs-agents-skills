# Native Logger Onboarding Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Persea onboarding attach to a repository's existing logger and preserve its behavior, while keeping the current GCP and HTTP transports and adding consented, reversible E2E validation.

**Architecture:** Phase 3 will become an adapter-first workflow: discover the active logger and its extension point; attach a transport adapter without replacing output, hooks, or call sites; and use a carefully preserved global-output reconfiguration only when no extension point exists. Logcore remains the owner of automatic fingerprints; adapters forward all `ERROR+` events and send parsed stack frames whenever the runtime exposes a real exception or caller stack. Phase 5 will ask before a live probe, pause classifier/debugger only with approval, and restore the exact previous flags in a finally-style flow.

**Tech Stack:** Agent Skills Markdown, Persea MCP tools, existing project logger integrations.

---

### Task 1: Correct the onboarding prerequisites and E2E consent flow

**Files:**
- Modify: `skills/perseaai-agents-setup/SKILL.md`

**Step 1: Declare the new MCP tools**

Add `get_project_status` and `set_project_agent_modules` to prerequisites.

**Step 2: Require explicit approval for the E2E probe**

Explain that a deliberate error can invoke classifier/debugger work. On approval, save flags, pause only classifier/debugger, run the probe, and always restore saved values. On refusal, retain the existing local validation result and report that delivery was not exercised.

### Task 2: Replace logger generation with native logger adaptation

**Files:**
- Modify: `skills/perseaai-agents-setup/SKILL.md`

**Step 1: Add adapter-first discovery**

Require inspection of the logger, its backend, handlers/hooks/middleware, current destinations, formatters and existing redaction before code generation.

**Step 2: Define the integration ladder**

Use an existing extension point first. If none exists, reconfigure global output only as a last resort, preserving destinations, handlers, propagation, levels, formatting and concurrent behavior. Do not modify call sites or install Persea runtime packages.

**Step 3: Define event and stack semantics**

Forward all `ERROR+` events. Preserve dependency frames as `inApp: false`; do not discard events simply because the origin is not confidently application code. Capture parsed stacks whenever an exception or caller stack is available without call-site changes. Do not calculate automatic fingerprints; Logcore owns them, except for an intentional pre-existing/manual project override.

### Task 3: Validate the revised skill

**Files:**
- Test: `scripts/validate_tool_references.py`
- Test: `scripts/validate_skill.py`

**Step 1: Check declared/used MCP tools**

Run: `python3 scripts/validate_tool_references.py skills/perseaai-agents-setup/SKILL.md`

Expected: all declared tools are used and none are undeclared.

**Step 2: Check frontmatter when PyYAML is available**

Run: `python3 scripts/validate_skill.py skills/perseaai-agents-setup/SKILL.md`

Expected: valid agentskills frontmatter; if PyYAML is not installed, report the environment dependency without installing it.

**Step 3: Review the diff**

Run: `git diff --check && git diff -- skills/perseaai-agents-setup/SKILL.md`

Expected: no whitespace errors and no unrelated changes.
