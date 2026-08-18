#!/usr/bin/env python3
"""Check a SKILL.md's Prerequisites list against the tools its body actually uses.

The Prerequisites block is what tells the agent to stop when the MCP server is
not connected, so it has to name every tool the skill goes on to call. Nothing
enforced that: adding a step that calls a new tool without adding it to the list
leaves the skill instructing a call it never declared, and an agent in a session
with a stale MCP server discovers it mid-run instead of up front. The reverse
drifts too — a tool declared long after the step using it was rewritten away.

Both directions are checked:

  * every ``call `tool``` in the body must appear in Prerequisites
  * every tool named in Prerequisites must be used somewhere in the body

Only the ``call `x``` idiom is matched, deliberately. A looser scan would have
to guess which of the file's many backticked identifiers are tool names, and a
validator that cries wolf is one nobody runs.
"""

import re
import sys
from pathlib import Path

_PREREQUISITES = re.compile(
    r"^## Prerequisites\n(.*?)^## ", re.DOTALL | re.MULTILINE
)
_BACKTICKED = re.compile(r"`([a-z][a-z0-9_]+)`")
_CALL = re.compile(r"[Cc]all `([a-z][a-z0-9_]+)`")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main(path: str) -> None:
    text = Path(path).read_text()

    block = _PREREQUISITES.search(text)
    if not block:
        fail("no '## Prerequisites' section followed by another '## ' heading")
    prerequisites = block.group(1)

    declared = set(_BACKTICKED.findall(prerequisites))
    if not declared:
        fail("the Prerequisites section names no tools")

    body = text[block.end(1) :]
    called = set(_CALL.findall(body))

    undeclared = sorted(called - declared)
    if undeclared:
        fail(
            "the body calls tools the Prerequisites section does not list: "
            + ", ".join(undeclared)
        )

    unused = sorted(tool for tool in declared if tool not in body)
    if unused:
        fail(
            "the Prerequisites section lists tools the body never uses: "
            + ", ".join(unused)
        )

    print(f"OK: {len(declared)} tools declared, all of them used, none undeclared")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: validate_tool_references.py <path/to/SKILL.md>")
        sys.exit(2)
    main(sys.argv[1])
