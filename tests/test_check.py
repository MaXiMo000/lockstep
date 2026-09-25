"""Run: python tests/test_check.py"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from lockstep.check import EXTRA, MATCHED, MISSING, VERSION_MISMATCH, check_drift


class TestCheckDrift(unittest.TestCase):
    def test_exact_match(self):
        lockfile = {"pinned": {"requests": "2.31.0"}, "unpinned": []}
        installed = {"requests": "2.31.0"}
        results = check_drift(lockfile, installed)
        self.assertEqual(results, [{
            "name": "requests", "status": MATCHED,
            "locked_version": "2.31.0", "installed_version": "2.31.0",
            "detail": "'requests' matches its locked version 2.31.0",
        }])

    def test_version_mismatch(self):
        lockfile = {"pinned": {"requests": "2.31.0"}, "unpinned": []}
        installed = {"requests": "2.28.0"}
        results = check_drift(lockfile, installed)
        self.assertEqual(results[0]["status"], VERSION_MISMATCH)
        self.assertEqual(results[0]["installed_version"], "2.28.0")

    def test_pinned_but_not_installed_is_missing(self):
        lockfile = {"pinned": {"requests": "2.31.0"}, "unpinned": []}
        results = check_drift(lockfile, installed={})
        self.assertEqual(results[0]["status"], MISSING)
        self.assertIsNone(results[0]["installed_version"])

    def test_installed_but_undeclared_is_extra(self):
        """The headline case this tool exists for: a package present on
        disk that the lockfile says nothing about at all."""
        lockfile = {"pinned": {}, "unpinned": []}
        installed = {"some-hotfix-package": "0.0.1"}
        results = check_drift(lockfile, installed)
        self.assertEqual(results[0]["status"], EXTRA)
        self.assertEqual(results[0]["installed_version"], "0.0.1")

    def test_unpinned_declared_package_is_not_reported_as_extra(self):
        """A range/bare-name entry in the lockfile still counts as
        'declared' for the extra check, even though it has no version to
        compare against for drift."""
        lockfile = {"pinned": {}, "unpinned": ["click"]}
        installed = {"click": "8.1.3"}
        results = check_drift(lockfile, installed)
        self.assertEqual(results, [])

    def test_pep440_equal_versions_match_even_when_spelled_differently(self):
        # Regression: compared as strings, "1.0" vs "1.0.0" read as drift.
        for locked, installed in [("1.0", "1.0.0"), ("2.0RC1", "2.0rc1"), ("1.0.post0", "1.0.post0")]:
            lockfile = {"pinned": {"x": locked}, "unpinned": []}
            status = check_drift(lockfile, {"x": installed})[0]["status"]
            self.assertEqual(status, MATCHED, (locked, installed))

    def test_arbitrary_equality_pin_is_an_exact_string_match(self):
        lockfile = {"pinned": {"x": "1.0"}, "unpinned": [], "arbitrary": ["x"]}
        self.assertEqual(check_drift(lockfile, {"x": "1.0.0"})[0]["status"], VERSION_MISMATCH)

    def test_tooling_pip_freeze_omits_is_not_extra_but_is_checked_when_pinned(self):
        lockfile = {"pinned": {"setuptools": "70.0.0"}, "unpinned": []}
        results = check_drift(lockfile, {"pip": "25.0", "wheel": "0.43", "setuptools": "69.0.0"})
        self.assertEqual([(r["name"], r["status"]) for r in results],
                         [("setuptools", VERSION_MISMATCH)])

    def test_names_normalized_on_both_sides_still_match(self):
        lockfile = {"pinned": {"flask-login": "0.6.2"}, "unpinned": []}
        installed = {"flask-login": "0.6.2"}  # already normalized, as installed_packages() gives it
        results = check_drift(lockfile, installed)
        self.assertEqual(results[0]["status"], MATCHED)

    def test_results_are_sorted_by_name_deterministically(self):
        lockfile = {"pinned": {"zeta": "1.0", "alpha": "1.0"}, "unpinned": []}
        installed = {"zeta": "1.0", "alpha": "1.0"}
        results = check_drift(lockfile, installed)
        self.assertEqual([r["name"] for r in results], ["alpha", "zeta"])

    def test_mixed_real_scenario(self):
        lockfile = {"pinned": {"requests": "2.31.0", "click": "8.1.3"}, "unpinned": ["numpy"]}
        installed = {
            "requests": "2.31.0",       # matched
            "click": "8.0.0",           # version_mismatch
            "numpy": "1.24.0",          # declared unpinned, no drift possible
            "sneaky-hotfix": "0.1.0",   # extra
            # "flask" (if it were pinned) would be missing -- not in this scenario
        }
        results = check_drift(lockfile, installed)
        by_name = {r["name"]: r["status"] for r in results}
        self.assertEqual(by_name, {
            "requests": MATCHED, "click": VERSION_MISMATCH, "sneaky-hotfix": EXTRA,
        })


if __name__ == "__main__":
    unittest.main()
