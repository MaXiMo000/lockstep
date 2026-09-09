"""Run: python tests/test_names.py"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from lockstep.names import normalize


class TestNormalize(unittest.TestCase):
    def test_dashes_underscores_dots_are_equivalent(self):
        self.assertEqual(normalize("Flask-Login"), normalize("flask_login"))
        self.assertEqual(normalize("flask_login"), normalize("flask.login"))

    def test_case_insensitive(self):
        self.assertEqual(normalize("Requests"), normalize("REQUESTS"))

    def test_repeated_separators_collapse(self):
        self.assertEqual(normalize("foo__bar"), normalize("foo-bar"))

    def test_all_together(self):
        self.assertEqual(normalize("Foo_Bar.Baz"), "foo-bar-baz")


if __name__ == "__main__":
    unittest.main()
