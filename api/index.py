"""
AlphaMind AI — Vercel `/api` Serverless Function Entrypoint (`api/index.py`).
"""

from http.server import BaseHTTPRequestHandler
import importlib.machinery
import os
import sys
import types

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(PACKAGE_ROOT, ".."))

for _p in (PACKAGE_ROOT, WORKSPACE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "alphamind" not in sys.modules:
    _pkg = types.ModuleType("alphamind")
    _pkg.__path__ = [PACKAGE_ROOT]
    _pkg.__package__ = "alphamind"
    _spec = importlib.machinery.ModuleSpec("alphamind", None, is_package=True)
    _spec.submodule_search_locations = [PACKAGE_ROOT]
    _pkg.__spec__ = _spec
    sys.modules["alphamind"] = _pkg

from alphamind.web.server import AlphaMindApiHandler, wsgi_app


class handler(AlphaMindApiHandler, BaseHTTPRequestHandler):
    """Vercel Python Serverless BaseHTTPRequestHandler entrypoint."""
    pass


def app(environ, start_response):
    """Vercel Python Runtime WSGI entrypoint."""
    return wsgi_app(environ, start_response)


application = app
