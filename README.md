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
$ lockstep check requirements.lock
[!=] 'click' is pinned to 8.0.0 but 8.1.3 is installed
[--] 'requests' is pinned to 2.31.0 but is not installed
[++] 'pip' 24.0 is installed but not declared anywhere in the lockfile

0/3 matched, 3 drifted
```

(Real output, from a real venv.)

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

Exit code is `1` if anything drifted, `0` if every declared package
matches exactly.

## What this assumes

**A fully-pinned lockfile** -- the output of `pip freeze`, `pip-compile`,
or `poetry export`, every direct *and transitive* dependency pinned to an
exact version. Not a hand-written `requirements.txt` listing only your
own top-level packages. If you point this at a partial file, every
transitive dependency pip installed on its own behalf (which never
appears in a partial file) reports as `extra` -- correct, technically, but
noise that drowns the real signal. That's a lockfile-completeness problem
this tool surfaces, not a bug in it.

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
```

35 tests. Several exist because testing against real `pip-compile` output
shapes (not synthetic `"package==1.2.3"` lines) caught real parsing bugs
during development: PEP 440's `===` arbitrary-equality operator being
mangled by a regex that matched `==` first and left a stray `=` on the
version, and `package[extra]==1.2.3` syntax needing to be handled
explicitly rather than assumed away.

MIT licensed.
