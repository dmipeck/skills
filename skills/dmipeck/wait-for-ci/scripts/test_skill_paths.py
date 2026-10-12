#!/usr/bin/env python3
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
ROOT_HINT = "directory containing this SKILL.md"

FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
COMMAND = re.compile(r"^python\s+(\S+)", re.MULTILINE)

EXPECTED = (
    "scripts/wait_github.py",
    "scripts/wait_gitlab.py",
    "scripts/wait_gitea.py",
)


def bash_scripts(text: str) -> list[str]:
    fences = FENCE.findall(text)
    if len(fences) != 1:
        raise AssertionError(f"expected one bash fence, found {len(fences)}")
    return COMMAND.findall(fences[0])


def names_skill_root(text: str) -> bool:
    flat = " ".join(text.replace("`", "").split())
    return ROOT_HINT in flat


def resolve(script: str, skill_dir: Path, cwd: Path, text: str) -> Path:
    if "<" in script or not names_skill_root(text):
        return cwd / script
    return skill_dir / script


class SkillScriptPathTests(unittest.TestCase):
    def test_bash_scripts_resolve_from_skill_root(self) -> None:
        text = SKILL_MD.read_text()
        scripts = bash_scripts(text)
        self.assertEqual(scripts, list(EXPECTED))
        self.assertNotIn("<this-skill>", text)
        with tempfile.TemporaryDirectory() as raw:
            cwd = Path(raw)
            for script in scripts:
                resolved = resolve(script, SKILL_DIR, cwd, text)
                self.assertTrue(resolved.is_file(), resolved)
                self.assertEqual(resolved.parent, SKILL_DIR / "scripts")
                self.assertFalse((cwd / script).exists())
