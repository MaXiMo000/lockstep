"""Parse a pinned requirements.txt-style lockfile into
{"pinned": {name: version}, "unpinned": [name, ...]}.

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

from .names import normalize

# Extras (`requests[security]`) and environment markers (`; python_version
# >= "3.8"`) are both real, common syntax in a real requirements file --
# found by testing this against actual pip-compile output, not synthetic
# "package==1.2.3" lines alone.
_PIN = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)'   # name
    r'(?:\[[^\]]*\])?'                  # optional extras, e.g. [security]
    r'\s*(?:===|==)\s*'                  # PEP 440 arbitrary-equality (===) tried
    r'([^\s;#]+)'                       # first, or == would eat two of its three '='
)
_RANGE_OP = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:>=|<=|!=|~=|>|<)'
)
_BARE_NAME = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*$')


def parse_lockfile(text: str) -> dict:
    pinned: dict[str, str] = {}
    unpinned: list[str] = []

    for raw_line in text.splitlines():
        # Environment markers and inline comments both trail after the
        # version; strip the comment first so a marker doesn't hide behind
        # it, then let each pattern's own [^\s;#]+ stop at a marker.
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue  # blank, or a pip option line (-r other.txt, --index-url ...)

        m = _PIN.match(line)
        if m:
            name, version = m.groups()
            pinned[normalize(name)] = version
            continue

        m = _RANGE_OP.match(line)
        if m:
            unpinned.append(normalize(m.group(1)))
            continue

        m = _BARE_NAME.match(line)
        if m:
            unpinned.append(normalize(m.group(1)))

    return {"pinned": pinned, "unpinned": unpinned}
