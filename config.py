"""
Configuration and Profile persistence for ShadowLink.
Handles saving and loading profiles to/from JSON, managing global configuration,
importing legacy .properties profiles, and automatic process-based profile switching.
"""

from __future__ import annotations
import ctypes
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from models import LayerConfig, PaddleBind, Profile

logger = logging.getLogger("ShadowLink.Config")

APP_VERSION = "1.1"
GITHUB_REPO = "Retholtz/ShadowLink-V2"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

DEFAULT_DATA_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "ShadowLink"
LOCAL_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Resolves the absolute path to a resource, working seamlessly both
    in regular development mode and inside PyInstaller frozen packages (onefile & onedir).
    """
    rel = Path(relative_path)
    if getattr(sys, "frozen", False):
        # 1. Check PyInstaller _MEIPASS (onefile or onedir _internal)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / rel
            if candidate.exists():
                return candidate
        # 2. Check next to the executable
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / rel
        if candidate.exists():
            return candidate
        # 3. Check inside _internal subdirectory
        internal_candidate = exe_dir / "_internal" / rel
        if internal_candidate.exists():
            return internal_candidate

    # Development mode: check project root
    project_root = Path(__file__).resolve().parent
    candidate = project_root / rel
    if candidate.exists():
        return candidate

    ref_candidate = project_root / "reference_kotlin" / rel
    if ref_candidate.exists():
        return ref_candidate

    return candidate


def get_app_icon():
    """
    Returns a QIcon containing both icon.ico and icon.png for crisp rendering across resolutions,
    with graceful fallback to a generated high-DPI accent icon if asset files are absent.
    """
    from PySide6.QtGui import QIcon
    ico_path = get_resource_path("icon.ico")
    png_path = get_resource_path("icon.png")

    icon = QIcon()
    if ico_path.exists():
        icon.addFile(str(ico_path))
    if png_path.exists():
        icon.addFile(str(png_path))

    if icon.isNull():
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#0078d4"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(4, 4, 56, 56, 16, 16)
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        p.drawText(pix.rect(), Qt.AlignCenter, "SL")
        p.end()
        icon = QIcon(pix)

    return icon


def get_profiles_directory() -> Path:
    """Returns the primary profiles directory, creating it if needed."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        portable_profiles = exe_dir / "profiles"
        if not portable_profiles.exists():
            portable_profiles.mkdir(parents=True, exist_ok=True)
            # Seed from bundled profiles if available
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                bundled = Path(meipass) / "profiles"
                if bundled.exists():
                    import shutil
                    for f in bundled.glob("*.json"):
                        dest = portable_profiles / f.name
                        if not dest.exists():
                            shutil.copy2(f, dest)
        return portable_profiles

    if not LOCAL_PROFILES_DIR.exists():
        LOCAL_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_PROFILES_DIR


def get_global_config_path() -> Path:
    """Returns the path to global config.json."""
    return get_profiles_directory().parent / "config.json"


# --- JSON PROFILE PERSISTENCE ---

def save_profile(profile: Profile, target_path: Optional[Path] = None) -> Path:
    """Save a profile to a JSON file."""
    if target_path is None:
        target_path = get_profiles_directory() / f"{profile.name}.json"

    data = profile.to_dict()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved profile '{profile.name}' to {target_path}")
    return target_path


def load_profile(file_path: Path) -> Profile:
    """Load a profile from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Profile.from_dict(data)


def load_all_profiles(directory: Optional[Path] = None) -> list[Profile]:
    """
    Load all .json profiles in the directory.
    If none exist, creates and saves a Default profile.
    """
    if directory is None:
        directory = get_profiles_directory()

    profiles: list[Profile] = []
    if directory.exists():
        for file in directory.glob("*.json"):
            try:
                p = load_profile(file)
                profiles.append(p)
            except Exception as e:
                logger.error(f"Failed to load profile '{file.name}': {e}")

    if not profiles:
        default_profile = Profile(name="Default")
        save_profile(default_profile, directory / "Default.json")
        profiles.append(default_profile)
        logger.info("No profiles found. Created default profile.")

    return profiles


# --- LEGACY .properties IMPORT ---

def import_properties_profile(file_path: Path) -> Profile:
    """
    Imports legacy Kotlin-era .properties profile into a Profile dataclass.
    """
    props: dict[str, str] = {}
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                props[k.strip()] = v.strip()

    p = Profile(name=file_path.stem)
    p.target_process = props.get("TARGET_PROCESS", "")
    p.toggle_button1 = props.get("TOGGLE_BTN_1", "None")
    p.toggle_button2 = props.get("TOGGLE_BTN_2", "None")
    p.combo_buffer_ms = int(props.get("COMBO_BUFFER_MS", "30") or "30")

    def load_bind(prefix: str, b: PaddleBind, default_key: Optional[str] = None) -> None:
        if f"{prefix}_EN" in props:
            b.enabled = props[f"{prefix}_EN"].lower() == "true"
        if f"{prefix}_MAC" in props:
            b.is_macro = props[f"{prefix}_MAC"].lower() == "true"
        if f"{prefix}_REP" in props:
            b.repeat_macro = props[f"{prefix}_REP"].lower() == "true"
        if f"{prefix}_STP" in props:
            b.step_through = props[f"{prefix}_STP"].lower() == "true"
        if f"{prefix}_TXT" in props:
            b.macro_text = props[f"{prefix}_TXT"]
        if f"{prefix}_KEY" in props:
            k = props[f"{prefix}_KEY"]
            if default_key and k == "A":
                b.key_char = default_key
            else:
                b.key_char = k
        if f"{prefix}_SH" in props:
            b.shift = props[f"{prefix}_SH"].lower() == "true"
        if f"{prefix}_CT" in props:
            b.ctrl = props[f"{prefix}_CT"].lower() == "true"
        if f"{prefix}_AL" in props:
            b.alt = props[f"{prefix}_AL"].lower() == "true"
        if f"{prefix}_WI" in props:
            b.win = props[f"{prefix}_WI"].lower() == "true"

    for i in range(5):
        suffix = "" if i == 0 else f"_L{i+1}"
        layer = p.layers[i]
        layer.name = props.get(f"LAYER{i+1}_NAME", f"Layer {i+1}")
        layer.enabled = props.get(f"LAYER{i+1}_EN", "true" if i == 0 else "false").lower() == "true"

        load_bind(f"M1{suffix}", layer.m1)
        load_bind(f"M2{suffix}", layer.m2)
        load_bind(f"M3{suffix}", layer.m3)
        load_bind(f"M4{suffix}", layer.m4)
        load_bind(f"CMD{suffix}", layer.cmd)
        load_bind(f"LIB{suffix}", layer.lib)

        load_bind(f"LB{suffix}", layer.lb, "Xbox_LB")
        load_bind(f"RB{suffix}", layer.rb, "Xbox_RB")
        load_bind(f"LT{suffix}", layer.lt, "Xbox_LT")
        load_bind(f"RT{suffix}", layer.rt, "Xbox_RT")
        load_bind(f"A{suffix}", layer.a, "Xbox_A")
        load_bind(f"B{suffix}", layer.b, "Xbox_B")
        load_bind(f"X{suffix}", layer.x, "Xbox_X")
        load_bind(f"Y{suffix}", layer.y, "Xbox_Y")
        load_bind(f"L3{suffix}", layer.l3, "Xbox_L3")
        load_bind(f"R3{suffix}", layer.r3, "Xbox_R3")
        load_bind(f"DUP{suffix}", layer.d_up, "Xbox_DUp")
        load_bind(f"DDOWN{suffix}", layer.d_down, "Xbox_DDown")
        load_bind(f"DLEFT{suffix}", layer.d_left, "Xbox_DLeft")
        load_bind(f"DRIGHT{suffix}", layer.d_right, "Xbox_DRight")

        load_bind(f"M1M2{suffix}", layer.m1_m2)
        load_bind(f"M1M3{suffix}", layer.m1_m3)
        load_bind(f"M1M4{suffix}", layer.m1_m4)
        load_bind(f"M2M3{suffix}", layer.m2_m3)
        load_bind(f"M2M4{suffix}", layer.m2_m4)
        load_bind(f"M3M4{suffix}", layer.m3_m4)
        load_bind(f"CMDLIB{suffix}", layer.cmd_lib)

    logger.info(f"Imported legacy profile from '{file_path.name}'")
    return p


# --- GLOBAL APP CONFIGURATION ---

DEFAULT_GLOBAL_CONFIG = {
    "active_profile": "Default",
    "auto_switch": True,
    "start_minimized": False,
    "load_on_startup": False,
    "dark_mode": True,
    "osd_position": "Bottom Right",
    "scan_interval_ms": 5000,
}


def load_global_config(target_path: Optional[Path] = None) -> dict:
    if target_path is None:
        target_path = get_global_config_path()

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**DEFAULT_GLOBAL_CONFIG, **cfg}
        except Exception as e:
            logger.error(f"Error loading global config: {e}")

    return dict(DEFAULT_GLOBAL_CONFIG)


def save_global_config(config: dict, target_path: Optional[Path] = None) -> None:
    if target_path is None:
        target_path = get_global_config_path()

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Saved global configuration to {target_path}")


# --- PROCESS WATCHDOG LOGIC ---

def get_foreground_process_name() -> str:
    """
    Returns the executable name of the active foreground window.
    Returns empty string if no window or on query failure.
    """
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return ""

    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return ""

    # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buffer))
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

    return ""


class AutoSwitchWatchdog:
    """
    Background worker that monitors the active foreground process
    and switches profiles when a matching target_process is detected.
    """

    def __init__(
        self,
        profiles_provider: Callable[[], list[Profile]],
        active_profile_provider: Callable[[], Profile],
        switch_profile_callback: Callable[[Profile], None],
        poll_interval_sec: float = 2.0,
    ) -> None:
        self.profiles_provider = profiles_provider
        self.active_profile_provider = active_profile_provider
        self.switch_profile_callback = switch_profile_callback
        self.poll_interval_sec = poll_interval_sec
        self.enabled = True
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ShadowLink-AutoSwitchWatchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run_loop(self) -> None:
        while self._running:
            try:
                if self.enabled:
                    proc_name = get_foreground_process_name().lower()
                    if proc_name:
                        current = self.active_profile_provider()
                        all_profiles = self.profiles_provider()
                        for p in all_profiles:
                            target = p.target_process.strip().lower()
                            if target and target == proc_name:
                                if p.name != current.name:
                                    logger.info(f"Auto-switching profile to '{p.name}' for process '{proc_name}'")
                                    self.switch_profile_callback(p)
                                break
            except Exception as e:
                logger.error(f"Error in AutoSwitchWatchdog: {e}")

            time.sleep(self.poll_interval_sec)


def get_desktop_directory() -> Path:
    """Returns the user's Desktop directory, resolving OneDrive redirection if present."""
    try:
        import ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY = 0x0010
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
            desktop_path = Path(buf.value)
            if desktop_path.exists():
                return desktop_path
    except Exception as e:
        logger.debug(f"SHGetFolderPath failed: {e}")

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        expanded = Path(os.path.expandvars(val))
        if expanded.exists():
            return expanded
    except Exception as e:
        logger.debug(f"Registry desktop lookup failed: {e}")

    return Path.home() / "Desktop"


def create_desktop_shortcut(target_name: str = "ShadowLink.lnk") -> Path:
    """
    Creates or updates a Windows desktop shortcut (.lnk) for ShadowLink.
    Works seamlessly both when running from source (points to pythonw.exe main.py)
    and when frozen with PyInstaller (points directly to ShadowLink.exe).
    """
    desktop_dir = get_desktop_directory()
    shortcut_path = desktop_dir / target_name

    icon_file = get_resource_path("icon.ico")

    if getattr(sys, "frozen", False):
        target_exe = Path(sys.executable)
        working_dir = target_exe.parent
        arguments = ""
        icon_loc = f"{str(target_exe)},0"
    else:
        project_root = Path(__file__).resolve().parent
        main_py = project_root / "main.py"
        working_dir = project_root
        arguments = f'"{str(main_py)}"'

        # Locate pythonw.exe in venv or current environment
        venv_pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
        if venv_pythonw.exists():
            target_exe = venv_pythonw
        else:
            target_exe = Path(sys.executable).parent / "pythonw.exe"
            if not target_exe.exists():
                target_exe = Path(sys.executable)

        icon_loc = f"{str(icon_file)},0" if icon_file.exists() else f"{str(target_exe)},0"

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$s = $ws.CreateShortcut('{str(shortcut_path)}')\n"
        f"$s.TargetPath = '{str(target_exe)}'\n"
        f"$s.Arguments = '{arguments}'\n"
        f"$s.WorkingDirectory = '{str(working_dir)}'\n"
        f"$s.IconLocation = '{icon_loc}'\n"
        "$s.Description = 'ShadowLink - ASUS ROG Controller Remapper'\n"
        "$s.Save()\n"
    )

    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info(f"Created desktop shortcut at: {shortcut_path}")
    return shortcut_path

