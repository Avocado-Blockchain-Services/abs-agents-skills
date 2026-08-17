# abs-agents-skills

Agent skills for the **Persea AI agents platform** by Avocado Blockchain
Services. Ships the `perseaai-agents-setup` skill, which teaches AI coding
agents (Claude Code, opencode, Cursor, Codex, …) how to onboard a project onto
the platform: connect GitHub, register the repo as a service, integrate
logcore structured logging, and open the integration PR.

> ⚠️ **Early stage.** The MCP endpoint below points at our dev environment;
> the URL and server naming will change before general availability.

## Install

### Claude Code (recommended — one step gets tools + skill)

```
/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
/plugin install perseaai-agents@abs-agents-skills
```

This also configures the platform MCP server (key `perseaai-agents`) via the
bundled `.mcp.json`; an OAuth browser window will open on first use.

### Any other agent (opencode, Cursor, Codex, …)

Install the skill:

```
npx skills add Avocado-Blockchain-Services/abs-agents-skills
```

Useful flags: `--agent opencode` to target one agent, `-g` for user-level
instead of project-level scope, `--copy` to copy files instead of symlinking.

Then connect the MCP server manually (streamable HTTP + OAuth):

- **URL:** `https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp`
- **opencode** — add to `opencode.json`:

  ```json
  {
    "mcp": {
      "perseaai-agents": {
        "type": "remote",
        "url": "https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp"
      }
    }
  }
  ```

- **Cursor / Codex** — register a remote (streamable HTTP) MCP server named
  `perseaai-agents` with the URL above, using each client's MCP settings.

### Zero-install fallback

Connect the MCP URL above directly in any MCP client — the server itself
exposes a `logcore_setup` prompt covering the same onboarding flow.

## Usage

With the MCP connected and the skill installed, just ask your agent:

> "Connect this repo to the Persea agents platform"

The `perseaai-agents-setup` skill triggers automatically and walks through
GitHub connection → project registration → logging integration → validation
→ PR.

## Repository layout

- `skills/perseaai-agents-setup/SKILL.md` — the onboarding skill
  ([agentskills.io](https://agentskills.io) format)
- `.claude-plugin/` — Claude Code plugin + self-hosted marketplace manifests
- `.mcp.json` — bundled MCP connection for Claude Code plugin installs
- `docs/superpowers/` — design spec and implementation plan

## License

Apache-2.0
