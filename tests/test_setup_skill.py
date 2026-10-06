"""Contracts for what the setup skill tells the agent about teams."""

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SETUP_SKILL = REPOSITORY_ROOT / "skills" / "perseaai-agents-setup" / "SKILL.md"


def skill_text() -> str:
    """The skill as one line of prose, so a wrapped sentence still matches."""
    return " ".join(SETUP_SKILL.read_text(encoding="utf-8").split())


class SetupSkillTeamContractTests(unittest.TestCase):
    def test_the_skill_never_looks_teams_up(self) -> None:
        """A project gets its own team; there is nothing to choose.

        From 0.8.0 the skill called `list_teams` and asked the developer to
        pick when it returned more than one. That was silent while every
        organization had a single team. Since 2026-09-03 the API creates a
        team per project, so the list is longer than one as soon as a
        developer has one project: the skill stopped every onboarding to offer
        teams named after other projects, and steered people into sharing one.
        Members are managed per team, so adding someone to one project then
        applied to the other without anyone asking for it.

        `list_teams` still exists on the server. The contract is that this
        skill has no use for it, not that the tool is gone.
        """
        self.assertFalse(
            "list_teams" in skill_text(),
            "the setup skill names `list_teams` again",
        )

    def test_the_skill_does_not_promise_a_default_team(self) -> None:
        """Omitting `team_id` creates a NEW team; it does not reuse a default.

        "Omitting `team_id` uses the organization's default team" was true
        when it was written and stopped being true on 2026-09-03
        (`ProjectService._resolve_team_id` in persea-agents-api). A skill that
        keeps saying it tells the agent two projects end up together when they
        do not.
        """
        self.assertFalse(
            "organization's default team" in skill_text(),
            "the setup skill promises the organization's default team again",
        )

    def test_create_project_is_called_without_a_team_id(self) -> None:
        """Every sentence that names `team_id` tells the agent to leave it out.

        Checked per sentence rather than once for the whole file, so a later
        step that reintroduces "pass the chosen `team_id`" fails here even
        while the original prohibition is still in place.
        """
        text = skill_text()

        self.assertTrue(
            "Call `create_project` with the selected `organization_id` and "
            "without `team_id`." in text,
            "the `create_project` step no longer says to omit `team_id`",
        )
        self.assertTrue(
            "Never pass `team_id`" in text,
            "the skill no longer forbids passing `team_id`",
        )

        mentions = [
            sentence
            for sentence in re.split(r"(?<=[.:;?!])\s+", text)
            if "`team_id`" in sentence
        ]
        for sentence in mentions:
            self.assertRegex(sentence, r"\b(without|Never pass)\b", sentence)


if __name__ == "__main__":
    unittest.main()
