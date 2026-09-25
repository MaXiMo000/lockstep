"""Compare a lockfile's pinned versions against what's actually installed.

Three distinct kinds of drift, not one blended "different" bucket, because
each implies a different fix: a version_mismatch means re-pin or
reinstall; missing means something never got installed; extra means an
undeclared package is present -- the case this tool exists for, the patch
someone installed by hand on a live server that never made it back into
the lockfile.
"""
from __future__ import annotations

from packaging.version import InvalidVersion, Version

MATCHED, VERSION_MISMATCH, MISSING, EXTRA = "matched", "version_mismatch", "missing", "extra"

# `pip freeze` leaves these out unless given --all, so a lockfile made with
# it never lists them and every environment would report them as `extra`.
# They're still checked normally when a lockfile does pin them.
FREEZE_OMITS = {"pip", "setuptools", "wheel", "distribute"}


def same_version(locked: str, installed: str, arbitrary: bool = False) -> bool:
    """PEP 440 equality: "1.0" == "1.0.0", "1.0RC1" == "1.0rc1". A `===` pin
    means exact string equality by definition, and a version PEP 440 can't
    parse falls back to that too."""
    if arbitrary:
        return locked == installed
    try:
        return Version(locked) == Version(installed)
    except InvalidVersion:
        return locked == installed


def check_drift(lockfile: dict, installed: dict[str, str]) -> list[dict]:
    pinned = lockfile["pinned"]
    arbitrary = set(lockfile.get("arbitrary", ()))
    results = []

    for name in sorted(pinned):
        locked_version = pinned[name]
        actual_version = installed.get(name)
        if actual_version is None:
            results.append({
                "name": name, "status": MISSING,
                "locked_version": locked_version, "installed_version": None,
                "detail": f"'{name}' is pinned to {locked_version} but is not installed",
            })
        elif not same_version(locked_version, actual_version, name in arbitrary):
            results.append({
                "name": name, "status": VERSION_MISMATCH,
                "locked_version": locked_version, "installed_version": actual_version,
                "detail": (f"'{name}' is pinned to {locked_version} but "
                           f"{actual_version} is installed"),
            })
        else:
            results.append({
                "name": name, "status": MATCHED,
                "locked_version": locked_version, "installed_version": actual_version,
                "detail": f"'{name}' matches its locked version {locked_version}",
            })

    declared = set(pinned) | set(lockfile.get("unpinned", ()))
    for name in sorted(installed):
        if name not in declared and name not in FREEZE_OMITS:
            results.append({
                "name": name, "status": EXTRA,
                "locked_version": None, "installed_version": installed[name],
                "detail": (f"'{name}' {installed[name]} is installed but not declared "
                           "anywhere in the lockfile"),
            })

    return results
