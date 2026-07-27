"""Locating the one declaration of the API surface.

The registry is `spec/registries/api.json` at the repo root — the same file the
Worker routes from and the TypeScript SDK builds its methods from. It is copied
into the package at build time for distribution; in a checkout it is read from
the repo so that editing the registry immediately changes the client, with no
build step in between to forget to run.
"""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_CANDIDATES = (
    _HERE / "api.json",                                  # packaged
    _HERE.parent.parent / "spec" / "registries" / "api.json",  # checkout
)


def load_registry() -> dict:
    for path in _CANDIDATES:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise RuntimeError(
        "packauth: could not find api.json. Looked in: "
        + ", ".join(str(p) for p in _CANDIDATES)
    )
