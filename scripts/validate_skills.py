"""Validate SKILL.md files for the public repository surface."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ALLOWED_FRONTMATTER = {"name", "description"}
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter must be a mapping")
    return loaded


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = _frontmatter(path)
    except ValueError as exc:
        return [f"{path}: {exc}"]

    extra = set(data) - ALLOWED_FRONTMATTER
    missing = ALLOWED_FRONTMATTER - set(data)
    if extra:
        errors.append(f"{path}: unexpected frontmatter keys: {', '.join(sorted(extra))}")
    if missing:
        errors.append(f"{path}: missing frontmatter keys: {', '.join(sorted(missing))}")

    name = data.get("name")
    if not isinstance(name, str) or not SKILL_NAME_RE.fullmatch(name):
        errors.append(f"{path}: name must be lower hyphen-case")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{path}: description must be a non-empty string")
    elif len(description) > 1024:
        errors.append(f"{path}: description exceeds 1024 characters")

    if path.parent.name != name:
        errors.append(f"{path}: parent directory must match skill name '{name}'")

    return errors


def main() -> int:
    skill_files = sorted(Path("skills").glob("*/SKILL.md"))
    if not skill_files:
        print("No skills found.", file=sys.stderr)
        return 1

    errors = [error for path in skill_files for error in validate(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Validated {len(skill_files)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
