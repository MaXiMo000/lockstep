"""lockstep check <lockfile> [--json] [--quiet-matched]
lockstep verify [package ...] [--json]"""
from __future__ import annotations

import argparse
import json
import sys

from .check import EXTRA, MATCHED, MISSING, VERSION_MISMATCH, check_drift
from .installed import installed_packages
from .names import normalize
from .parse import LockfileError, parse_file
from .verify import verify_installed

_TAG = {MATCHED: "OK", VERSION_MISMATCH: "!=", MISSING: "--", EXTRA: "++"}


def _check(args) -> int:
    try:
        lockfile = parse_file(args.lockfile)
    except (OSError, UnicodeDecodeError, LockfileError) as exc:
        sys.exit(f"lockstep: {exc}")
    results = check_drift(lockfile, installed_packages())

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            if args.quiet_matched and r["status"] == MATCHED:
                continue
            print(f"[{_TAG[r['status']]}] {r['detail']}")
        n_drift = sum(1 for r in results if r["status"] != MATCHED)
        summary = f"{len(results) - n_drift}/{len(results)} matched"
        if n_drift:
            summary += f", {n_drift} drifted"
        print(f"\n{summary}")

    return 1 if any(r["status"] != MATCHED for r in results) else 0


def _verify(args) -> int:
    only = {normalize(n) for n in args.packages} or None
    results = verify_installed(only)
    if only:
        found = {r["name"] for r in results}
        for name in sorted(only - found):
            sys.exit(f"lockstep: '{name}' is not installed")
    bad = [r for r in results if r["modified"] or r["missing"]]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in bad:
            for f in r["modified"]:
                print(f"[!=] {r['name']} {r['version']}: {f} was modified after install")
            for f in r["missing"]:
                print(f"[--] {r['name']} {r['version']}: {f} is missing")
        no_record = [r["name"] for r in results if r["no_record"]]
        checked = sum(r["checked"] for r in results)
        print(f"\n{len(results) - len(bad)}/{len(results)} package(s) intact, {checked} file(s) checked"
              + (f"; {len(no_record)} with no RECORD to check against: {', '.join(no_record)}"
                 if no_record else ""))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lockstep")
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser(
        "check", help="compare this environment's installed packages against a pinned lockfile")
    check_p.add_argument("lockfile", help="requirements-style lockfile, pylock.toml, or Pipfile.lock")
    check_p.add_argument("--json", action="store_true", help="print the full report as JSON")
    check_p.add_argument("--quiet-matched", action="store_true",
                         help="only print drift, not every package that already matches")
    check_p.set_defaults(func=_check)

    verify_p = sub.add_parser(
        "verify", help="re-hash installed files against each package's own RECORD")
    verify_p.add_argument("packages", nargs="*", help="only these packages (default: all)")
    verify_p.add_argument("--json", action="store_true", help="print the full report as JSON")
    verify_p.set_defaults(func=_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
