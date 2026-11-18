"""Run: python tests/test_npm.py

package-lock.json parsing and the node_modules walk, against real
directory trees in a temp folder shaped the way npm 7+ lays them out.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from lockstep.check import EXTRA, MATCHED, MISSING, VERSION_MISMATCH, check_drift
from lockstep.cli import main
from lockstep.npm import NpmLockError, installed_node_modules, parse_package_lock
from lockstep.parse import LockfileError, parse_file

LOCK = {
    "name": "app", "lockfileVersion": 3, "requires": True,
    "packages": {
        "": {"name": "app", "dependencies": {"a": "^1", "@scope/b": "^2"}},
        "node_modules/a": {"version": "1.0.0"},
        "node_modules/a/node_modules/c": {"version": "2.0.0"},
        "node_modules/c": {"version": "1.0.0"},
        "node_modules/@scope/b": {"version": "2.1.0"},
        "node_modules/devtool": {"version": "5.0.0", "dev": True},
        "node_modules/win-binary": {"version": "0.1.0", "optional": True, "os": ["win32"]},
        "node_modules/ws-lib": {"resolved": "packages/ws-lib", "link": True},
        "packages/ws-lib": {"version": "0.0.1"},
        "packages/ws-lib/node_modules/d": {"version": "3.0.0"},
    },
}


class _Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "package-lock.json").write_text(json.dumps(LOCK))
        for path, entry in LOCK["packages"].items():
            if "node_modules/" in path and "version" in entry and path != "node_modules/win-binary" \
                    and path != "node_modules/devtool":
                self.install(path, entry["version"])
        self.install("packages/ws-lib", "0.0.1")

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, path: str, version: str) -> None:
        folder = self.root / path
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "package.json").write_text(json.dumps({"name": path.rsplit("/", 1)[-1], "version": version}))

    def drift(self, include_dev: bool = False) -> dict[str, str]:
        lock = parse_package_lock((self.root / "package-lock.json").read_text(), include_dev)
        found = installed_node_modules(self.root, lock["workspaces"])
        return {r["name"]: r["status"] for r in check_drift(lock, found) if r["status"] != MATCHED}


class TestNpm(_Tree):
    def test_an_exact_install_matches(self):
        self.assertEqual(self.drift(), {})

    def test_the_same_package_at_two_versions_is_checked_per_path(self):
        self.install("node_modules/a/node_modules/c", "2.0.1")
        self.assertEqual(self.drift(), {"node_modules/a/node_modules/c": VERSION_MISMATCH})

    def test_scoped_and_workspace_packages_are_walked(self):
        found = installed_node_modules(self.root, ["packages/ws-lib"])
        self.assertEqual(found["node_modules/@scope/b"], "2.1.0")
        self.assertEqual(found["packages/ws-lib/node_modules/d"], "3.0.0")

    def test_missing_and_hand_installed_packages_are_drift(self):
        (self.root / "node_modules/c/package.json").unlink()
        self.install("node_modules/left-pad", "1.3.0")
        self.assertEqual(self.drift(), {"node_modules/c": MISSING, "node_modules/left-pad": EXTRA})

    def test_dev_packages_are_neither_required_nor_extra_by_default(self):
        self.assertEqual(self.drift(), {})
        self.install("node_modules/devtool", "5.0.0")
        self.assertEqual(self.drift(), {})

    def test_dev_packages_are_required_when_asked_for(self):
        self.assertEqual(self.drift(include_dev=True), {"node_modules/devtool": MISSING})

    def test_an_absent_optional_package_is_fine_but_a_wrong_one_is_not(self):
        self.assertEqual(self.drift(), {})
        self.install("node_modules/win-binary", "0.2.0")
        self.assertEqual(self.drift(), {"node_modules/win-binary": VERSION_MISMATCH})

    def test_versions_compare_exactly(self):
        self.install("node_modules/a", "1.0")
        self.assertEqual(self.drift(), {"node_modules/a": VERSION_MISMATCH})

    def test_a_v1_lockfile_says_how_to_regenerate_it(self):
        with self.assertRaises(NpmLockError) as caught:
            parse_package_lock(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
        self.assertIn("npm install --package-lock-only", str(caught.exception))

    def test_parse_file_picks_npm_by_name(self):
        self.assertEqual(parse_file(self.root / "package-lock.json")["ecosystem"], "npm")
        (self.root / "npm-shrinkwrap.json").write_text("{")
        with self.assertRaises(LockfileError):
            parse_file(self.root / "npm-shrinkwrap.json")


class TestNpmCli(_Tree):
    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = main(["check", str(self.root / "package-lock.json"), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_clean_tree_exits_0_and_drift_exits_1(self):
        self.assertEqual(self.run_cli()[0], 0)
        self.install("node_modules/a", "9.9.9")
        code, out = self.run_cli("--quiet-matched")
        self.assertEqual(code, 1)
        self.assertIn("'node_modules/a' is pinned to 1.0.0 but 9.9.9 is installed", out)

    def test_python_only_flags_are_refused_for_npm(self):
        code, _ = self.run_cli("--python", sys.executable)
        self.assertIn("node_modules", str(code))


if __name__ == "__main__":
    unittest.main()
