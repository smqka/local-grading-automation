"""Portable contract checks for the optional Windows packaging layer."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "packaging" / "windows" / "launcher.py"
spec = importlib.util.spec_from_file_location("grading_windows_launcher", LAUNCHER)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherValidationTests(unittest.TestCase):
    def test_compatible_https_endpoint(self):
        self.assertEqual(
            launcher.validate_config("https://api.openai.com/v1/", " gpt-4.1 ", "abc"),
            ("https://api.openai.com/v1", "gpt-4.1", "abc"),
        )

    def test_insecure_remote_http_rejected(self):
        with self.assertRaises(ValueError):
            launcher.validate_config("http://example.com/v1", "gpt-4.1", "secret")

    def test_local_http_allowed(self):
        self.assertEqual(
            launcher.validate_config("http://127.0.0.1:8000/v1", "vision", "test")[0],
            "http://127.0.0.1:8000/v1",
        )

    def test_key_cannot_be_part_of_url(self):
        with self.assertRaises(ValueError):
            launcher.validate_config("https://username:password@host.test/v1", "vision", "test")

    def test_key_is_required(self):
        with self.assertRaises(ValueError):
            launcher.validate_config("https://api.openai.com/v1", "vision", "")

    def test_bundled_paths_are_consistent(self):
        ps = (ROOT / "packaging" / "windows" / "build.ps1").read_text(encoding="utf-8")
        for part in ("grading-api", "launcher", "node.exe", "server", "web"):
            self.assertIn(part, ps)


if __name__ == "__main__":
    unittest.main()
