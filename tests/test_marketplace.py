"""Contracts for the Claude Code marketplace manifest."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json"
REPOSITORY_URL = "https://github.com/Avocado-Blockchain-Services/abs-agents-skills.git"

# The object forms of a plugin `source` that `claude plugin validate` accepts.
# Verified against Claude Code 2.1.285 through 2.1.290 by validating one
# manifest per type: these four pass; "git" and an invented type both fail.
ACCEPTED_SOURCE_TYPES = {"github", "url", "git-subdir", "npm"}


def load_plugins() -> dict[str, dict]:
    with MARKETPLACE.open(encoding="utf-8") as manifest:
        return {plugin["name"]: plugin for plugin in json.load(manifest)["plugins"]}


class MarketplaceManifestContractTests(unittest.TestCase):
    def test_every_plugin_source_is_a_type_claude_code_accepts(self) -> None:
        """A source type Claude Code does not know makes the plugin uninstallable.

        `"source": "git"` reads like the obvious spelling for a plain git
        repository, and it is not one: the type for a git URL is `"url"`. Claude
        Code rejects the unknown type at install with "this plugin uses a source
        type your Claude Code version does not support. Update Claude Code and
        try again" -- which sends the reader to upgrade a client that is already
        current, while the manifest is what needs changing. `marketplace add`
        still succeeds, so nothing fails until someone installs that one plugin.

        The dev channel shipped with `"git"` from 0.3.0 and was restored to it in
        2848779 when `git-subdir` turned out to install an empty plugin.
        """
        for name, plugin in load_plugins().items():
            source = plugin["source"]
            if isinstance(source, str):
                self.assertTrue(
                    source.startswith("./"),
                    f"{name}: a string source must be a path relative to the marketplace",
                )
                continue
            self.assertIn(source.get("source"), ACCEPTED_SOURCE_TYPES, name)

    def test_the_dev_channel_serves_the_development_branch_of_this_repository(self) -> None:
        """The dev plugin is this repository at `development`, whole.

        Not `git-subdir`: that type sparse-checks-out one folder, and with the
        plugin at the repository root there is no folder to name -- `path: "."`
        fetched the root files and dropped `.claude-plugin/` and `skills/`.
        """
        source = load_plugins()["perseaai-agents-dev"]["source"]

        self.assertEqual(
            source,
            {"source": "url", "url": REPOSITORY_URL, "ref": "development"},
        )

    @unittest.skipUnless(shutil.which("claude"), "the Claude Code CLI is not installed")
    def test_claude_code_itself_accepts_the_manifest(self) -> None:
        """Ask the real validator, where it is available.

        The allow-list above is a record of what one range of versions accepted.
        The CLI is the authority, and it is the check that would have caught
        this before a release.
        """
        result = subprocess.run(
            ["claude", "plugin", "validate", str(MARKETPLACE)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
