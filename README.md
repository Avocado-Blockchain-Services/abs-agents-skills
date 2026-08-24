# abs-agents-skills

Agent skills for the **Persea AI agents platform** by Avocado Blockchain
Services. Ships the `perseaai-agents-setup` skill, which teaches AI coding
agents (Claude Code, Codex, opencode, Cursor, …) how to onboard a project onto
the platform: connect GitHub, register the repo as a service, integrate
logcore structured logging, and open the integration PR.

> ⚠️ **Early stage.** The MCP endpoints below point at pre-production
> environments; URLs will move to a stable domain before general availability.

## Channels

| Channel | Plugin | Branch | MCP endpoint |
|---|---|---|---|
| **Stable** | `perseaai-agents` | `main` | staging API (`agents-api-…`) |
| **Dev** | `perseaai-agents-dev` | `development` | dev API (`agents-api-dev-…`) |

Both channels are served by this same marketplace. Install **one per
workspace** — they ship the same skill and would double-trigger side by side.
Skill changes land on `development` first, get dogfooded by the team against
the dev API, and are promoted to `main` with a version bump.

**Promoting `development` → `main`:** merge, but keep the channel-owned files
out of the merge — `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` (name/version), `.agents/plugins/marketplace.json`
(Codex channel), and `.mcp.json` (endpoint) belong to each branch:

```
git switch main && git merge --no-ff --no-commit development
git checkout main -- .claude-plugin/ .codex-plugin/ .agents/plugins/ .mcp.json
# bump the same version in both plugin manifests, then commit
```

**Testing an unmerged PR branch** needs no channel at all — a marketplace can
be a local checkout:

```
/plugin marketplace add /path/to/your/abs-agents-skills   # on the PR branch
/plugin install perseaai-agents-dev@abs-agents-skills
```

## Install

### Claude Code (recommended — one step gets tools + skill)

```
/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
/plugin install perseaai-agents@abs-agents-skills
```

(Team members testing pre-release content: `/plugin install
perseaai-agents-dev@abs-agents-skills` instead.)

This also configures the platform MCP server (key `perseaai-agents`) via the
bundled `.mcp.json`; an OAuth browser window will open on first use.

### Codex (native plugin: tools + skill)

```sh
codex plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
codex plugin add perseaai-agents@abs-agents-skills
```

Start a new Codex session in the repository after installation so it loads the
bundled MCP server and onboarding skill.

### Any other agent (opencode, Cursor, …)

Install the skill:

```
npx skills add Avocado-Blockchain-Services/abs-agents-skills
```

Useful flags: `--agent opencode` to target one agent, `-g` for user-level
instead of project-level scope, `--copy` to copy files instead of symlinking.

Then connect the MCP server manually (streamable HTTP + OAuth):

- **URL (stable / staging API):**
  `https://agents-api-352942961463.us-east4.run.app/mcp/lite/mcp`
- **URL (dev channel):**
  `https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp`
- **opencode** — add to `opencode.json`:

  ```json
  {
    "mcp": {
      "perseaai-agents": {
        "type": "remote",
        "url": "https://agents-api-352942961463.us-east4.run.app/mcp/lite/mcp"
      }
    }
  }
  ```

- **Cursor** — register a remote (streamable HTTP) MCP server named
  `perseaai-agents` with the URL above, using Cursor's MCP settings.

### Zero-install fallback

Connect the MCP URL above directly in any MCP client — the server itself
exposes a `logcore_setup` prompt covering the same onboarding flow.

## Usage

With the MCP connected and the skill installed, just ask your agent:

> "Connect this repo to the Persea agents platform"

The `perseaai-agents-setup` skill triggers automatically and walks through
GitHub connection → project registration → logging integration → validation
→ PR.

The GitHub connection is organization-scoped and uses one browser interaction:

1. The agent lists the Persea organizations and asks which one to configure.
2. It calls `check_github_connection(organization_id)`.
3. If needed, it calls `get_github_connect_url(organization_id)` and opens the
   single returned `connect_url`.
4. It polls the same organization until the API confirms the installation.

The connection URL combines GitHub App installation and user authorization.
There are no separate authorization and installation URLs, and closing the
browser window is not treated as success.

### GitHub MCP tools

| Tool | Contract |
|---|---|
| `list_organizations()` | Select the Persea organization before connecting GitHub. |
| `check_github_connection(organization_id)` | Report whether that organization has a verified GitHub App installation. |
| `get_github_connect_url(organization_id)` | Return one `connect_url` for an organization owner to open. |

Una vez integrado el proyecto, para saber si está funcionando:

> "¿Está llegando algo a la plataforma desde este repo?"
> "¿Cómo va mi proyecto?"

La skill `perseaai-agents-status` se dispara sola: diagnostica el pipeline
cuando todavía no hay datos, y reporta logs, veredictos del classifier, runs
del debugger y PRs esperando review cuando sí los hay.

## Repository layout

- `skills/perseaai-agents-setup/SKILL.md` — the onboarding skill
  ([agentskills.io](https://agentskills.io) format)
- `skills/perseaai-agents-status/SKILL.md` — la skill de monitoreo post-setup
- `.claude-plugin/` — Claude Code plugin + self-hosted marketplace manifests
- `.codex-plugin/` — Codex plugin manifest
- `.agents/plugins/marketplace.json` — native Codex marketplace catalog
- `.mcp.json` — bundled MCP connection for Claude Code and Codex plugin installs
- `docs/superpowers/` — design spec and implementation plan

## License

Apache-2.0
