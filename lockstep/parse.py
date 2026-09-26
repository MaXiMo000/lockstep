"""Parse a pinned requirements.txt-style lockfile into
{"pinned": {name: version}, "unpinned": [name, ...], "arbitrary": [name, ...]}.

Only an exact pin (`package==1.2.3`) declares a single version runtime
could drift from -- a range (`package>=1.0`) or a bare name doesn't, so
those are recorded separately as "unpinned" rather than silently ignored
(which would make them read as untracked "extra" packages later) or
treated as a false pinned match.

lockstep assumes a **fully-pinned** lockfile -- the output of `pip freeze`,
`pip-compile`, or `poetry export`, every direct and transitive dependency
pinned -- not a hand-written requirements.txt listing only top-level
packages. See README's "What this assumes" for why: pip installs
transitive dependencies that never appear in a partial file, and every one
of them would otherwise report as "extra" for no reason but the lockfile
being incomplete.
"""
from __future__ import annotations

import re

from packaging.markers import InvalidMarker, Marker

from .names import normalize

# Extras (`requests[security]`) and environment markers (`; python_version
# >= "3.8"`) are both real, common syntax in a real requirements file --
# found by testing this against actual pip-compile output, not synthetic
# "package==1.2.3" lines alone.
_PIN = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)'   # name
    r'(?:\[[^\]]*\])?'                  # optional extras, e.g. [security]
    r'\s*(===|==)\s*'                    # PEP 440 arbitrary-equality (===) tried
    r'([^\s;#]+)'                       # first, or == would eat two of its three '='
)
_RANGE_OP = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:>=|<=|!=|~=|>|<)'
)
_BARE_NAME = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*$')


# The marker environment to judge against; None is the running interpreter.
# Set by `lockstep check --python`, which checks a different one.
MARKER_ENV: dict | None = None


def _applies(marker: str) -> bool:
    """Does a PEP 508 environment marker hold for the running interpreter?
    An unparseable marker counts as applying: better a false "missing"
    than silently not checking a package."""
    if not marker:
        return True
    try:
        return Marker(marker).evaluate(MARKER_ENV)
    except InvalidMarker:
        return True


def parse_lockfile(text: str) -> dict:
    pinned: dict[str, str] = {}
    unpinned: list[str] = []
    arbitrary: list[str] = []  # `===` pins: exact string match, no PEP 440 normalization

    for raw_line in text.splitlines():
        # Environment markers and inline comments both trail after the
        # version; strip the comment first so a marker doesn't hide behind
        # it, then let each pattern's own [^\s;#]+ stop at a marker.
        line = raw_line.split("#", 1)[0].strip().rstrip("\\").strip()
        if not line or line.startswith("-"):
            continue  # blank, or a pip option line (-r other.txt, --index-url ...)
        if ";" in line:
            # A pin for another platform or Python ("colorama==0.4.6 ;
            # sys_platform == 'win32'") isn't expected here, and reporting
            # it as missing would be a false alarm on every other platform.
            line, marker = (part.strip() for part in line.split(";", 1))
            if not _applies(marker):
                continue

        m = _PIN.match(line)
        if m:
            name, op, version = m.groups()
            pinned[normalize(name)] = version
            if op == "===":
                arbitrary.append(normalize(name))
            continue

        m = _RANGE_OP.match(line)
        if m:
            unpinned.append(normalize(m.group(1)))
            continue

        m = _BARE_NAME.match(line)
        if m:
            unpinned.append(normalize(m.group(1)))

    return {"pinned": pinned, "unpinned": unpinned, "arbitrary": arbitrary}


class LockfileError(ValueError):
    pass


_EXPORT_HINT = {
    "poetry.lock": "poetry export -f requirements.txt -o requirements.lock",
}


def parse_file(path, groups=(), extras=()) -> dict:
    """Any supported lockfile, chosen by name: uv.lock, pylock.toml /
    pylock.*.toml (PEP 751), Pipfile.lock, or anything else as
    requirements-style text.

    poetry.lock is refused with the export command to run instead: its
    markers live on dependency edges and its groups differ by version of
    Poetry; its own export resolves both.
    """
    import pathlib

    p = pathlib.Path(path)
    name = p.name.lower()
    if name in _EXPORT_HINT:
        raise LockfileError(f"{p.name} isn't read directly -- export it first: {_EXPORT_HINT[name]}")
    text = p.read_text(encoding="utf-8")
    if name == "uv.lock":
        return _parse_uv_lock(text, groups, extras)
    if name == "pylock.toml" or (name.startswith("pylock.") and name.endswith(".toml")):
        return _parse_pylock(text)
    if name == "pipfile.lock":
        return _parse_pipfile_lock(text)
    return parse_lockfile(text)


def _parse_pylock(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise LockfileError(f"not valid TOML: {exc}") from exc
    pinned, unpinned = {}, []
    for pkg in doc.get("packages", []):
        name = pkg.get("name")
        if not name or not _applies(pkg.get("marker", "")):
            continue
        if pkg.get("version"):
            pinned[normalize(name)] = pkg["version"]
        else:
            unpinned.append(normalize(name))  # a VCS/directory package: no single version
    return {"pinned": pinned, "unpinned": unpinned, "arbitrary": []}


def _parse_uv_lock(text: str, groups=(), extras=()) -> dict:
    """uv.lock, walked the way `uv sync --no-dev` would install it.

    uv puts markers on dependency *edges*, not packages, so a package's
    presence depends on the path to it. Walk from the workspace members,
    following only edges whose marker holds here -- a Windows-only
    dependency is then simply never reached on Linux rather than reported
    missing. Dev groups are left out unless named: a deployed environment
    is `--no-dev`, and every dev tool would read as missing there.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise LockfileError(f"not valid TOML: {exc}") from exc

    by_name: dict[str, list[dict]] = {}
    for pkg in doc.get("package", []):
        by_name.setdefault(normalize(pkg.get("name", "")), []).append(pkg)

    def pick(edge: dict) -> dict | None:
        found = by_name.get(normalize(edge.get("name", "")), [])
        if "version" in edge:  # a forked resolution names its version
            found = [p for p in found if p.get("version") == edge["version"]] or found
        return found[0] if found else None

    members = {normalize(m) for m in (doc.get("manifest") or {}).get("members", [])}
    roots = [p for pkgs in by_name.values() for p in pkgs
             if {"editable", "virtual"} & set(p.get("source") or {})
             and (normalize(p["name"]) in members
                  or (not members and (p["source"].get("editable") or p["source"].get("virtual")) == "."))]
    if not roots:
        raise LockfileError("no workspace member (a package with source editable/virtual) in this uv.lock")

    pinned, unpinned = {}, []
    seen: set[tuple[str, str]] = set()
    stack = [(root, tuple(extras), True) for root in roots]
    while stack:
        pkg, want_extras, is_root = stack.pop()
        name = normalize(pkg["name"])
        key = (name + "@" + str(pkg.get("version")), ",".join(sorted(want_extras)))
        if key in seen:
            continue
        seen.add(key)
        if pkg.get("version") and "virtual" not in (pkg.get("source") or {}):
            pinned[name] = pkg["version"]
        elif "virtual" not in (pkg.get("source") or {}):
            unpinned.append(name)  # an editable project with a dynamic version
        edges = list(pkg.get("dependencies", []))
        for extra in want_extras:
            edges += (pkg.get("optional-dependencies") or {}).get(extra, [])
        if is_root:
            for group in groups:
                edges += (pkg.get("dev-dependencies") or {}).get(group, [])
        for edge in edges:
            if not _applies(edge.get("marker", "")):
                continue
            dep = pick(edge)
            if dep is not None:
                stack.append((dep, tuple(edge.get("extra", [])), False))
    return {"pinned": pinned, "unpinned": sorted(set(unpinned) - set(pinned)), "arbitrary": []}


def _parse_pipfile_lock(text: str) -> dict:
    import json

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LockfileError(f"not valid JSON: {exc}") from exc
    pinned, unpinned, arbitrary = {}, [], []
    # "default" only: what `pipenv install --deploy` puts in a production
    # environment. "develop" packages would all read as missing there.
    for name, spec in (doc.get("default") or {}).items():
        if not isinstance(spec, dict) or not _applies(spec.get("markers", "")):
            continue
        version = spec.get("version", "")
        if version.startswith("==="):
            pinned[normalize(name)] = version[3:]
            arbitrary.append(normalize(name))
        elif version.startswith("=="):
            pinned[normalize(name)] = version[2:]
        else:
            unpinned.append(normalize(name))
    return {"pinned": pinned, "unpinned": unpinned, "arbitrary": arbitrary}
