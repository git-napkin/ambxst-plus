"""Discover skills as direct <name>/SKILL.md children of a root."""

from __future__ import annotations

from pathlib import Path

from .registry import Tool
from .friendly import labels, tick


def discover_skills(skill_dirs):
    catalog = {}
    for root in skill_dirs or []:
        directory = Path(root).expanduser()
        if not directory.is_dir():
            continue
        try:
            children = list(directory.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                catalog[child.name] = {
                    "name": child.name,
                    "path": str(skill_md),
                    "content": skill_md.read_text(encoding="utf-8"),
                }
            except OSError:
                continue
    return catalog


def skill_catalog_names(skill_dirs):
    return sorted(discover_skills(skill_dirs).keys())


class ReadSkillTool(Tool):
    name = "read_skill"
    user_friendly_name = "Read skill"
    schema = {
        "description": "Load a skill's SKILL.md by name from the skill catalog.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    }

    def should_autoexecute(self, ctx, args):
        return True

    def execute(self, ctx, args):
        name = (args or {}).get("skill") or (args or {}).get("name") or ""
        catalog = discover_skills(ctx.skill_dirs)
        if name not in catalog:
            return {
                "status": "error",
                "error": "Unknown skill: %s" % name,
                "available": sorted(catalog.keys()),
            }
        entry = catalog[name]
        return {
            "status": "ok",
            "name": entry["name"],
            "path": entry["path"],
            "content": entry["content"],
        }

    def user_friendly_name_for(self, args):
        name = (args or {}).get("skill") or (args or {}).get("name") or ""
        label = tick(name)
        if label:
            return labels(
                "Reading skill %s" % label,
                "Read skill %s" % label,
                ask="Read skill %s" % label,
            )
        return labels("Reading skill", "Read skill", ask="Read skill")
