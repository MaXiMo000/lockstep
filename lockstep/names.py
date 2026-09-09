"""PEP 503 name normalization: pip, PyPI, and importlib.metadata all agree
that "Flask-Login", "flask_login", and "FLASK.LOGIN" name the same
distribution. Comparing a lockfile's spelling against the installed
environment's spelling without this would report real matches as drift
purely from formatting, which is worse than missing a real one -- it
teaches whoever runs this to stop trusting the output.
"""
from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[-_.]+")


def normalize(name: str) -> str:
    return _SEPARATORS.sub("-", name).strip().lower()
