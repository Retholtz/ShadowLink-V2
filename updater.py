"""
Auto-Update Subsystem for ShadowLink.
Queries the GitHub Releases API, checks for newer versions, downloads release assets,
and performs seamless background self-updates using a Windows batch launcher.
"""

from __future__ import annotations
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional
import urllib.error
import urllib.request
import zipfile

from PySide6.QtCore import QObject, QThread, Signal

import config

logger = logging.getLogger("ShadowLink.Updater")


@dataclass
class ReleaseInfo:
    tag_name: str
    version_str: str
    version_tuple: tuple[int, ...]
    title: str
    notes: str
    html_url: str
    asset_name: str
    download_url: str
    asset_size: int
    is_zip: bool
    published_at: str


def parse_version(v_str: str) -> tuple[int, ...]:
    """
    Extracts numerical version components from a version string or tag.
    Examples:
        'Version-1.0' -> (1, 0)
        'v1.1'        -> (1, 1)
        '1.2.3'       -> (1, 2, 3)
        'Version 1.40' -> (1, 40)
    """
    if not v_str:
        return (0,)
    # Find sequence of digits separated by dots or dashes
    match = re.search(r"(\d+(?:[.\-_]\d+)*)", v_str)
    if not match:
        return (0,)

    parts_str = re.split(r"[.\-_]", match.group(1))
    parts: list[int] = []
    for p in parts_str:
        try:
            parts.append(int(p))
        except ValueError:
            break

    return tuple(parts) if parts else (0,)


def is_version_newer(latest_str: str, current_str: str) -> bool:
    """
    Compares two version strings. Returns True if latest_str is strictly newer than current_str.
    Normalizes tuple lengths with zeros (e.g. (1, 1) vs (1, 1, 0) are equal).
    """
    t_latest = list(parse_version(latest_str))
    t_current = list(parse_version(current_str))

    max_len = max(len(t_latest), len(t_current))
    t_latest.extend([0] * (max_len - len(t_latest)))
    t_current.extend([0] * (max_len - len(t_current)))

    return tuple(t_latest) > tuple(t_current)


def check_for_updates(
    current_version: str = config.APP_VERSION,
    api_url: str = config.GITHUB_API_URL,
    timeout_sec: float = 8.0,
) -> tuple[bool, Optional[ReleaseInfo], str]:
    """
    Queries GitHub API for the latest release and checks if a newer version is available.
    Returns:
        (has_update: bool, release_info: Optional[ReleaseInfo], message: str)
    """
    logger.info(f"Checking for updates from GitHub ({api_url}). Current version: {current_version}")
    req = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ShadowLink-App",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            if response.status != 200:
                msg = f"GitHub API check returned status {response.status}"
                logger.warning(msg)
                return False, None, msg

            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = f"GitHub API returned HTTP {e.code}: {e.reason}"
        logger.warning(msg)
        return False, None, msg
    except urllib.error.URLError as e:
        msg = f"Could not connect to GitHub: {e.reason}"
        logger.warning(msg)
        return False, None, msg
    except Exception as e:
        msg = f"Error checking for updates: {e}"
        logger.error(msg)
        return False, None, msg

    tag_name = payload.get("tag_name", "")
    if not tag_name:
        msg = "No release tag found in GitHub response."
        logger.warning(msg)
        return False, None, msg

    parsed_tuple = parse_version(tag_name)
    version_str = ".".join(str(x) for x in parsed_tuple) if parsed_tuple else tag_name
    title = payload.get("name") or f"Release {tag_name}"
    notes = payload.get("body") or ""
    html_url = payload.get("html_url", f"https://github.com/{config.GITHUB_REPO}/releases")
    published_at = payload.get("published_at", "")

    # Look for assets (.exe preferred, then .zip)
    assets = payload.get("assets", [])
    selected_asset = None

    # First search for direct .exe binary
    for a in assets:
        if a.get("name", "").lower().endswith(".exe"):
            selected_asset = a
            break

    # If no .exe found, search for .zip archive
    if not selected_asset:
        for a in assets:
            if a.get("name", "").lower().endswith(".zip"):
                selected_asset = a
                break

    if selected_asset:
        asset_name = selected_asset.get("name", "")
        download_url = selected_asset.get("browser_download_url", "")
        asset_size = int(selected_asset.get("size", 0))
        is_zip = asset_name.lower().endswith(".zip")
    else:
        # Fallback to source zipball if no compiled assets are attached
        asset_name = f"{tag_name}.zip"
        download_url = payload.get("zipball_url", "")
        asset_size = 0
        is_zip = True

    rel_info = ReleaseInfo(
        tag_name=tag_name,
        version_str=version_str,
        version_tuple=parsed_tuple,
        title=title,
        notes=notes,
        html_url=html_url,
        asset_name=asset_name,
        download_url=download_url,
        asset_size=asset_size,
        is_zip=is_zip,
        published_at=published_at,
    )

    has_update = is_version_newer(tag_name, current_version)
    if has_update:
        msg = f"Version {version_str} is available! (Current: {current_version})"
        logger.info(msg)
        return True, rel_info, msg
    else:
        msg = f"You are up to date! (Version {current_version})"
        logger.info(msg)
        return False, rel_info, msg


class UpdateDownloaderThread(QThread):
    """
    Background worker thread to download the update asset with progress tracking.
    """
    progress = Signal(int, int)              # (bytes_downloaded, total_bytes)
    finished = Signal(bool, str, str)        # (success, message, local_file_path)

    def __init__(self, download_url: str, target_file: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.download_url = download_url
        self.target_file = target_file
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        logger.info(f"Starting download from {self.download_url} to {self.target_file}")
        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "ShadowLink-App"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_size = int(resp.headers.get("Content-Length", 0))
                bytes_read = 0
                chunk_size = 64 * 1024  # 64 KB chunks

                self.target_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.target_file, "wb") as f:
                    while True:
                        if self._cancelled:
                            logger.info("Download cancelled by user.")
                            self.finished.emit(False, "Download cancelled.", "")
                            return

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)
                        self.progress.emit(bytes_read, total_size)

            logger.info(f"Download complete: {self.target_file} ({bytes_read} bytes)")
            self.finished.emit(True, "Download complete.", str(self.target_file))

        except Exception as e:
            logger.error(f"Download failed: {e}")
            if self.target_file.exists():
                try:
                    self.target_file.unlink()
                except Exception:
                    pass
            self.finished.emit(False, f"Download failed: {e}", "")


def extract_executable_from_zip(zip_path: Path, output_dir: Path) -> Optional[Path]:
    """
    Extracts an executable from a downloaded zip archive.
    Searches for ShadowLink.exe first, or any .exe binary.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            # 1. Prefer ShadowLink.exe
            target_entry = next((n for n in namelist if Path(n).name.lower() == "shadowlink.exe"), None)
            if not target_entry:
                # 2. Fallback to any .exe
                target_entry = next((n for n in namelist if n.lower().endswith(".exe")), None)

            if target_entry:
                zf.extract(target_entry, output_dir)
                extracted_path = output_dir / target_entry
                logger.info(f"Extracted executable '{extracted_path.name}' from {zip_path.name}")
                return extracted_path

            # If no .exe found, extract all
            zf.extractall(output_dir)
            for f in output_dir.rglob("*.exe"):
                return f
    except Exception as e:
        logger.error(f"Failed to extract zip archive: {e}")

    return None


def install_update_and_restart(downloaded_file: Path) -> tuple[bool, str]:
    """
    Installs the downloaded update.
    - If running frozen (PyInstaller executable):
        Stages the new binary as ShadowLink_Update.exe and executes updater.bat
        which waits for ShadowLink to close, deletes the old executable, renames the new one,
        and launches it before deleting itself.
    - If running from source (development mode):
        Leaves the file intact and informs the user.
    """
    is_frozen = getattr(sys, "frozen", False)

    # 1. Resolve source executable from download
    source_exe: Optional[Path] = None
    if downloaded_file.suffix.lower() == ".zip":
        extract_dir = downloaded_file.parent / "extracted_update"
        extract_dir.mkdir(parents=True, exist_ok=True)
        source_exe = extract_executable_from_zip(downloaded_file, extract_dir)
        if not source_exe:
            return False, "Could not find an executable inside the downloaded ZIP archive."
    else:
        source_exe = downloaded_file

    # 2. If running frozen, execute self-updating batch script
    if is_frozen:
        current_exe = Path(sys.executable)
        app_dir = current_exe.parent
        staged_update = app_dir / "ShadowLink_Update.exe"

        try:
            # Copy source_exe to staged location next to current_exe
            shutil.copy2(source_exe, staged_update)
        except Exception as e:
            return False, f"Could not stage update file at {staged_update}: {e}"

        bat_file = app_dir / "updater.bat"
        # Script waits 2 seconds, retries deleting current_exe until released,
        # renames the update to current_exe, starts it, and deletes updater.bat
        bat_content = f"""@echo off
cd /d "%~dp0"
timeout /t 2 /nobreak > nul
:retry_del
del "{current_exe.name}" >nul 2>&1
if exist "{current_exe.name}" (
    timeout /t 1 /nobreak > nul
    goto retry_del
)
ren "{staged_update.name}" "{current_exe.name}"
start "" "{current_exe.name}"
del "%~f0" & exit
"""
        try:
            bat_file.write_text(bat_content, encoding="utf-8")
        except Exception as e:
            return False, f"Could not create updater batch script: {e}"

        logger.info(f"Launching updater script: {bat_file}")
        try:
            # Launch updater detached
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", str(bat_file.name)],
                cwd=str(app_dir),
                shell=True,
                creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
            )
            return True, "Update ready. Restarting ShadowLink..."
        except Exception as e:
            return False, f"Failed to launch updater process: {e}"

    else:
        # Running from Python source (dev mode)
        return True, f"Running from source: Update downloaded to {source_exe}. You can run the executable directly."

