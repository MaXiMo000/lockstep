"""Run: python tests/test_installed.py

Exercises the real importlib.metadata of the interpreter running this
test -- not a mock -- so this proves installed_packages() actually reads
real package metadata correctly, not just that it calls the right stdlib
function.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from lockstep.installed import installed_packages


class TestInstalledPackages(unittest.TestCase):
    def test_pip_itself_is_found(self):
        """pip is installed in essentially every real Python environment
        this tool will ever run in -- a safe, real package to assert on
        rather than a hypothetical one."""
        packages = installed_packages()
        self.assertIn("pip", packages)
        self.assertTrue(packages["pip"])  # a non-empty version string

    def test_all_keys_are_normalized(self):
        packages = installed_packages()
        for name in packages:
            self.assertEqual(name, name.lower())
            self.assertNotIn("_", name)

    def test_returns_a_real_nonempty_mapping(self):
        packages = installed_packages()
        self.assertGreater(len(packages), 0)
        for version in packages.values():
            self.assertIsInstance(version, str)


if __name__ == "__main__":
    unittest.main()
