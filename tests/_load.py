"""Load a skill script from .claude/skills (the folder names have hyphens)."""

import importlib.util
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, ".claude", "skills")


def load(folder, name):
    path = os.path.join(SKILLS, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("trader_" + name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
