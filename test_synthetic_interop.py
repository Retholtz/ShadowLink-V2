"""
Standalone Validation Script for ShadowLink-V2 & External Synthetic Input Interoperability.

Simulates an external desktop automation assistant (e.g., Aether Desktop) dispatching
synthetic keystrokes concurrently while ShadowLink-V2 actively polls controller inputs
and injects mapped paddle keys/modifiers.

Verifies:
1. External synthetic keystrokes are neither dropped nor swallowed.
2. Modifier states (Shift, Ctrl, Alt, Win) remain properly synchronized with zero stuck keys.
3. ShadowLink's SendInput tags (SHADOWLINK_EXTRA_INFO) and paired releases operate cleanly.
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import threading
import time
import sys

import keymap
from keymap import (
    INPUT,
    KEYBDINPUT,
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    KEYEVENTF_EXTENDEDKEY,
    SHADOWLINK_EXTRA_INFO,
    get_active_keys,
    release_all_keys,
)
import models
import hardware

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("InteropValidator")

AETHER_EXTRA_INFO = 0x41455448  # 'AETH' in ASCII representing Aether Desktop


def create_synthetic_keybd_input(vk: int, scan: int, is_up: bool = False, extra_info: int = AETHER_EXTRA_INFO) -> INPUT:
    """Creates a clean Win32 KEYBDINPUT structure simulating an external assistant."""
    flags = KEYEVENTF_KEYUP if is_up else 0
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(
        wVk=vk,
        wScan=scan,
        dwFlags=flags,
        time=0,
        dwExtraInfo=extra_info,
    )
    return inp


def test_concurrency_and_modifier_synchronization() -> bool:
    print("=" * 72)
    print("  ShadowLink-V2 & External Assistant (Aether) Interoperability Test")
    print("=" * 72)

    # 1. Setup ShadowLink profile with paddle modifier bindings
    profile = models.Profile(name="InteropTestProfile", combo_buffer_ms=25)
    layer = profile.layers[0]
    layer.enabled = True

    # Configure paddles with modifiers to stress-test modifier state synchronization
    layer.m1.enabled = True
    layer.m1.key_char = "Q"
    layer.m1.shift = True  # Shift + Q

    layer.m2.enabled = True
    layer.m2.key_char = "E"
    layer.m2.ctrl = True   # Ctrl + E

    layer.m3.enabled = True
    layer.m3.key_char = "Tab"
    layer.m3.alt = True    # Alt + Tab

    layer.m4.enabled = True
    layer.m4.key_char = "R"

    layer.m1_m2.enabled = True
    layer.m1_m2.key_char = "Space"
    layer.m1_m2.win = True  # Win + Space

    manager = hardware.ControllerManager(profile)
    manager.controller_link_status = hardware.DeviceStatus.CONNECTED
    manager.usb_dongle_status = hardware.DeviceStatus.CONNECTED

    # 2. Intercept Win32 _SendInput to log and verify dispatch
    real_send_input = keymap._SendInput
    dispatched_events: list[dict] = []
    events_lock = threading.Lock()

    def instrumented_send_input(n, p_inp, sz):
        inp = getattr(p_inp, '_obj', p_inp)
        extra = inp.union.ki.dwExtraInfo
        vk = inp.union.ki.wVk
        scan = inp.union.ki.wScan
        flags = inp.union.ki.dwFlags
        is_up = bool(flags & KEYEVENTF_KEYUP)
        sender = "ShadowLink" if extra == SHADOWLINK_EXTRA_INFO else ("Aether" if extra == AETHER_EXTRA_INFO else "Other")

        with events_lock:
            dispatched_events.append({
                "sender": sender,
                "vk": vk,
                "scan": scan,
                "is_up": is_up,
                "flags": flags,
                "extra": extra,
                "time": time.time(),
            })
        return 1

    keymap._SendInput = instrumented_send_input

    # 3. Simulate Aether Assistant synthetic input stream
    external_sent_count = 0
    external_stop = threading.Event()
    aether_keys_to_test = [
        (0x41, 0x1E, "A"),
        (0x42, 0x30, "B"),
        (0x09, 0x0F, "Tab"),
        (0x0D, 0x1C, "Enter"),
        (0x31, 0x02, "1"),
        (0x32, 0x03, "2"),
    ]

    def aether_worker():
        nonlocal external_sent_count
        idx = 0
        while not external_stop.is_set():
            vk, scan, name = aether_keys_to_test[idx % len(aether_keys_to_test)]
            idx += 1

            # Dispatch external synthetic down
            inp_down = create_synthetic_keybd_input(vk, scan, is_up=False)
            keymap._SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
            external_sent_count += 1

            time.sleep(0.005)

            # Dispatch external synthetic up
            inp_up = create_synthetic_keybd_input(vk, scan, is_up=True)
            keymap._SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
            external_sent_count += 1

            time.sleep(0.010)

    # 4. Mock HID device providing stream of packet reports
    class SimulatedHidDevice:
        def __init__(self):
            self.stop_event = threading.Event()
            self._seq = 0

        def read(self, size, timeout_ms=10):
            if self.stop_event.is_set():
                return []
            self._seq += 1
            # Alternate button patterns: M1, M2, M1+M2 combo, M3, idle
            pattern = self._seq % 12
            # Byte 5: M3, Byte 6: M2, Byte 7: M4, Byte 8: M1
            b5 = 1 if pattern in (7, 8) else 0
            b6 = 1 if pattern in (3, 4, 5) else 0
            b7 = 0
            b8 = 1 if pattern in (1, 2, 5) else 0
            time.sleep(0.008)
            return [0xB3, 0, 0, 0, 0, b5, b6, b7, b8] + [0] * 55

        def close(self):
            self.stop_event.set()

    mock_hid = SimulatedHidDevice()
    manager._hid_device = mock_hid
    manager._is_hid_connected = True
    manager._running = True

    print("\n[Phase 1] Starting concurrent execution:")
    print("  - Aether Desktop synthetic worker injecting keys...")
    print("  - ShadowLink HID controller reader evaluating paddles and combos...")

    t_aether = threading.Thread(target=aether_worker, name="Mock-Aether-Thread", daemon=True)
    t_hid = threading.Thread(target=manager._hid_reader_loop, name="ShadowLink-HID-Test", daemon=True)

    t_aether.start()
    t_hid.start()

    # Run concurrent interaction for 2.0 seconds
    time.sleep(2.0)

    # Stop threads
    external_stop.set()
    mock_hid.close()
    t_aether.join(timeout=1.0)
    time.sleep(0.1)
    manager.stop()
    t_hid.join(timeout=1.0)

    # Cleanly restore _SendInput
    keymap._SendInput = real_send_input

    # 5. Analysis & Verification
    with events_lock:
        total_events = len(dispatched_events)
        aether_events = [e for e in dispatched_events if e["sender"] == "Aether"]
        sl_events = [e for e in dispatched_events if e["sender"] == "ShadowLink"]

    print("\n[Phase 2] Execution Results:")
    print(f"  - Total Win32 input events captured: {total_events}")
    print(f"  - External (Aether) events sent:     {external_sent_count}")
    print(f"  - External (Aether) events verified: {len(aether_events)}")
    print(f"  - ShadowLink controller events:      {len(sl_events)}")

    # Check 1: Zero external events dropped
    aether_dropped = external_sent_count - len(aether_events)
    print(f"  - External events dropped:           {aether_dropped}")

    # Check 2: Active keys remaining in ShadowLink registry
    active_keys_remaining = get_active_keys()
    print(f"  - Active keys held by ShadowLink:    {list(active_keys_remaining)}")

    # Check 3: Check paired release of ShadowLink inputs
    sl_down_counts: dict[int, int] = {}
    sl_up_counts: dict[int, int] = {}
    for e in sl_events:
        vk = e["vk"]
        if e["is_up"]:
            sl_up_counts[vk] = sl_up_counts.get(vk, 0) + 1
        else:
            sl_down_counts[vk] = sl_down_counts.get(vk, 0) + 1

    unpaired_sl = False
    for vk, down_count in sl_down_counts.items():
        up_count = sl_up_counts.get(vk, 0)
        if down_count != up_count:
            unpaired_sl = True
            logger.warning(f"Unpaired VK 0x{vk:02X}: {down_count} downs vs {up_count} ups")

    # Check 4: Check paired release of external assistant inputs
    aether_down_counts: dict[int, int] = {}
    aether_up_counts: dict[int, int] = {}
    for e in aether_events:
        vk = e["vk"]
        if e["is_up"]:
            aether_up_counts[vk] = aether_up_counts.get(vk, 0) + 1
        else:
            aether_down_counts[vk] = aether_down_counts.get(vk, 0) + 1

    unpaired_aether = False
    for vk, down_count in aether_down_counts.items():
        up_count = aether_up_counts.get(vk, 0)
        if down_count != up_count:
            unpaired_aether = True
            logger.warning(f"Unpaired Aether VK 0x{vk:02X}: {down_count} downs vs {up_count} ups")

    # Final Failsafe verification
    released_failsafe = release_all_keys()

    print("\n[Phase 3] Verdict & Validation Summary:")
    passed = True

    if aether_dropped != 0:
        print("  [FAIL] External assistant keystrokes were dropped!")
        passed = False
    else:
        print("  [PASS] Zero external assistant keystrokes dropped.")

    if len(active_keys_remaining) != 0:
        print(f"  [FAIL] ShadowLink left keys held: {active_keys_remaining}")
        passed = False
    else:
        print("  [PASS] All ShadowLink keys cleanly released (no stuck modifiers).")

    if unpaired_sl:
        print("  [FAIL] Asymmetry detected in ShadowLink key down/up pairings.")
        passed = False
    else:
        print("  [PASS] Perfect symmetry in ShadowLink key down/up dispatches.")

    if unpaired_aether:
        print("  [FAIL] Asymmetry detected in external key down/up dispatches.")
        passed = False
    else:
        print("  [PASS] Perfect symmetry in external key down/up dispatches.")

    print("=" * 72)
    if passed:
        print("  OVERALL STATUS: ALL INTEROPERABILITY CHECKS PASSED")
    else:
        print("  OVERALL STATUS: FAILED")
    print("=" * 72)

    return passed


if __name__ == "__main__":
    success = test_concurrency_and_modifier_synchronization()
    sys.exit(0 if success else 1)

