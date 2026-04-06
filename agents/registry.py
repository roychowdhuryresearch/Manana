"""Auto-discovery registry — finds all BaseAgent subclasses in agents/."""

from __future__ import annotations
import importlib
import pkgutil
import os

from agents.base import BaseAgent


def _discover_agents() -> dict[str, type[BaseAgent]]:
    """Scan agents/ for all BaseAgent subclasses, return {name: class}."""
    agents_dir = os.path.dirname(os.path.abspath(__file__))
    result = {}

    for module_info in pkgutil.iter_modules([agents_dir]):
        if module_info.name in ("base", "registry", "orchestrator", "catalog"):
            continue
        module = importlib.import_module(f"agents.{module_info.name}")
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseAgent)
                and obj is not BaseAgent
                and obj.name  # skip if name not set
            ):
                result[obj.name] = obj

    return result


# Built once at import time
ALL_AGENTS = _discover_agents()

PHASE1_AGENTS = {name: cls for name, cls in ALL_AGENTS.items() if cls.phase == 1}
PHASE2_AGENTS = {name: cls for name, cls in ALL_AGENTS.items() if cls.phase == 2}
PHASE3_AGENTS = {name: cls for name, cls in ALL_AGENTS.items() if cls.phase == 3}
