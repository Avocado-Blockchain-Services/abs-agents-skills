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
        """Claude Code accepts only `callbackPort` inside `oauth`.

        A `clientId` or `scopes` key there makes it drop the whole server entry
        at parse time -- silently. The plugin still loads and its skills appear,
        but the MCP server is absent from `/mcp` entirely: not "needs
        authentication", not an error, just missing. Verified by removing the
        two keys from an installed build, after which the server registered.

        It is not needed either: the resource metadata points at an Auth0 that
        advertises `registration_endpoint` (/oidc/register), so Claude Code
        performs dynamic client registration and discovers the scopes itself.

        Codex is the opposite and keeps both keys -- see the test below. The two
        hosts read different files (`.mcp.json` vs `.codex-plugin/mcp.json`), so
        neither contract constrains the other.
        """
        server = load_json(".mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "oauth": {
                    "callbackPort": 29352,
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

    def test_plugin_manifests_reference_the_expected_mcp_configs_at_version_051(self) -> None:
        # The version is the plugin cache key: Claude Code stores an installed
        # build under `cache/<marketplace>/<plugin>/<version>/` and reuses it
        # rather than re-copying. Shipping a config fix without bumping this
        # leaves every existing install on the old build, which is how the
        # broken 0.5.0 kept coming back after the source was already correct.
        claude_manifest = load_json(".claude-plugin/plugin.json")
        codex_manifest = load_json(".codex-plugin/plugin.json")

        self.assertEqual(claude_manifest["version"], "0.5.1")
        self.assertEqual(codex_manifest["version"], "0.5.1")
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-plugin/mcp.json")


if __name__ == "__main__":
    unittest.main()
