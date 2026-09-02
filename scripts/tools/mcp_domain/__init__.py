"""Auto-discovery: loads all domain modules and merges their TOOLS + HANDLERS."""

import importlib
import pkgutil
import os


def load_all_domains():
    """Discover and load all modules in mcp_domain/, returning merged TOOLS and HANDLERS."""
    all_tools = []
    all_handlers = {}
    package_dir = os.path.dirname(__file__)

    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        if module_name.startswith("_"):
            continue
        mod = importlib.import_module(f"mcp_domain.{module_name}")
        all_tools.extend(mod.TOOLS)
        all_handlers.update(mod.HANDLERS)

    return all_tools, all_handlers
