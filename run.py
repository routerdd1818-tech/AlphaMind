"""
AlphaMind AI — One-Click Project Entry Point
Usage:
    python alphamind/run.py
    or:
    cd alphamind && python run.py
"""

import importlib.machinery
import os
import sys
import types

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

# Add paths to sys.path
for p in [CURRENT_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

if "alphamind" not in sys.modules:
    _pkg = types.ModuleType("alphamind")
    _pkg.__path__ = [CURRENT_DIR]
    _pkg.__package__ = "alphamind"
    _spec = importlib.machinery.ModuleSpec("alphamind", None, is_package=True)
    _spec.submodule_search_locations = [CURRENT_DIR]
    _pkg.__spec__ = _spec
    sys.modules["alphamind"] = _pkg

from alphamind.web.server import PORT, start_server

if __name__ == "__main__":
    print("=" * 60)
    print("  AlphaMind AI — 智慧選股與供應鏈資金動能分析平台")
    print(f"  Web Dashboard & API: http://0.0.0.0:{PORT}")
    print("=" * 60)
    start_server()
