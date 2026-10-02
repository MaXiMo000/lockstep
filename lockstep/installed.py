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


# Run by the *target* interpreter, so stdlib only. Returns what it has
# installed and its PEP 508 marker environment -- a marker has to be judged
# against the environment being checked, not the one lockstep runs in.
_PROBE = r'''
import json, os, platform, sys
# `python -c` puts the working directory on sys.path, so a stray
# *.egg-info there -- a source checkout, an image's WORKDIR -- read as an
# installed package. Only what the interpreter itself would load counts.
sys.path[:] = [p for p in sys.path if p not in ("", ".", os.getcwd())]
from importlib import metadata
v = sys.implementation.version
iv = "%d.%d.%d" % (v.major, v.minor, v.micro)
if v.releaselevel != "final":
    iv += v.releaselevel[0] + str(v.serial)
print(json.dumps({
    "dists": {d.metadata.get("Name"): d.version for d in metadata.distributions() if d.metadata.get("Name")},
    "env": {
        "implementation_name": sys.implementation.name, "implementation_version": iv,
        "os_name": os.name, "platform_machine": platform.machine(),
        "platform_release": platform.release(), "platform_system": platform.system(),
        "platform_version": platform.version(), "python_full_version": platform.python_version(),
        "platform_python_implementation": platform.python_implementation(),
        "python_version": ".".join(platform.python_version_tuple()[:2]),
        "sys_platform": sys.platform,
    },
}))
'''


def probe(python: str) -> tuple[dict[str, str], dict[str, str]]:
    """(installed packages, marker environment) of another interpreter --
    a venv, or a container's python via a wrapper script -- so lockstep
    need not be installed in the environment it is checking."""
    import os
    import shutil
    # A bare name is looked up on PATH; a relative path is made absolute,
    # because Windows will not launch `.venv/Scripts/python.exe` as given.
    python = shutil.which(python) or os.path.abspath(python)
    return _run_probe([python], python)


def probe_image(image: str) -> tuple[dict[str, str], dict[str, str]]:
    """The same probe inside a container image: `docker run --rm` with no
    network, nothing installed into it, nothing left behind. Tries python3,
    then python -- slim images ship one or the other."""
    errors = []
    for exe in ("python3", "python"):
        try:
            return _run_probe(["docker", "run", "--rm", "--network", "none",
                               "--entrypoint", exe, image], f"{image} ({exe})", timeout=300)
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def _run_probe(prefix: list[str], label: str, timeout: int = 60):
    import json
    import subprocess
    try:
        ran = subprocess.run([*prefix, "-c", _PROBE], capture_output=True, text=True,
                             encoding="utf-8", timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not run {label}: {exc}") from None
    if ran.returncode != 0:
        raise RuntimeError(f"could not run {label}: {(ran.stderr or '').strip()[-200:]}")
    data = json.loads(ran.stdout)
    return {normalize(n): v for n, v in data["dists"].items()}, data["env"]
