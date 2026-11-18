"""npm: package-lock.json (lockfile v2/v3, npm 7+) against node_modules.

npm can install the same package at several versions, one per place in the
tree, so packages are compared by install path ("node_modules/a/node_modules/b"),
not by name. "Installed" is read from each package's own package.json on
disk, not from node_modules/.package-lock.json: that hidden file is npm's
record of what it did, and a hand-edited or partially copied node_modules
is exactly what it would miss.
"""
from __future__ import annotations

import json
import os
import pathlib

LOCKFILE_NAMES = {"package-lock.json", "npm-shrinkwrap.json"}


class NpmLockError(ValueError):
    pass


def parse_package_lock(text: str, include_dev: bool = False) -> dict:
    """The lockstep lockfile shape, keyed by install path.

    Dev packages are left out unless asked for, as `npm ci --omit=dev`
    leaves them out of a deployed tree; they still count as declared, so a
    dev machine doesn't report them as extra. Optional packages (often
    platform-specific binaries) are checked when present and never
    reported missing. Workspace links are declared without a version.
    """
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NpmLockError(f"not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("packages"), dict):
        version = doc.get("lockfileVersion") if isinstance(doc, dict) else None
        raise NpmLockError(
            f"lockfileVersion {version} has no 'packages' map; regenerate it with npm 7 "
            "or newer: npm install --package-lock-only")

    pinned, unpinned, optional, workspaces = {}, [], [], []
    for path, entry in doc["packages"].items():
        if not path or not isinstance(entry, dict):
            continue  # "" is the project itself
        if "node_modules/" not in path:
            workspaces.append(path)  # a workspace folder; its own node_modules is walked too
            continue
        dev = entry.get("dev") and not include_dev
        if dev or entry.get("link") or not entry.get("version"):
            unpinned.append(path)
            continue
        pinned[path] = entry["version"]
        if entry.get("optional") or entry.get("devOptional"):
            optional.append(path)
    return {"pinned": pinned, "unpinned": unpinned, "optional": optional,
            "arbitrary": list(pinned), "ecosystem": "npm", "workspaces": workspaces}


def _is_junction(path: pathlib.Path) -> bool:
    # npm links with directory junctions on Windows; is_symlink() is False for those.
    return getattr(path, "is_junction", lambda: False)()


def installed_node_modules(root: str | os.PathLike, workspaces=()) -> dict[str, str]:
    """{install path: version} for every package under root's node_modules
    and each workspace's, read from its package.json. Symlinked packages
    (workspace links, `npm link`) are recorded but not walked into."""
    root = pathlib.Path(root)
    found: dict[str, str] = {}

    def record(pkg_dir: pathlib.Path) -> None:
        try:
            version = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError, AttributeError):
            return  # not a package: a stray folder npm didn't put there
        found[pkg_dir.relative_to(root).as_posix()] = str(version or "")
        if not (pkg_dir.is_symlink() or _is_junction(pkg_dir)):
            walk(pkg_dir / "node_modules")

    def walk(node_modules: pathlib.Path) -> None:
        try:
            entries = sorted(os.scandir(node_modules), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue  # .bin, .package-lock.json, .cache
            path = pathlib.Path(entry.path)
            if entry.name.startswith("@") and entry.is_dir() and not (entry.is_symlink() or _is_junction(path)):
                for scoped in sorted(os.scandir(path), key=lambda e: e.name):
                    record(pathlib.Path(scoped.path))
            else:
                record(path)

    walk(root / "node_modules")
    for workspace in workspaces:
        walk(root / workspace / "node_modules")
    return found
