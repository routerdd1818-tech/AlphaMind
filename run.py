"""
AlphaMind AI — One-Click Project Entry Point
Usage:
    python alphamind/run.py
    or:
    cd alphamind && python run.py
"""

import os
import sys
import webbrowser

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

# Add paths to sys.path
for p in [CURRENT_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from alphamind.web.server import start_server

if __name__ == "__main__":
    print("=" * 60)
    print("  AlphaMind AI — 智慧選股與供應鏈資金動能分析平台")
    print("  Web Dashboard: http://localhost:8888")
    print("=" * 60)
    start_server()
