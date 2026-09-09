"""lockstep check <lockfile> [--json] [--quiet-matched]"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .check import EXTRA, MATCHED, MISSING, VERSION_MISMATCH, check_drift
from .installed import installed_packages
from .parse import parse_lockfile

_TAG = {MATCHED: "OK", VERSION_MISMATCH: "!=", MISSING: "--", EXTRA: "++"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lockstep")
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser(
        "check", help="compare this environment's installed packages against a pinned lockfile")
    check_p.add_argument("lockfile", help="a fully-pinned lockfile -- see README's \"What this assumes\"")
    check_p.add_argument("--json", action="store_true", help="print the full report as JSON")
    check_p.add_argument("--quiet-matched", action="store_true",
                          help="only print drift, not every package that already matches")

    args = parser.parse_args(argv)

    try:
        text = pathlib.Path(args.lockfile).read_text(encoding="utf-8")
    except OSError as exc:
        sys.exit(f"lockstep: {exc}")

    lockfile = parse_lockfile(text)
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


if __name__ == "__main__":
    raise SystemExit(main())
