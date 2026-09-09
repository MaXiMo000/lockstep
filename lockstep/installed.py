"""What's actually installed in the running Python environment, right now.

Not a second parse of anything -- `importlib.metadata` is the interpreter's
own view of itself, stdlib, no subprocess needed. Run `lockstep check`
*inside* the environment you want to verify (the container, the venv, the
deployed server) so this reflects that environment, not the one lockstep
itself happens to be installed in.
"""
from __future__ import annotations

from importlib import metadata

from .names import normalize


def installed_packages() -> dict[str, str]:
    result: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue  # a distribution with no name in its own metadata -- skip, not a crash
        result[normalize(name)] = dist.version
    return result
