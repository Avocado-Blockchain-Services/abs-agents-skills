#!/usr/bin/env python3
"""Validate SKILL.md files against the agentskills.io frontmatter contract."""
import re
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "metadata"}

def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)

def main(path):
    p = Path(path)
    text = p.read_text()
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        fail("no frontmatter block delimited by --- at start of file")
    try:
        import yaml
        fm = yaml.safe_load(m.group(1))
    except ImportError:
        fail("pyyaml not installed (pip install pyyaml)")
    if not isinstance(fm, dict):
        fail("frontmatter is not a mapping")
    extra = set(fm) - ALLOWED_KEYS
    if extra:
        fail(f"non-spec top-level keys: {extra}")
    name = fm.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        fail(f"invalid name: {name!r}")
    if name != p.parent.name:
        fail(f"name {name!r} != directory {p.parent.name!r}")
    desc = fm.get("description", "")
    if not (1 <= len(desc) <= 1024):
        fail(f"description length {len(desc)} outside 1..1024")
    body = text[m.end():]
    if "mcp__" in body:
        fail("body references prefixed tool names; use bare names")
    print(f"OK: {path}")

if __name__ == "__main__":
    main(sys.argv[1])
