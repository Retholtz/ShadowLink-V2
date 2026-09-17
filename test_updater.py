"""
Unit tests for the ShadowLink Auto-Update subsystem.
Tests version parsing, comparison logic, asset extraction,
mocked GitHub release responses, and live GitHub API queries.
"""

from __future__ import annotations
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import zipfile

import config
import updater
from updater import (
    ReleaseInfo,
    check_for_updates,
    extract_executable_from_zip,
    install_update_and_restart,
    is_version_newer,
    parse_version,
)


class TestVersionLogic(unittest.TestCase):
    def test_parse_version_strings(self):
        self.assertEqual(parse_version("Version-1.0"), (1, 0))
        self.assertEqual(parse_version("v1.1"), (1, 1))
        self.assertEqual(parse_version("1.1"), (1, 1))
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("ShadowLink-1.40"), (1, 40))
        self.assertEqual(parse_version("v2.0.0-beta"), (2, 0, 0))
        self.assertEqual(parse_version(""), (0,))
        self.assertEqual(parse_version("invalid"), (0,))

    def test_is_version_newer(self):
        # Newer
        self.assertTrue(is_version_newer("1.1", "1.0"))
        self.assertTrue(is_version_newer("Version-1.2", "1.1"))
        self.assertTrue(is_version_newer("1.10", "1.2"))
        self.assertTrue(is_version_newer("2.0.0", "1.9.9"))
        self.assertTrue(is_version_newer("1.1.1", "1.1"))

        # Not newer (equal or older)
        self.assertFalse(is_version_newer("Version-1.0", "1.1"))
        self.assertFalse(is_version_newer("1.1", "1.1"))
        self.assertFalse(is_version_newer("1.1.0", "1.1"))
        self.assertFalse(is_version_newer("1.0", "1.1"))
        self.assertFalse(is_version_newer("1.0.5", "1.1"))


class TestReleaseParsing(unittest.TestCase):
    def test_check_for_updates_with_exe_asset(self):
        mock_payload = {
            "tag_name": "v1.2",
            "name": "ShadowLink 1.2 Release",
            "body": "Fixed controller reconnect and added new binds.",
            "html_url": "https://github.com/Retholtz/ShadowLink-V2/releases/tag/v1.2",
            "published_at": "2026-09-17T00:00:00Z",
            "assets": [
                {
                    "name": "ShadowLink.exe",
                    "browser_download_url": "https://github.com/download/ShadowLink.exe",
                    "size": 45000000,
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            has_update, rel_info, msg = check_for_updates(current_version="1.1")
            self.assertTrue(has_update)
            self.assertIsNotNone(rel_info)
            self.assertEqual(rel_info.version_str, "1.2")
            self.assertEqual(rel_info.asset_name, "ShadowLink.exe")
            self.assertFalse(rel_info.is_zip)
            self.assertEqual(rel_info.asset_size, 45000000)

    def test_check_for_updates_with_zip_asset(self):
        mock_payload = {
            "tag_name": "Version-1.0",
            "name": "Version 1.0",
            "body": "Initial release",
            "html_url": "https://github.com/Retholtz/ShadowLink-V2/releases/tag/Version-1.0",
            "assets": [
                {
                    "name": "ShadowLink.V2.zip",
                    "browser_download_url": "https://github.com/download/ShadowLink.V2.zip",
                    "size": 47489259,
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            # When current version is 1.1, Version-1.0 is NOT newer
            has_update, rel_info, msg = check_for_updates(current_version="1.1")
            self.assertFalse(has_update)
            self.assertIsNotNone(rel_info)
            self.assertEqual(rel_info.tag_name, "Version-1.0")
            self.assertTrue(rel_info.is_zip)
            self.assertIn("up to date", msg)

            # If current version is 0.9, Version-1.0 IS newer
            has_update_old, rel_info_old, msg_old = check_for_updates(current_version="0.9")
            self.assertTrue(has_update_old)
            self.assertIn("available", msg_old)

    def test_check_for_updates_network_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            has_update, rel_info, msg = check_for_updates(current_version="1.1")
            self.assertFalse(has_update)
            self.assertIsNone(rel_info)
            self.assertIn("Could not connect to GitHub", msg)


class TestZipExtraction(unittest.TestCase):
    def test_extract_executable_from_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "test_package.zip"
            extract_out = tmp_path / "output"

            # Create a mock zip containing ShadowLink.exe
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("ShadowLink.exe", b"MZ_MOCK_EXE_BYTES")
                zf.writestr("readme.txt", b"Instructions")

            exe = extract_executable_from_zip(zip_path, extract_out)
            self.assertIsNotNone(exe)
            self.assertEqual(exe.name.lower(), "shadowlink.exe")
            self.assertEqual(exe.read_bytes(), b"MZ_MOCK_EXE_BYTES")


class TestLiveGitHubAPI(unittest.TestCase):
    def test_live_repo_query(self):
        """Tests live GitHub query against https://api.github.com/repos/Retholtz/ShadowLink-V2/releases/latest"""
        has_update, rel_info, msg = check_for_updates(current_version="1.1")
        # In the live repo, the current latest tag is Version-1.0
        if rel_info is not None:
            self.assertEqual(rel_info.tag_name, "Version-1.0")
            # Since our version is 1.1, has_update must be False
            self.assertFalse(has_update)
            self.assertIn("up to date", msg)


if __name__ == "__main__":
    unittest.main()

