# Laravel Local Onboarding Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evaluate the unpublished native-logger onboarding skill against a real open-source Laravel application through a local Persea MCP/API environment.

**Architecture:** Use the Laravel application's existing Monolog-backed logger as the sole integration boundary. Run the MCP/API and its local dependencies separately, register a disposable local project/service, validate the emitted HTTP payload and only run a real E2E probe after explicitly recording and restoring module flags.

**Tech Stack:** Laravel/PHP, Monolog, Python/FastAPI MCP server, PostgreSQL, Redis, Docker Compose, PHPUnit/Pest where available.

---

### Task 1: Establish an isolated test fixture

**Files:**
- Create: a disposable clone under `/private/tmp`
- Modify: only the disposable clone's logging configuration and test fixture
- Test: native Laravel log emission

**Step 1:** Clone a public Laravel repository into a temporary directory.

**Step 2:** Confirm the project uses Laravel's existing `Log` facade and Monolog channels.

**Step 3:** Record its original logging configuration and select the least-invasive channel extension.

### Task 2: Run the local platform prerequisites

**Files:**
- Modify: no tracked API files
- Test: Lite and Full MCP tool registration plus API health

**Step 1:** Start the API, PostgreSQL, and Redis from the API repository's Docker Compose configuration.

**Step 2:** Apply database migrations and verify the local MCP endpoints expose `set_project_agent_modules`.

**Step 3:** Use a disposable authenticated local identity/project only; do not target a shared remote project.

### Task 3: Execute onboarding through the native logger

**Files:**
- Modify: only the disposable Laravel clone
- Test: emitted JSON payload and Laravel regression test

**Step 1:** Register a disposable `EXTERNAL_BACKEND` service and obtain the local service configuration.

**Step 2:** Add a Monolog handler to the existing Laravel channel without replacing channels, formatters, or call sites.

**Step 3:** Emit an existing-style `Log::error()` event and assert stdout/file behavior remains and the adapter receives an ERROR payload.

**Step 4:** Validate the exact captured payload through `validate_setup`; include exception and message-only cases.

### Task 4: Exercise the controlled E2E path and clean up

**Files:**
- Modify: no tracked project files outside the disposable clone
- Test: state restoration on success and failure

**Step 1:** Record classifier/debugger flags, disable both via the local MCP, and run the agreed E2E probe.

**Step 2:** Restore exactly the recorded flags in a finally-style cleanup path.

**Step 3:** Stop local containers and report any onboarding ambiguity, failed invariant, or missing cross-service capability before publishing the skill.
