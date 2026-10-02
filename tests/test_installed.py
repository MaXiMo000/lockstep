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


class TestProbeIgnoresTheWorkingDirectory(unittest.TestCase):
    def test_a_stray_egg_info_in_cwd_is_not_installed(self):
        """Seen live: a source checkout's lockstep_evidence.egg-info read as
        an installed package, because `python -c` puts cwd on sys.path."""
        import os
        import tempfile
        from lockstep.installed import probe
        with tempfile.TemporaryDirectory() as tmp:
            info = pathlib.Path(tmp) / "phantom_pkg.egg-info"
            info.mkdir()
            (info / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: phantom-pkg\nVersion: 9.9\n",
                                           encoding="utf-8")
            here = os.getcwd()
            os.chdir(tmp)
            try:
                installed, _ = probe(sys.executable)
            finally:
                os.chdir(here)
        self.assertNotIn("phantom-pkg", installed)


if __name__ == "__main__":
    unittest.main()
