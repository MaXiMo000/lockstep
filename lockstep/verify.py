"""Are the files on disk still the ones each package installed?

Every wheel install writes a RECORD: every file it put down, with its
sha256 and size. pip writes it and never looks at it again. So a file in
site-packages that was hand-patched on a live server, "fixed" by a
debugging session and left that way, or tampered with after install
reads as the same package version to pip, to `pip freeze`, and to
`lockstep check` -- the version string didn't change, the code did.

This re-hashes every installed file against its own RECORD entry:

    modified  -- the file's bytes no longer match the recorded sha256
    missing   -- RECORD lists it, it's gone from disk

Files RECORD lists without a hash (RECORD itself, and anything an
installer generated after the fact) can't be checked and are skipped --
reported as a count, never silently treated as verified.
"""
from __future__ import annotations

import base64
import csv
import hashlib
from importlib import metadata

from .names import normalize


def _digest(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode()


def _record_rows(dist: metadata.Distribution) -> list[tuple[str, str]] | None:
    """(path, hash) for every RECORD line, read directly. Not
    `dist.files`: since Python 3.12 that silently drops entries whose file
    no longer exists -- exactly the deleted files this has to report."""
    text = dist.read_text("RECORD")
    if text is None:
        return None
    return [(row[0], row[1] if len(row) > 1 else "") for row in csv.reader(text.splitlines()) if row]


def verify_distribution(dist: metadata.Distribution) -> dict:
    name = normalize(dist.metadata.get("Name") or "?")
    rows = _record_rows(dist)
    result = {"name": name, "version": dist.version, "checked": 0, "unhashed": 0,
              "modified": [], "missing": [], "no_record": rows is None}
    for rel, hash_field in rows or ():
        algo, _, expected = hash_field.partition("=")
        if algo != "sha256" or not expected:
            # No hash (RECORD itself, installer-generated files) or an
            # algorithm nothing real uses: can't check, so counted, not passed.
            result["unhashed"] += 1
            continue
        try:
            actual = _digest(dist.locate_file(rel))
        except FileNotFoundError:
            result["missing"].append(rel)
            continue
        except OSError:
            result["unhashed"] += 1
            continue
        result["checked"] += 1
        if actual != expected:
            result["modified"].append(rel)
    result["modified"].sort()
    result["missing"].sort()
    return result


def verify_installed(only: set[str] | None = None) -> list[dict]:
    """One result per installed distribution (or only the named ones)."""
    results = []
    for dist in metadata.distributions():
        name = normalize(dist.metadata.get("Name") or "")
        if not name or (only and name not in only):
            continue
        results.append(verify_distribution(dist))
    return sorted(results, key=lambda r: r["name"])
