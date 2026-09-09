"""Run: python tests/test_cli.py

Exercises the real CLI entry point against the real, currently-running
Python environment -- not mocked installed-package data -- so this proves
the whole pipeline (read file -> parse -> introspect this interpreter ->
diff -> report) actually works end to end.
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

from lockstep.cli import main
from lockstep.installed import installed_packages


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lockfile = pathlib.Path(self.tmp.name) / "requirements.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def test_correctly_pinned_real_package_matches(self):
        """pip is installed in this real environment -- pin it to its
        actual real version and lockstep should say it matches. Checked via
        --json against pip's specific entry, not the overall exit code:
        this test runs in a real, un-isolated dev environment with many
        other installed packages a one-line lockfile never declares, which
        correctly makes the *overall* result drift (see "What this
        assumes" in README) -- that's real, intended behavior, not
        something to work around by asserting a global pass here."""
        pip_version = installed_packages()["pip"]
        self.lockfile.write_text(f"pip=={pip_version}\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["check", str(self.lockfile), "--json"])
        report = json.loads(buf.getvalue())
        pip_entry = next(r for r in report if r["name"] == "pip")
        self.assertEqual(pip_entry["status"], "matched")

    def test_wrong_pinned_version_of_a_real_package_is_drift(self):
        self.lockfile.write_text("pip==0.0.1\n")  # almost certainly not what's really installed
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["check", str(self.lockfile)])
        self.assertEqual(code, 1)
        self.assertIn("[!=]", buf.getvalue())

    def test_a_package_that_cannot_exist_is_missing(self):
        self.lockfile.write_text("this-package-definitely-does-not-exist-xyz==1.0.0\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["check", str(self.lockfile)])
        self.assertEqual(code, 1)
        self.assertIn("[--]", buf.getvalue())

    def test_quiet_matched_hides_ok_rows_but_keeps_drift(self):
        pip_version = installed_packages()["pip"]
        self.lockfile.write_text(f"pip=={pip_version}\nthis-does-not-exist-xyz==1.0\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["check", str(self.lockfile), "--quiet-matched"])
        self.assertNotIn("[OK]", buf.getvalue())
        self.assertIn("[--]", buf.getvalue())

    def test_missing_lockfile_is_a_clean_error_not_a_traceback(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["check", str(self.lockfile)])  # never written
        self.assertIn("lockstep:", str(ctx.exception))

    def test_json_flag_prints_the_full_report(self):
        pip_version = installed_packages()["pip"]
        self.lockfile.write_text(f"pip=={pip_version}\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["check", str(self.lockfile), "--json"])
        report = json.loads(buf.getvalue())
        self.assertEqual(report[0]["name"], "pip")
        self.assertEqual(report[0]["status"], "matched")


if __name__ == "__main__":
    unittest.main()
