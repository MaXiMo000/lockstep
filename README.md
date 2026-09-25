# lockstep

[![ci](https://github.com/MaXiMo000/lockstep/actions/workflows/ci.yml/badge.svg)](https://github.com/MaXiMo000/lockstep/actions/workflows/ci.yml)

**Does what's actually installed match the lockfile? Runtime dependency
drift, not a commit-time CVE scan.**

[`carabiner`](https://github.com/MaXiMo000/carabiner)'s `deps` engine
answers "does the lockfile *committed to this repo* have a known CVE" --
a question about the source tree, checked in CI. `lockstep` answers a
different one: does the environment actually *running right now* --
the container, the server, the venv someone SSHed into and patched by
hand -- still match what that lockfile says should be there. A CVE scan
at commit time can't see drift that happens after deploy; this is built
specifically to.

```
$ lockstep check requirements.lock --quiet-matched
[!=] 'click' is pinned to 8.1.8 but 8.1.7 is installed
[--] 'requests' is pinned to 2.32.3 but is not installed
[++] 'six' 1.16.0 is installed but not declared anywhere in the lockfile

3/6 matched, 3 drifted
```

And the drift a version number can't show -- installed code that was
edited in place after install:

```
$ lockstep verify
[!=] click 8.1.7: click/core.py was modified after install

5/6 package(s) intact, 529 file(s) checked
```

(Both real output, from a real venv. The lockfile also pinned
`uvloop ; sys_platform != "win32"` -- correctly not expected on the
Windows machine this ran on, so not reported missing.)

## Install

```
pip install lockstep-evidence   # the command it installs is `lockstep`
```

(`lockstep` was already taken on PyPI -- same story as every sibling in
this portfolio.)

## Use

Run it **inside** the environment you want to verify -- the container at
runtime, the deployed server, the venv itself -- against a lockfile:

```
lockstep check requirements.lock
```

It reads the *running interpreter's own* installed-package metadata
(`importlib.metadata`, stdlib, no subprocess) and compares it against the
lockfile. `--json` prints the full machine-readable report; `--quiet-matched`
hides packages that already match, showing only drift.

## `lockstep verify`: was installed code edited in place?

Every wheel install writes a `RECORD` -- each file it put down, with its
sha256. pip writes it and never reads it again. So a file in
site-packages hand-patched on a live server, "fixed" during a debugging
session and left that way, or tampered with after install still reports
the same version to pip, to `pip freeze`, and to `lockstep check`. The
version string didn't change; the code did.

`lockstep verify` re-hashes every installed file against its own `RECORD`
entry and names each one that's **modified** or **missing**. `lockstep
verify requests urllib3` checks just those. It's fast -- hashing is the
only work (about 500 files in well under a second here) -- so it fits in
a container's startup or a deploy's health check. A package installed
without a `RECORD` (a legacy egg-style editable install) is listed as
uncheckable, never counted as intact.

What it doesn't prove: that the *original* install was the real package.
A `RECORD` is written by whoever installed it; if that install came from a
compromised index, it'll describe the compromised files faithfully. Pair
it with hash-pinned installs (`pip install --require-hashes`) for that.

## Three kinds of drift, not one

| Status | Meaning |
|---|---|
| `matched` | Installed version equals the locked version. |
| `version_mismatch` | Installed, but a different version than declared. |
| `missing` | Declared in the lockfile, not installed at all. |
| `extra` | Installed, but the lockfile says nothing about it. |

`extra` is the headline case: the hotfix someone `pip install`ed directly
on a live server that never made it back into the lockfile, silently
outliving the deploy that was supposed to make it official. A commit-time
scan of the lockfile alone can never see this -- by the time it exists,
the running environment and the committed lockfile have already diverged.

Versions are compared the way pip compares them (PEP 440, via
`packaging`): `1.0` and `1.0.0` match, and so do `2.0RC1` and `2.0rc1`. A
`===` pin is the exception PEP 440 defines: exact string equality.

`pip`, `setuptools`, `wheel` and `distribute` are never reported as
`extra`, because `pip freeze` leaves them out of the lockfile it writes. If
your lockfile does pin one of them, it's checked like anything else.

Exit code is `1` if anything drifted, `0` if every declared package
matches.

## Lockfile formats

- **requirements-style** (`pip freeze`, `pip-compile`, `uv pip compile`,
  `poetry export`): `==`/`===` pins, extras, hashes, and environment
  markers -- a pin whose marker doesn't hold here (`colorama ;
  sys_platform == "win32"` on Linux) isn't expected, so it's never a false
  "missing".
- **`pylock.toml`** (PEP 751, the standard lockfile format), with
  per-package markers.
- **`Pipfile.lock`**: the `default` packages, i.e. what `pipenv install
  --deploy` puts in production.
- **`uv.lock` / `poetry.lock`** aren't read directly -- their platform
  markers live on dependency edges, so every platform-specific package
  would read as missing elsewhere. lockstep tells you the export command
  instead: `uv export --format pylock.toml`, or `poetry export -f
  requirements.txt`.

The lockfile must be **fully pinned**: every direct *and transitive*
dependency, the way all of the above produce it. A hand-written
`requirements.txt` listing only top-level packages makes every transitive
dependency read as `extra` -- correct, technically, but noise.

## Not the same question as `pip check`

`pip check` already ships with pip, and answers the obvious first
question: are the packages *currently installed* internally consistent
with each other's own declared requirements (nothing needs `foo>=2.0`
while `foo 1.0` is what's actually there)? It never reads a lockfile at
all -- it can't tell you whether reality matches what you *intended* to
have installed, only whether what's installed is self-consistent right
now. An environment can pass `pip check` cleanly while still being three
versions behind its own lockfile, or running a hotfixed package the
lockfile has never heard of -- exactly lockstep's `extra` case, above.

The two are complementary, not competing: `pip check` catches a broken
dependency graph; `lockstep check` catches drift from your own declared
source of truth. Worth running both -- neither substitutes for the
other, and `pip check` costs nothing extra since it's already there.

## What this does NOT do

- **Python only, via `pip`/PyPI metadata.** `carabiner`'s own `deps.py`
  docstring makes the same call for the same reason: "the plan called for
  pip-audit, npm audit and osv-scanner... it gets one" -- one ecosystem
  done correctly beats three done shallowly. npm/Cargo/etc. runtime drift
  is the same idea, applied to a different package manager; not built here.
- **No CVE data, no severity, no vulnerability database.** That's
  `carabiner`'s `deps` engine's job already, at commit time. This only
  asks "does reality match the declaration," not "is the declared version
  itself safe" -- genuinely different questions, and conflating them would
  duplicate an engine that already exists and does that one well.
- **Doesn't distinguish a top-level `extra` from a transitive one.** Real
  dependency-tree resolution (which package pulled in which) is
  `pip-compile`-level complexity; out of scope for what's meant to be a
  small, fast check.

## Tests

```
pip install -e .
python tests/test_names.py       # PEP 503 name normalization
python tests/test_parse.py       # lockfile parsing -- extras, ===, hashes, markers
python tests/test_installed.py   # reads THIS interpreter's real installed packages
python tests/test_check.py       # matched/version_mismatch/missing/extra classification
python tests/test_cli.py         # the real CLI, against this real environment
python tests/test_verify.py      # RECORD verification, pylock.toml, Pipfile.lock, markers
```

35 tests. Several exist because testing against real `pip-compile` output
shapes (not synthetic `"package==1.2.3"` lines) caught real parsing bugs
during development: PEP 440's `===` arbitrary-equality operator being
mangled by a regex that matched `==` first and left a stray `=` on the
version, and `package[extra]==1.2.3` syntax needing to be handled
explicitly rather than assumed away.

MIT licensed.
