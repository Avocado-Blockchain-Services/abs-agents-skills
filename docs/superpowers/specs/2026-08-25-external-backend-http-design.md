# HTTP delivery for backends outside GCP — Design Spec

**Date:** 2026-08-25
**Status:** Approved for implementation
**Owner:** Reylan
**Channel:** `development` branch (plugin `perseaai-agents-dev`, MCP `perseaai-agents-dev`)

## Overview

On 2026-08-24 `abs_logs` accepted [ADR-013](https://github.com/Avocado-Blockchain-Services/abs_logs/blob/development/docs/adr/ADR-013-backends-outside-gcp-ship-over-http.md),
*"Backends outside GCP ship errors over HTTP, from the SDK, with nothing installed on the host"*.
A service running on a VPS, Hetzner, DigitalOcean, another cloud or a PaaS has no runtime agent
and no log sink, so until now it never entered the error → issue → classification → auto-fix
pipeline. The edge collector was ruled out — installing binaries on customers' machines defeats
adoption — in favour of the gateway that already existed for the browser: the service posts its
errors to `POST /v1/logs` with a **service-scoped API key**.

Neither this skill nor the MCP covered that case. Both encoded a binary — frontend → `http`,
backend → `stdout` — and the API blocked it outright: a `BACKEND` service was never issued an
`api_key`, so `get_service_config` returned `null` and the gateway would have answered 401.

**The GCP path does not change.** Everything new is additive and inactive by default.

## The problem in one sentence

*"What is this service?"* and *"how do its logs get here?"* stopped having the same answer, and the
whole system was built on the assumption that they did.

## Decisions

### 1. A new `ServiceType` value, not a new column

The first version of this change added a `log_delivery` column (`SINK` | `GATEWAY`) to separate
"where it runs" from "how it delivers". It was dropped after auditing the code: across all of
`src/` there are **five** comparisons against `service_type`, and **every one of them is against
`WEB_APP_FRONTEND`** — none against `BACKEND`. A third value falls into the correct branch of each
on its own. And logcore, which queries the `services` table to resolve its API key, selects
`s.service_type` but discards it: it maps it to no enum of its own, so a new value never reaches it.

The enum already documents itself as *"How a service's logs reach logcore"*. What commit `e5bda30`
purged was the **language** — which forced a Node service to be registered as `PYTHON_BACKEND`, a
false label — not the delivery path. `EXTERNAL_BACKEND` does not reintroduce that problem: it says
exactly what the type always said, and the answer is now ternary rather than binary.

The migration is the same one-liner `b7e4c1a90f22` used to add `BACKEND`:
`ALTER TYPE servicetype ADD VALUE IF NOT EXISTS 'EXTERNAL_BACKEND'`. Nothing is rewritten and every
service keeps its type, and therefore its path.

### 2. Two methods on the enum, so nobody derives it again

`ships_over_gateway()` and `transport()` live on `ServiceType`. The question almost every caller
actually has was spelled `!= WEB_APP_FRONTEND` because the two coincided; they stopped coinciding
the moment a backend could be server-side **and** gateway-delivered. Centralising it keeps every
call site from repeating a derivation that already got it wrong once.

`is_backend()` still means "not a browser" and is still correct for `EXTERNAL_BACKEND` — that is
what keeps everything branching on "server-side or not" intact.

### 3. Ask the developer

Hosting cannot be read from the repository. No file says whether this deploys to Cloud Run or to a
droplet, and guessing fails silently in both directions: a backend outside GCP registered as
`BACKEND` gets no key and can never report. The skill asks, in Phase 2, in those words.

The key follows the delivery path: the four places that forced `api_key = None` for anything but
`WEB_APP_FRONTEND` now call `ships_over_gateway()`. A backend inside GCP still gets no key — the
sink identifies it by `service_id` — and issuing one would hand out a credential nothing consumes.

### 4. Hand-written client, no SDK

The official SDKs (`ablock-logger`, `@ablock/logger`) implement the full transport, but they live in
a private Artifact Registry that requires GCP auth — precisely what a customer outside GCP does not
have. The skill keeps its **no new dependencies** rule and generates the emitter from the contract,
as it already does for any language without a snippet.

What is taken from the SDK is the **behavioural specification**: an `ERROR` severity floor,
20/5s batching, retries with backoff, non-retryable 4xx echoed to stderr, a 1000-entry buffer, a
circuit breaker after 10 failures, flush on exit and on crash, self-exclusion of its own URL, and
the clamps. It is exposed as `transport_info.backend_delivery_rules` so the agent reads it from the
tool rather than from a repository it cannot see.

Environment variables are `LOGCORE_SERVICE`, `LOGCORE_ENV`, `LOGCORE_URL`, `LOGCORE_KEY` and
`LOGCORE_MIN_SEVERITY`: the same prefix the skill already uses on the other two paths
(`<PREFIX>LOGCORE_URL`/`_KEY` on the frontend, `LOGCORE_SERVICE_ID` on the GCP backend), so a
developer with a frontend and a backend does not configure two vocabularies for one service.

Using the normative spec's own names (`ABLOCK_*`, which the SDKs read by themselves) was considered,
so that adopting an SDK later would cost no configuration. It was dropped: `configure()` and
`configureNode()` accept endpoint, key and floor **as arguments**, with the environment only as a
fallback, so the migration costs three lines and does not justify a third prefix. The setup PR
already passes them that way.

No bundler prefix: this is server code, and **the key is a server secret** — unlike the frontend's,
which ships in a bundle by design — so a browser prefix would publish it to every visitor.

### 5. `set_service_type`, because `add_service` is idempotent

`add_service` returns the existing service untouched, so it cannot correct any of the ones already
registered — and all of them are `BACKEND`. The new tool moves a backend between the two hostings
and issues the key if it had none; it never re-issues an existing one, which would silently
invalidate a deployment already sending. Same pattern as `set_build_commands`.

It only exchanges the two backend spellings. Turning a frontend into a backend is not a correction
but a different service, and doing it in place would leave the generated code, the PR and the wire
format describing something else.

## Scope in the API (`persea-agents-api`)

| Area | Change |
|---|---|
| Model | `EXTERNAL_BACKEND` value on `ServiceType` plus `ships_over_gateway()` and `transport()`; a one-line migration, no columns and no schema changes |
| Key issuance | `projects.py` and `project_service.py` decide via `ships_over_gateway()` |
| `get_infra_setup` | Returns `applicable: false` for a gateway-delivered service instead of gcloud commands naming a project the service does not run in |
| `test_connection` | `covers_production_logs` is true for any gateway-delivered service: there, the gateway **is** the production path |
| `get_logging_snippet` | `transport_info.http` stops describing itself as frontend-only and gains `backend_delivery_rules` |
| `get_service_config`, `get_project_status` | Expose `transport`, derived from the type, so the agent does not re-derive it |
| `set_service_type` | New tool |
| `github_pr_service` | The setup PR already generated the SDK's `configure()`, which picks the path from the environment; the file now also declares which variables each hosting needs |

## Non-goals

- Shipping or requiring the SDK.
- The read-back of INFO/WARNING lines around a trace: it does not exist outside GCP, and the ADR
  records that as an accepted consequence (the edge collector is paused, not cancelled).
- Propagating the trace across message queues (Celery, RQ, Kafka, Pub/Sub): a known pending item
  in the ADR.
- A per-service rate limit: database-resolved keys sit at a fixed 20 rps, and bursts beyond it are
  throttled with a retried 429 rather than lost.
