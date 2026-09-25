"""Run: python tests/test_verify.py

`lockstep verify` against a distribution laid out on disk exactly as pip
installs one (a .dist-info with METADATA and a RECORD of sha256s), read
through the real importlib.metadata -- then modified, deleted, and left
alone. Plus the pylock.toml / Pipfile.lock parsers and marker handling.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from importlib import metadata

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from lockstep.cli import main
from lockstep.parse import LockfileError, parse_file, parse_lockfile
from lockstep.verify import verify_distribution


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def install_fake(site: pathlib.Path) -> metadata.Distribution:
    files = {"demo/__init__.py": b"VERSION = '1.0'\n", "demo/core.py": b"def add(a, b):\n    return a + b\n"}
    for rel, data in files.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_bytes(data)
    info = site / "demo-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: Demo\nVersion: 1.0\n", encoding="utf-8")
    record = [f"{rel},{_record_hash(data)},{len(data)}" for rel, data in files.items()]
    record += ["demo-1.0.dist-info/METADATA,,", "demo-1.0.dist-info/RECORD,,"]
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")
    return metadata.PathDistribution(info)


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = pathlib.Path(self.tmp.name)
        self.dist = install_fake(self.site)

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_untouched_install_is_intact(self):
        r = verify_distribution(self.dist)
        self.assertEqual((r["name"], r["checked"], r["modified"], r["missing"]), ("demo", 2, [], []))
        self.assertEqual(r["unhashed"], 2)  # METADATA and RECORD have no hash; counted, not "verified"

    def test_a_patched_file_is_named(self):
        (self.site / "demo" / "core.py").write_bytes(b"def add(a, b):\n    return a - b  # hotfix\n")
        self.assertEqual(verify_distribution(self.dist)["modified"], ["demo/core.py"])

    def test_a_deleted_file_is_missing(self):
        (self.site / "demo" / "__init__.py").unlink()
        self.assertEqual(verify_distribution(self.dist)["missing"], ["demo/__init__.py"])

    def test_a_distribution_with_no_record_says_so(self):
        (self.site / "demo-1.0.dist-info" / "RECORD").unlink()
        r = verify_distribution(self.dist)
        self.assertTrue(r["no_record"])
        self.assertEqual(r["checked"], 0)

    def test_cli_verify_on_this_real_environment(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["verify", "--json"])
        results = json.loads(out.getvalue())
        self.assertIn("packaging", {r["name"] for r in results})
        self.assertEqual(code, 0, [r for r in results if r["modified"] or r["missing"]])


class TestLockfileFormats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_pylock_toml_with_markers_and_a_vcs_package(self):
        p = self._write("pylock.toml", '''lock-version = "1.0"
created-by = "uv"
[[packages]]
name = "Requests"
version = "2.32.3"
[[packages]]
name = "colorama"
version = "0.4.6"
marker = "sys_platform == 'nonexistent-os'"
[[packages]]
name = "mylib"
[packages.vcs]
type = "git"
url = "https://example.com/mylib.git"
commit-id = "abc"
''')
        self.assertEqual(parse_file(p), {"pinned": {"requests": "2.32.3"}, "unpinned": ["mylib"],
                                         "arbitrary": []})

    def test_pipfile_lock_default_only(self):
        p = self._write("Pipfile.lock", json.dumps({
            "_meta": {},
            "default": {"flask": {"version": "==3.0.3"}, "attrs": {"version": "===23.1.0"},
                        "pywin32": {"version": "==306", "markers": "sys_platform == 'nonexistent-os'"},
                        "mylib": {"git": "https://example.com/mylib.git"}},
            "develop": {"pytest": {"version": "==8.0.0"}},
        }))
        self.assertEqual(parse_file(p), {"pinned": {"flask": "3.0.3", "attrs": "23.1.0"},
                                         "unpinned": ["mylib"], "arbitrary": ["attrs"]})

    def test_uv_and_poetry_lock_point_at_their_export_command(self):
        for name, hint in (("uv.lock", "uv export --format pylock.toml"), ("poetry.lock", "poetry export")):
            with self.assertRaises(LockfileError) as ctx:
                parse_file(self._write(name, ""))
            self.assertIn(hint, str(ctx.exception))

    def test_requirements_marker_for_another_platform_is_not_expected_here(self):
        result = parse_lockfile("colorama==0.4.6 ; sys_platform == 'nonexistent-os'\n"
                                "requests==2.31.0 ; python_version >= '3'\n")
        self.assertEqual(result["pinned"], {"requests": "2.31.0"})

    def test_an_unparseable_marker_still_counts_as_expected(self):
        self.assertEqual(parse_lockfile("x==1.0 ; this is not a marker\n")["pinned"], {"x": "1.0"})


if __name__ == "__main__":
    unittest.main()
