"""
Hardware interface for ASUS ROG Raikiri / Raikiri Pro controller.
Captures back paddles (M1-M4, Command, Library) via hidapi (VID 0x0B05, usage page ending in c3, report 0xB3).
Implements microswitch debouncing, combo arbitration, layer switching, and XInput monitoring.
"""

from __future__ import annotations
import ctypes
import logging
import threading
import time
from typing import Callable, Optional

import hid
from models import ButtonState, DeviceStatus, LayerConfig, PaddleBind, Profile
import keymap
import macros

logger = logging.getLogger("ShadowLink.Hardware")

ASUS_VID = 0x0B05
REPORT_ID_PADDLES = 0xB3


# --- XINPUT CTYPES BINDINGS ---

class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


_xinput = None
for _dll in ("xinput1_4", "xinput9_1_0", "xinput1_3"):
    try:
        _xinput = getattr(ctypes.windll, _dll)
        break
    except Exception:
        pass


def find_raikiri_hid_devices() -> list[dict]:
    """Find all connected ASUS ROG HID devices."""
    try:
        devices = hid.enumerate(ASUS_VID, 0)
        return devices or []
    except Exception as e:
        logger.warning(f"Error enumerating HID devices: {e}")
        return []


def is_raikiri_paddle_device(device_info: dict) -> bool:
    """Check if device usage_page ends with 0xC3 (e.g. 0xFFC3)."""
    up = device_info.get("usage_page", 0)
    return (up & 0xFF) == 0xC3 or hex(up).lower().endswith("c3")


def is_valid_paddle_packet(data: list[int] | bytes) -> bool:
    """
    Validates that an incoming HID report is a genuine ROG Raikiri paddle report.
    Rejects malformed packets or multi-byte Aura RGB / firmware data sharing Report ID 0xB3.
    """
    if not data or len(data) < 9:
        return False
    if (data[0] & 0xFF) != REPORT_ID_PADDLES:
        return False
    is_alt_mode = (len(data) > 3 and data[3] == 2)
    if not is_alt_mode:
        # In normal mode, paddle switch bytes (5, 6, 7, 8) must be binary 0 or 1
        if data[5] not in (0, 1) or data[6] not in (0, 1) or data[7] not in (0, 1) or data[8] not in (0, 1):
            return False
    else:
        # In alt mode, Command (5) and Library (6) switches must be binary 0 or 1
        if data[5] not in (0, 1) or data[6] not in (0, 1):
            return False
    return True


class ControllerManager:
    """
    Manages communication with ASUS ROG controller paddles and standard inputs.
    """

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.active_layer_index = 0  # 0-indexed (Layer 1 is index 0)

        # Status tracking
        self.usb_dongle_status = DeviceStatus.DISCONNECTED
        self.usb_dongle_details = "USB Dongle unplugged"
        self.controller_link_status = DeviceStatus.DISCONNECTED
        self.controller_link_details = "Controller turned off or sleeping"

        self.last_hid_data_time = 0.0
        self.last_xinput_data_time = 0.0
        self.last_dongle_seen_time = 0.0
        self.last_connection_error: Optional[str] = None

        # Control lifecycle
        self._running = False
        self._threads: list[threading.Thread] = []

        # HID device handle
        self._hid_device: Optional[hid.device] = None
        self._hid_lock = threading.RLock()
        self._is_hid_connected = False

        # Button states: Paddles & Combos
        self.m1_state = ButtonState()
        self.m2_state = ButtonState()
        self.m3_state = ButtonState()
        self.m4_state = ButtonState()
        self.cmd_state = ButtonState()
        self.lib_state = ButtonState()

        self.m1_m2_state = ButtonState()
        self.m1_m3_state = ButtonState()
        self.m1_m4_state = ButtonState()
        self.m2_m3_state = ButtonState()
        self.m2_m4_state = ButtonState()
        self.m3_m4_state = ButtonState()
        self.cmd_lib_state = ButtonState()

        # Standard button states (14 controls)
        self.std_states = [ButtonState() for _ in range(14)]

        # Callbacks
        self.on_paddle_event: Optional[Callable[[str, bool, bool], None]] = None
        self.on_layer_changed: Optional[Callable[[int, str], None]] = None
        self.on_status_updated: Optional[Callable[[DeviceStatus, str, DeviceStatus, str], None]] = None

    @property
    def current_layer(self) -> LayerConfig:
        if 0 <= self.active_layer_index < len(self.profile.layers):
            return self.profile.layers[self.active_layer_index]
        return self.profile.layers[0]

    def set_profile(self, new_profile: Profile) -> None:
        self._cancel_and_release_all_paddles()
        self.profile = new_profile
        # Reset to first enabled layer
        for idx, layer in enumerate(self.profile.layers):
            if layer.enabled:
                self.set_active_layer(idx)
                break

    def set_active_layer(self, layer_index: int) -> None:
        if 0 <= layer_index < len(self.profile.layers):
            self.active_layer_index = layer_index
            layer_name = self.profile.layers[layer_index].name
            logger.info(f"Active layer set to: {layer_index + 1} ({layer_name})")
            if self.on_layer_changed:
                self.on_layer_changed(layer_index + 1, layer_name)

    def cycle_layer(self) -> None:
        """Cycle to next enabled layer matching Kotlin logic."""
        enabled_indices = [i for i, l in enumerate(self.profile.layers) if l.enabled]
        if not enabled_indices:
            return

        current = self.active_layer_index
        if current in enabled_indices:
            pos = enabled_indices.index(current)
            next_idx = enabled_indices[(pos + 1) % len(enabled_indices)]
        else:
            next_idx = enabled_indices[0]

        self.set_active_layer(next_idx)

    def _update_dongle_status(self, status: DeviceStatus, details: str) -> None:
        if self.usb_dongle_status != status or self.usb_dongle_details != details:
            self.usb_dongle_status = status
            self.usb_dongle_details = details
            logger.info(f"USB Dongle: {status.value} ({details})")
            if self.on_status_updated:
                self.on_status_updated(
                    self.usb_dongle_status, self.usb_dongle_details,
                    self.controller_link_status, self.controller_link_details
                )

    def _update_controller_status(self, status: DeviceStatus, details: str) -> None:
        if self.controller_link_status != status or self.controller_link_details != details:
            self.controller_link_status = status
            self.controller_link_details = details
            logger.info(f"Controller Link: {status.value} ({details})")
            if self.on_status_updated:
                self.on_status_updated(
                    self.usb_dongle_status, self.usb_dongle_details,
                    self.controller_link_status, self.controller_link_details
                )

    def _fire_bind(self, state: ButtonState, bind: PaddleBind) -> None:
        state.fire(
            bind,
            press_action_fn=keymap.press_key_bind,
            macro_exec_fn=macros.execute_macro,
            step_exec_fn=macros.execute_macro_step,
        )

    def _release_bind(self, state: ButtonState) -> None:
        state.release_if_active(release_action_fn=keymap.release_key_bind)

    def _cancel_and_release_all_paddles(self) -> None:
        all_states = [
            self.m1_state, self.m2_state, self.m3_state, self.m4_state,
            self.cmd_state, self.lib_state,
            self.m1_m2_state, self.m1_m3_state, self.m1_m4_state,
            self.m2_m3_state, self.m2_m4_state, self.m3_m4_state,
            self.cmd_lib_state,
        ]
        for s in all_states:
            s.cancel_and_release(release_action_fn=keymap.release_key_bind)

    # --- MAIN SNIFFER THREADS ---

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        t_hid = threading.Thread(target=self._hid_reader_loop, name="ShadowLink-HID-Reader", daemon=True)
        t_xinput = threading.Thread(target=self._xinput_reader_loop, name="ShadowLink-XInput-Reader", daemon=True)
        t_watchdog = threading.Thread(target=self._watchdog_loop, name="ShadowLink-Watchdog", daemon=True)

        self._threads = [t_hid, t_xinput, t_watchdog]
        for t in self._threads:
            t.start()

        logger.info("ShadowLink Hardware Controller Manager started")

    def stop(self) -> None:
        self._running = False
        self._cancel_and_release_all_paddles()
        with self._hid_lock:
            if self._hid_device:
                try:
                    self._hid_device.close()
                except Exception:
                    pass
                self._hid_device = None
            self._is_hid_connected = False
        logger.info("ShadowLink Hardware Controller Manager stopped")

    def _hid_reader_loop(self) -> None:
        """Main loop managing HID connection and parsing Report 0xB3."""
        was_toggle_triggered = False

        s1 = s2 = s3 = s4 = s_cmd = s_lib = False
        last_m1_time = last_m2_time = last_m3_time = 0.0
        last_m4_time = last_cmd_time = last_lib_time = 0.0

        prev_debounced_s1 = prev_debounced_s2 = prev_debounced_s3 = False
        prev_debounced_s4 = prev_debounced_cmd = prev_debounced_lib = False

        off_delay_sec = 0.020  # 20ms microswitch debounce on release
        last_valid_paddle_time = 0.0

        while self._running:
            if not self._is_hid_connected or self._hid_device is None:
                time.sleep(0.2)
                continue

            try:
                # Read 64 bytes with 10ms timeout
                data = self._hid_device.read(64, timeout_ms=10)

                now = time.time()
                if data and len(data) > 0:
                    if is_valid_paddle_packet(data):
                        self.last_hid_data_time = now
                        last_valid_paddle_time = now
                        is_alt_mode = (len(data) > 3 and data[3] == 2)

                        s1 = (not is_alt_mode) and (data[8] == 1)
                        s2 = (not is_alt_mode) and (data[6] == 1)
                        s3 = (not is_alt_mode) and (data[5] == 1)
                        s4 = (not is_alt_mode) and (data[7] == 1)

                        s_cmd = is_alt_mode and (data[5] == 1)
                        s_lib = is_alt_mode and (data[6] == 1)
                elif data is None:
                    # Device disconnected
                    logger.warning("HID device disconnected during read")
                    self._cancel_and_release_all_paddles()
                    s1 = s2 = s3 = s4 = s_cmd = s_lib = False
                    prev_debounced_s1 = prev_debounced_s2 = prev_debounced_s3 = False
                    prev_debounced_s4 = prev_debounced_cmd = prev_debounced_lib = False
                    with self._hid_lock:
                        self._is_hid_connected = False
                        if self._hid_device:
                            try:
                                self._hid_device.close()
                            except Exception:
                                pass
                            self._hid_device = None
                    continue

                # Safety release: if a button is marked held but no report received for >3.0s
                # (e.g. controller was abruptly switched off or wireless dropped while held), release it cleanly
                if (s1 or s2 or s3 or s4 or s_cmd or s_lib) and last_valid_paddle_time > 0 and (now - last_valid_paddle_time) > 3.0:
                    s1 = s2 = s3 = s4 = s_cmd = s_lib = False

                # If controller is sleeping or off, ensure inputs do not latch
                if self.controller_link_status == DeviceStatus.DISCONNECTED:
                    if s1 or s2 or s3 or s4 or s_cmd or s_lib:
                        s1 = s2 = s3 = s4 = s_cmd = s_lib = False
                        self._cancel_and_release_all_paddles()

                # Debouncing: high updates timestamp, low holds for off_delay_sec
                if s1: last_m1_time = now
                if s2: last_m2_time = now
                if s3: last_m3_time = now
                if s4: last_m4_time = now
                if s_cmd: last_cmd_time = now
                if s_lib: last_lib_time = now

                debounced_s1 = s1 or ((now - last_m1_time) < off_delay_sec)
                debounced_s2 = s2 or ((now - last_m2_time) < off_delay_sec)
                debounced_s3 = s3 or ((now - last_m3_time) < off_delay_sec)
                debounced_s4 = s4 or ((now - last_m4_time) < off_delay_sec)
                debounced_cmd = s_cmd or ((now - last_cmd_time) < off_delay_sec)
                debounced_lib = s_lib or ((now - last_lib_time) < off_delay_sec)

                # Fire raw paddle change callbacks if listeners registered
                if self.on_paddle_event:
                    if debounced_s1 != prev_debounced_s1:
                        self.on_paddle_event("M1", s1, debounced_s1)
                    if debounced_s2 != prev_debounced_s2:
                        self.on_paddle_event("M2", s2, debounced_s2)
                    if debounced_s3 != prev_debounced_s3:
                        self.on_paddle_event("M3", s3, debounced_s3)
                    if debounced_s4 != prev_debounced_s4:
                        self.on_paddle_event("M4", s4, debounced_s4)
                    if debounced_cmd != prev_debounced_cmd:
                        self.on_paddle_event("Command", s_cmd, debounced_cmd)
                    if debounced_lib != prev_debounced_lib:
                        self.on_paddle_event("Library", s_lib, debounced_lib)

                prev_debounced_s1 = debounced_s1
                prev_debounced_s2 = debounced_s2
                prev_debounced_s3 = debounced_s3
                prev_debounced_s4 = debounced_s4
                prev_debounced_cmd = debounced_cmd
                prev_debounced_lib = debounced_lib

                states = {
                    "M1": debounced_s1,
                    "M2": debounced_s2,
                    "M3": debounced_s3,
                    "M4": debounced_s4,
                    "Command": debounced_cmd,
                    "Library": debounced_lib,
                }

                p = self.profile
                t1 = p.toggle_button1
                t2 = p.toggle_button2

                t1_pressed = states.get(t1, False) if t1 != "None" else False
                t2_pressed = states.get(t2, False) if t2 != "None" else False

                is_single_toggle = (
                    (t1 != "None" and t2 == "None")
                    or (t1 == "None" and t2 != "None")
                    or (t1 != "None" and t1 == t2)
                )

                if not is_single_toggle and t1 != "None" and t2 != "None":
                    is_combo_triggered = t1_pressed and t2_pressed
                elif is_single_toggle:
                    is_combo_triggered = t1_pressed if t1 != "None" else t2_pressed
                else:
                    is_combo_triggered = False

                consumed: set[str] = set()

                if is_combo_triggered and not was_toggle_triggered:
                    was_toggle_triggered = True
                    self._cancel_and_release_all_paddles()
                    self.cycle_layer()
                elif not is_combo_triggered:
                    was_toggle_triggered = False

                if is_combo_triggered:
                    if t1 != "None": consumed.add(t1)
                    if t2 != "None": consumed.add(t2)

                cl = self.current_layer

                # Handle Combos
                def handle_combo(
                    name1: str, sA: bool,
                    name2: str, sB: bool,
                    combo_state: ButtonState,
                    combo_bind: PaddleBind,
                    stateA: ButtonState,
                    stateB: ButtonState,
                ) -> None:
                    if sA and sB and combo_bind.enabled and (name1 not in consumed) and (name2 not in consumed):
                        consumed.add(name1)
                        consumed.add(name2)
                        if not combo_state.pressed:
                            stateA.cancel_pending()
                            stateB.cancel_pending()
                            if stateA.single_action_fired:
                                self._release_bind(stateA)
                            if stateB.single_action_fired:
                                self._release_bind(stateB)
                            stateA.combo_consumed = True
                            stateB.combo_consumed = True

                            combo_state.pressed = True
                            combo_state.single_action_fired = True
                            self._fire_bind(combo_state, combo_bind)
                    else:
                        if combo_state.pressed:
                            self._release_bind(combo_state)
                            combo_state.pressed = False

                handle_combo("M1", debounced_s1, "M2", debounced_s2, self.m1_m2_state, cl.m1_m2, self.m1_state, self.m2_state)
                handle_combo("M1", debounced_s1, "M3", debounced_s3, self.m1_m3_state, cl.m1_m3, self.m1_state, self.m3_state)
                handle_combo("M1", debounced_s1, "M4", debounced_s4, self.m1_m4_state, cl.m1_m4, self.m1_state, self.m4_state)
                handle_combo("M2", debounced_s2, "M3", debounced_s3, self.m2_m3_state, cl.m2_m3, self.m2_state, self.m3_state)
                handle_combo("M2", debounced_s2, "M4", debounced_s4, self.m2_m4_state, cl.m2_m4, self.m2_state, self.m4_state)
                handle_combo("M3", debounced_s3, "M4", debounced_s4, self.m3_m4_state, cl.m3_m4, self.m3_state, self.m4_state)
                handle_combo("Command", debounced_cmd, "Library", debounced_lib, self.cmd_lib_state, cl.cmd_lib, self.cmd_state, self.lib_state)

                # Handle Singles
                def handle_single(name: str, state: bool, bs: ButtonState, bind: PaddleBind) -> None:
                    if name in consumed:
                        if not bs.pressed:
                            bs.pressed = True
                        bs.cancel_pending()
                        if bs.single_action_fired:
                            self._release_bind(bs)
                            bs.single_action_fired = False
                        bs.combo_consumed = True
                        return

                    if state and not bs.pressed:
                        bs.pressed = True
                        bs.single_action_fired = False
                        bs.combo_consumed = False

                        if bind.enabled:
                            buffer_ms = self.profile.combo_buffer_ms
                            if buffer_ms > 0:
                                def on_timer_expire() -> None:
                                    if not bs.combo_consumed:
                                        bs.single_action_fired = True
                                        self._fire_bind(bs, bind)

                                t_task = threading.Timer(buffer_ms / 1000.0, on_timer_expire)
                                bs.pending_timer = t_task
                                t_task.start()
                            else:
                                bs.single_action_fired = True
                                self._fire_bind(bs, bind)

                    elif not state and bs.pressed:
                        bs.cancel_pending()
                        if bind.enabled and not bs.single_action_fired and not bs.combo_consumed:
                            self._fire_bind(bs, bind)
                        self._release_bind(bs)
                        bs.pressed = False
                        bs.combo_consumed = False

                handle_single("M1", debounced_s1, self.m1_state, cl.m1)
                handle_single("M2", debounced_s2, self.m2_state, cl.m2)
                handle_single("M3", debounced_s3, self.m3_state, cl.m3)
                handle_single("M4", debounced_s4, self.m4_state, cl.m4)
                handle_single("Command", debounced_cmd, self.cmd_state, cl.cmd)
                handle_single("Library", debounced_lib, self.lib_state, cl.lib)

            except Exception as e:
                logger.error(f"Error in Raikiri reading loop: {e}", exc_info=True)
                self.last_connection_error = f"HID read error: {e}"
                self._cancel_and_release_all_paddles()
                s1 = s2 = s3 = s4 = s_cmd = s_lib = False
                prev_debounced_s1 = prev_debounced_s2 = prev_debounced_s3 = False
                prev_debounced_s4 = prev_debounced_cmd = prev_debounced_lib = False
                with self._hid_lock:
                    self._is_hid_connected = False
                    if self._hid_device:
                        try:
                            self._hid_device.close()
                        except Exception:
                            pass
                        self._hid_device = None

    def _xinput_reader_loop(self) -> None:
        """Reads standard gamepad controls via XInput for slots 0..3."""
        if _xinput is None:
            logger.warning("XInput DLL not found on system; standard controller buttons disabled")
            return

        x_state = XINPUT_STATE()

        while self._running:
            try:
                w_buttons = 0
                lt_val = 0
                rt_val = 0
                any_connected = False

                for slot in range(4):
                    res = _xinput.XInputGetState(slot, ctypes.byref(x_state))
                    if res == 0:  # ERROR_SUCCESS
                        any_connected = True
                        w_buttons |= (x_state.Gamepad.wButtons & 0xFFFF)
                        lt = x_state.Gamepad.bLeftTrigger & 0xFF
                        rt = x_state.Gamepad.bRightTrigger & 0xFF
                        if lt > lt_val: lt_val = lt
                        if rt > rt_val: rt_val = rt

                if any_connected:
                    self.last_xinput_data_time = time.time()

                    s_lb = (w_buttons & 0x0100) != 0
                    s_rb = (w_buttons & 0x0200) != 0
                    s_lt = lt_val > 128
                    s_rt = rt_val > 128
                    s_a = (w_buttons & 0x1000) != 0
                    s_b = (w_buttons & 0x2000) != 0
                    s_x = (w_buttons & 0x4000) != 0
                    s_y = (w_buttons & 0x8000) != 0
                    s_l3 = (w_buttons & 0x0040) != 0
                    s_r3 = (w_buttons & 0x0080) != 0
                    s_dup = (w_buttons & 0x0001) != 0
                    s_ddown = (w_buttons & 0x0002) != 0
                    s_dleft = (w_buttons & 0x0004) != 0
                    s_dright = (w_buttons & 0x0008) != 0

                    cl = self.current_layer

                    def check_std_state(s: bool, bs: ButtonState, bind: PaddleBind) -> None:
                        if s and not bs.pressed:
                            bs.pressed = True
                            bs.single_action_fired = False
                            if bind.enabled:
                                bs.single_action_fired = True
                                self._fire_bind(bs, bind)
                        elif not s and bs.pressed:
                            bs.cancel_pending()
                            if bind.enabled and not bs.single_action_fired:
                                self._fire_bind(bs, bind)
                            self._release_bind(bs)
                            bs.pressed = False

                    check_std_state(s_lb, self.std_states[0], cl.lb)
                    check_std_state(s_rb, self.std_states[1], cl.rb)
                    check_std_state(s_lt, self.std_states[2], cl.lt)
                    check_std_state(s_rt, self.std_states[3], cl.rt)
                    check_std_state(s_a, self.std_states[4], cl.a)
                    check_std_state(s_b, self.std_states[5], cl.b)
                    check_std_state(s_x, self.std_states[6], cl.x)
                    check_std_state(s_y, self.std_states[7], cl.y)
                    check_std_state(s_l3, self.std_states[8], cl.l3)
                    check_std_state(s_r3, self.std_states[9], cl.r3)
                    check_std_state(s_dup, self.std_states[10], cl.d_up)
                    check_std_state(s_ddown, self.std_states[11], cl.d_down)
                    check_std_state(s_dleft, self.std_states[12], cl.d_left)
                    check_std_state(s_dright, self.std_states[13], cl.d_right)

                else:
                    for bs in self.std_states:
                        if bs.pressed:
                            bs.cancel_pending()
                            self._release_bind(bs)
                            bs.pressed = False

            except Exception as e:
                logger.error(f"Error in XInput reader loop: {e}", exc_info=True)

            time.sleep(0.01)

    def _watchdog_loop(self) -> None:
        """Watchdog monitoring USB Dongle presence and Controller Link heartbeat."""
        while self._running:
            try:
                now = time.time()
                recent_hid = (now - self.last_hid_data_time) < 2.5
                recent_xinput = (now - self.last_xinput_data_time) < 2.5

                # If HID device is not opened, attempt to connect to paddle interface
                if not self._is_hid_connected:
                    devices = find_raikiri_hid_devices()
                    dongle_present = len(devices) > 0

                    if dongle_present:
                        self.last_dongle_seen_time = now
                        self._update_dongle_status(DeviceStatus.CONNECTED, "ROG Raikiri II USB Dongle plugged in")
                        paddle_dev = next((d for d in devices if is_raikiri_paddle_device(d)), None)
                        if paddle_dev and "path" in paddle_dev:
                            try:
                                dev_path = paddle_dev["path"]
                                dev = hid.device()
                                dev.open_path(dev_path)
                                # Drain any queued startup/handshake packets from the device buffer
                                try:
                                    for _ in range(20):
                                        if not dev.read(64, timeout_ms=5):
                                            break
                                except Exception:
                                    pass
                                with self._hid_lock:
                                    self._hid_device = dev
                                    self._is_hid_connected = True
                                    self.last_connection_error = None
                                logger.info(f"ROG Raikiri II HID device successfully opened on path {dev_path}")
                            except Exception as open_err:
                                self.last_connection_error = f"Failed to open Raikiri HID: {open_err}"
                                logger.warning(f"Could not open Raikiri HID device: {open_err}")
                    else:
                        is_dongle_recent = (now - self.last_dongle_seen_time) < 2.5
                        if not is_dongle_recent:
                            self._update_dongle_status(DeviceStatus.DISCONNECTED, "USB Dongle unplugged / not detected")
                else:
                    self.last_dongle_seen_time = now
                    self._update_dongle_status(DeviceStatus.CONNECTED, "ROG Raikiri II USB Dongle plugged in")

                # Controller Link status
                err = self.last_connection_error
                if err is not None and self.usb_dongle_status == DeviceStatus.CONNECTED:
                    if self.controller_link_status != DeviceStatus.ERROR:
                        self._cancel_and_release_all_paddles()
                    self._update_controller_status(DeviceStatus.ERROR, err)
                elif recent_hid or recent_xinput:
                    if recent_hid and recent_xinput:
                        desc = "Connected (Raikiri II HID & XInput active)"
                    elif recent_hid:
                        desc = "Connected (Raikiri II HID active)"
                    else:
                        desc = "Connected (XInput active)"
                    self._update_controller_status(DeviceStatus.CONNECTED, desc)
                else:
                    if self.controller_link_status != DeviceStatus.DISCONNECTED:
                        self._cancel_and_release_all_paddles()
                    if self.usb_dongle_status == DeviceStatus.CONNECTED:
                        self._update_controller_status(DeviceStatus.DISCONNECTED, "Controller turned off or sleeping")
                    else:
                        self._update_controller_status(DeviceStatus.DISCONNECTED, "USB Dongle unplugged")

            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}", exc_info=True)

            time.sleep(1.0)

