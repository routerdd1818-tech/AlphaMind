"""
AlphaMind AI — Root Entrypoint for Vercel Python Runtime, Render, Railway & Local Execution.
Exports:
- `app` / `application`: Standard WSGI callable
- `handler`: BaseHTTPRequestHandler subclass for Vercel Serverless Python
"""

from http.server import BaseHTTPRequestHandler
import importlib.machinery
import os
import sys
import types

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

for _p in (CURRENT_DIR, PARENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "alphamind" not in sys.modules:
    _pkg = types.ModuleType("alphamind")
    _pkg.__path__ = [CURRENT_DIR]
    _pkg.__package__ = "alphamind"
    _spec = importlib.machinery.ModuleSpec("alphamind", None, is_package=True)
    _spec.submodule_search_locations = [CURRENT_DIR]
    _pkg.__spec__ = _spec
    sys.modules["alphamind"] = _pkg

from alphamind.web.server import AlphaMindApiHandler, start_server, wsgi_app


class handler(AlphaMindApiHandler, BaseHTTPRequestHandler):
    """Vercel Python Serverless BaseHTTPRequestHandler entrypoint."""
    pass


def app(environ, start_response):
    """Vercel Python Runtime / Gunicorn WSGI entrypoint."""
    return wsgi_app(environ, start_response)


application = app


if __name__ == "__main__":
    start_server()
