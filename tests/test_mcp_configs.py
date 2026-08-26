"""Host-specific OAuth configuration contracts for the development MCP."""

import json
from pathlib import Path
import unittest


MCP_NAME = "perseaai-agents-dev"
MCP_URL = "https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp"
CLIENT_ID = "OwSOkAnm6fyS7igs8nKQI2btOo5IRm9X"
SCOPES = ["openid", "profile", "email", "offline_access"]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    with (REPOSITORY_ROOT / relative_path).open(encoding="utf-8") as config_file:
        return json.load(config_file)


class McpConfigurationContractTests(unittest.TestCase):
    def test_readme_documents_the_development_codex_marketplace_command(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "codex plugin marketplace add "
            "Avocado-Blockchain-Services/abs-agents-skills --ref development",
            readme,
        )

    def test_claude_root_config_uses_its_host_specific_oauth_contract(self) -> None:
        """Claude Code's `oauth` block carries the static client id and string scopes.

        The Auth0 development tenant has dynamic client registration disabled
        (its metadata still advertises /oidc/register -- advertising is not
        enablement), so Claude Code must be handed the shared public client id
        via `oauth.clientId`, the documented "pre-configured OAuth credentials"
        path. No secret: it is a public PKCE client.

        `oauth.scopes` must be a SINGLE SPACE-SEPARATED STRING (RFC 6749 §3.3).
        An array here fails Claude Code's config schema and the whole server
        entry is dropped at parse time -- silently: absent from `/mcp`, not
        "needs authentication", no error. That array is how 0.5.0 shipped
        broken, and misreading the drop as "clientId is unsupported" is how
        0.5.1 removed the client id and stranded Claude Code on the rejected
        DCR path. Verified against Claude Code 2.1.246: array scopes -> entry
        dropped; string scopes + clientId -> accepted ("client_id configured").

        Scopes are pinned explicitly because Claude Code (v2.1.196+) no longer
        requests the discovered `scopes_supported` catalog and the dev
        protected-resource metadata advertises no scopes; unpinned, the
        authorize request would carry no scope and yield no refresh token.

        Codex reads a different file with its own schema (top-level scopes
        array) -- see the test below; neither contract constrains the other.
        """
        server = load_json(".mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "oauth": {
                    "clientId": CLIENT_ID,
                    "callbackPort": 29352,
                    "scopes": " ".join(SCOPES),
                },
            },
        )

    def test_codex_config_uses_its_host_specific_oauth_contract(self) -> None:
        config_path = REPOSITORY_ROOT / ".codex-plugin/mcp.json"
        self.assertTrue(config_path.is_file(), "Codex-specific MCP configuration is missing")
        if not config_path.is_file():
            return

        server = load_json(".codex-plugin/mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "scopes": SCOPES,
                "oauth": {
                    "clientId": CLIENT_ID,
                    "callbackPort": 29352,
                },
            },
        )

    def test_plugin_manifests_reference_the_expected_mcp_configs_at_version_052(self) -> None:
        # The version is the plugin cache key: Claude Code stores an installed
        # build under `cache/<marketplace>/<plugin>/<version>/` and reuses it
        # rather than re-copying. Shipping a config fix without bumping this
        # leaves every existing install on the old build, which is how the
        # broken 0.5.0 kept coming back after the source was already correct.
        claude_manifest = load_json(".claude-plugin/plugin.json")
        codex_manifest = load_json(".codex-plugin/plugin.json")

        self.assertEqual(claude_manifest["version"], "0.5.2")
        self.assertEqual(codex_manifest["version"], "0.5.2")
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-plugin/mcp.json")


if __name__ == "__main__":
    unittest.main()
