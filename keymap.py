"""
Key mapping and Win32/DirectX input injection for ShadowLink.
Maps supported keys and mouse buttons to Win32 Virtual Key codes and DirectX scan codes.
Provides high-performance ctypes SendInput execution for games and desktop apps.
"""

from __future__ import annotations
import ctypes
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import PaddleBind


# --- WIN32 INPUT STRUCTURES & CONSTANTS ---

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUT_UNION),
    ]


_user32 = ctypes.windll.user32
_SendInput = _user32.SendInput
_SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
_SendInput.restype = ctypes.c_uint


@dataclass(frozen=True)
class KeyInfo:
    name: str
    vk_code: Optional[int]
    scan_code: Optional[int]
    is_extended: bool = False
    is_mouse: bool = False
    mouse_event_down: Optional[int] = None
    mouse_event_up: Optional[int] = None


SUPPORTED_KEYS = [
    "LClick", "RClick", "MClick",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace",
    "ESC", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "F13", "F14", "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22", "F23", "F24",
    "Insert", "Home", "Page Up", "Delete", "End", "Page Down",
    "Space", "Enter", "Tab", "Up", "Down", "Left", "Right",
    ",", ".", "/", "\\", ";", "'", "[", "]",
    "NumPad 0", "NumPad 1", "NumPad 2", "NumPad 3", "NumPad 4", "NumPad 5", "NumPad 6", "NumPad 7", "NumPad 8", "NumPad 9",
    "NumPad /", "NumPad *", "NumPad -", "NumPad +", "NumPad .", "NumPad Enter",
    "Shift", "Ctrl", "Alt", "Win"
]


# Raw mappings: name -> (VK, ScanCode, is_extended)
_KEY_DEFINITIONS: dict[str, tuple[Optional[int], Optional[int], bool]] = {
    # Letters (A-Z)
    "A": (0x41, 0x1E, False),
    "B": (0x42, 0x30, False),
    "C": (0x43, 0x2E, False),
    "D": (0x44, 0x20, False),
    "E": (0x45, 0x12, False),
    "F": (0x46, 0x21, False),
    "G": (0x47, 0x22, False),
    "H": (0x48, 0x23, False),
    "I": (0x49, 0x17, False),
    "J": (0x4A, 0x24, False),
    "K": (0x4B, 0x25, False),
    "L": (0x4C, 0x26, False),
    "M": (0x4D, 0x32, False),
    "N": (0x4E, 0x31, False),
    "O": (0x4F, 0x18, False),
    "P": (0x50, 0x19, False),
    "Q": (0x51, 0x10, False),
    "R": (0x52, 0x13, False),
    "S": (0x53, 0x1F, False),
    "T": (0x54, 0x14, False),
    "U": (0x55, 0x16, False),
    "V": (0x56, 0x2F, False),
    "W": (0x57, 0x11, False),
    "X": (0x58, 0x2D, False),
    "Y": (0x59, 0x15, False),
    "Z": (0x5A, 0x2C, False),

    # Numbers row
    "1": (0x31, 0x02, False),
    "2": (0x32, 0x03, False),
    "3": (0x33, 0x04, False),
    "4": (0x34, 0x05, False),
    "5": (0x35, 0x06, False),
    "6": (0x36, 0x07, False),
    "7": (0x37, 0x08, False),
    "8": (0x38, 0x09, False),
    "9": (0x39, 0x0A, False),
    "0": (0x30, 0x0B, False),

    # Punctuation & Symbols
    "`": (0xC0, 0x29, False),
    "-": (0xBD, 0x0C, False),
    "=": (0xBB, 0x0D, False),
    ",": (0xBC, 0x33, False),
    ".": (0xBE, 0x34, False),
    "/": (0xBF, 0x35, False),
    "\\": (0xDC, 0x2B, False),
    ";": (0xBA, 0x27, False),
    "'": (0xDE, 0x28, False),
    "[": (0xDB, 0x1A, False),
    "]": (0xDD, 0x1B, False),

    # Navigation & Control
    "ESC": (0x1B, 0x01, False),
    "Tab": (0x09, 0x0F, False),
    "Space": (0x20, 0x39, False),
    "Enter": (0x0D, 0x1C, False),
    "Backspace": (0x08, 0x0E, False),
    "Insert": (0x2D, 0x52, True),
    "Delete": (0x2E, 0x53, True),
    "Home": (0x24, 0x47, True),
    "End": (0x23, 0x4F, True),
    "Page Up": (0x21, 0x49, True),
    "Page Down": (0x22, 0x51, True),
    "Up": (0x26, 0x48, True),
    "Down": (0x28, 0x50, True),
    "Left": (0x25, 0x4B, True),
    "Right": (0x27, 0x4D, True),

    # Function Keys
    "F1": (0x70, 0x3B, False),
    "F2": (0x71, 0x3C, False),
    "F3": (0x72, 0x3D, False),
    "F4": (0x73, 0x3E, False),
    "F5": (0x74, 0x3F, False),
    "F6": (0x75, 0x40, False),
    "F7": (0x76, 0x41, False),
    "F8": (0x77, 0x42, False),
    "F9": (0x78, 0x43, False),
    "F10": (0x79, 0x44, False),
    "F11": (0x7A, 0x57, False),
    "F12": (0x7B, 0x58, False),
    "F13": (0x7C, 0x64, False),
    "F14": (0x7D, 0x65, False),
    "F15": (0x7E, 0x66, False),
    "F16": (0x7F, 0x67, False),
    "F17": (0x80, 0x68, False),
    "F18": (0x81, 0x69, False),
    "F19": (0x82, 0x6A, False),
    "F20": (0x83, 0x6B, False),
    "F21": (0x84, 0x6C, False),
    "F22": (0x85, 0x6D, False),
    "F23": (0x86, 0x6E, False),
    "F24": (0x87, 0x6F, False),

    # Numpad
    "NumPad 0": (0x60, 0x52, False),
    "NumPad 1": (0x61, 0x4F, False),
    "NumPad 2": (0x62, 0x50, False),
    "NumPad 3": (0x63, 0x51, False),
    "NumPad 4": (0x64, 0x4B, False),
    "NumPad 5": (0x65, 0x4C, False),
    "NumPad 6": (0x66, 0x4D, False),
    "NumPad 7": (0x67, 0x47, False),
    "NumPad 8": (0x68, 0x48, False),
    "NumPad 9": (0x69, 0x49, False),
    "NumPad /": (0x6F, 0x35, True),
    "NumPad *": (0x6A, 0x37, False),
    "NumPad -": (0x6D, 0x4A, False),
    "NumPad +": (0x6B, 0x4E, False),
    "NumPad .": (0x6E, 0x53, False),
    "NumPad Enter": (0x0D, 0x1C, True),

    # Modifiers
    "Shift": (0x10, 0x2A, False),
    "Ctrl": (0x11, 0x1D, False),
    "Alt": (0x12, 0x38, False),
    "Win": (0x5B, 0x5B, True),
}

# Mouse definitions: name -> (down_flag, up_flag, VK)
_MOUSE_DEFINITIONS = {
    "LClick": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 0x01),
    "RClick": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 0x02),
    "MClick": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0x04),
}


KEY_MAP: dict[str, KeyInfo] = {}

for name, (vk, scan, is_ext) in _KEY_DEFINITIONS.items():
    info = KeyInfo(name=name, vk_code=vk, scan_code=scan, is_extended=is_ext, is_mouse=False)
    KEY_MAP[name] = info
    KEY_MAP[name.lower()] = info
    # Common variations
    clean_name = name.lower().replace(" ", "").replace("_", "")
    KEY_MAP[clean_name] = info

for name, (down_flag, up_flag, vk) in _MOUSE_DEFINITIONS.items():
    info = KeyInfo(
        name=name,
        vk_code=vk,
        scan_code=None,
        is_extended=False,
        is_mouse=True,
        mouse_event_down=down_flag,
        mouse_event_up=up_flag,
    )
    KEY_MAP[name] = info
    KEY_MAP[name.lower()] = info
    KEY_MAP[name.lower().replace("click", "")] = info


def get_key_info(key: str) -> Optional[KeyInfo]:
    """Retrieve KeyInfo for key name (case-insensitive with fallback aliases)."""
    if not key:
        return None
    k = key.strip()
    if k in KEY_MAP:
        return KEY_MAP[k]
    k_lower = k.lower()
    if k_lower in KEY_MAP:
        return KEY_MAP[k_lower]
    clean = k_lower.replace(" ", "").replace("_", "")
    return KEY_MAP.get(clean)


def is_mouse_key(key: str) -> bool:
    info = get_key_info(key)
    return info.is_mouse if info else False


# --- WIN32 INPUT SENDERS ---

def send_key_down(key: str) -> bool:
    """Send key down using DirectX hardware scan code with extended flag if needed."""
    info = get_key_info(key)
    if info is None or info.is_mouse:
        return False

    scan = info.scan_code or 0
    vk = info.vk_code or 0
    flags = KEYEVENTF_SCANCODE
    if info.is_extended:
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(
        wVk=vk,
        wScan=scan,
        dwFlags=flags,
        time=0,
        dwExtraInfo=0,
    )
    return _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


def send_key_up(key: str) -> bool:
    """Send key up using DirectX hardware scan code."""
    info = get_key_info(key)
    if info is None or info.is_mouse:
        return False

    scan = info.scan_code or 0
    vk = info.vk_code or 0
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if info.is_extended:
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(
        wVk=vk,
        wScan=scan,
        dwFlags=flags,
        time=0,
        dwExtraInfo=0,
    )
    return _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


def send_key_tap(key: str, delay_ms: float = 50.0) -> None:
    send_key_down(key)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    send_key_up(key)


def send_mouse_down(btn: str) -> bool:
    info = get_key_info(btn)
    if info is None or not info.is_mouse or info.mouse_event_down is None:
        return False

    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(
        dx=0, dy=0, mouseData=0,
        dwFlags=info.mouse_event_down,
        time=0, dwExtraInfo=0,
    )
    return _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


def send_mouse_up(btn: str) -> bool:
    info = get_key_info(btn)
    if info is None or not info.is_mouse or info.mouse_event_up is None:
        return False

    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(
        dx=0, dy=0, mouseData=0,
        dwFlags=info.mouse_event_up,
        time=0, dwExtraInfo=0,
    )
    return _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


def send_mouse_tap(btn: str, delay_ms: float = 50.0) -> None:
    send_mouse_down(btn)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    send_mouse_up(btn)


def send_mouse_abs(x: int, y: int) -> bool:
    """Move mouse pointer to absolute screen coordinates (x, y)."""
    return bool(_user32.SetCursorPos(x, y))


def send_mouse_delta(dx: int, dy: int) -> bool:
    """Move mouse pointer relative to current position by (dx, dy)."""
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(
        dx=dx, dy=dy, mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE,
        time=0, dwExtraInfo=0,
    )
    return _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


# --- PADDLE BIND HIGH-LEVEL INJECTION ---

def press_key_bind(bind: PaddleBind) -> None:
    """
    Press configured modifiers followed by the target key or mouse button.
    Matches Kotlin pressKeyBind logic.
    """
    if not bind.enabled or bind.key_char.startswith("Xbox_"):
        return

    if bind.win:
        send_key_down("Win")
    if bind.shift:
        send_key_down("Shift")
    if bind.ctrl:
        send_key_down("Ctrl")
    if bind.alt:
        send_key_down("Alt")

    info = get_key_info(bind.key_char)
    if info:
        if info.is_mouse:
            send_mouse_down(bind.key_char)
        else:
            send_key_down(bind.key_char)


def release_key_bind(bind: PaddleBind) -> None:
    """
    Release target key or mouse button followed by modifiers in reverse.
    Matches Kotlin releaseKeyBind logic.
    """
    if bind.key_char.startswith("Xbox_"):
        return

    info = get_key_info(bind.key_char)
    if info:
        if info.is_mouse:
            send_mouse_up(bind.key_char)
        else:
            send_key_up(bind.key_char)

    if bind.alt:
        send_key_up("Alt")
    if bind.ctrl:
        send_key_up("Ctrl")
    if bind.shift:
        send_key_up("Shift")
    if bind.win:
        send_key_up("Win")

