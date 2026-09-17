"""
Comprehensive unit test suite for ShadowLink Python backend.
Tests models, keymap, macros, hardware logic, and config persistence.
"""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

import config
import hardware
import keymap
import macros
import models


class TestModels(unittest.TestCase):
    def test_paddle_bind_roundtrip(self):
        bind = models.PaddleBind(
            enabled=True,
            is_macro=True,
            repeat_macro=True,
            step_through=False,
            macro_text="100ms, A down, 50ms, A up",
            key_char="B",
            shift=True,
            ctrl=False,
            alt=True,
            win=False,
        )
        d = bind.to_dict()
        bind2 = models.PaddleBind.from_dict(d)
        self.assertEqual(bind, bind2)

    def test_profile_roundtrip(self):
        profile = models.Profile(
            name="Apex Legends",
            target_process="r5apex.exe",
            toggle_button1="M1",
            toggle_button2="M2",
            combo_buffer_ms=45,
        )
        profile.layers[0].name = "Movement"
        profile.layers[0].m1.key_char = "Space"
        profile.layers[1].enabled = True
        profile.layers[1].name = "Looting"

        d = profile.to_dict()
        profile2 = models.Profile.from_dict(d)

        self.assertEqual(profile.name, profile2.name)
        self.assertEqual(profile.target_process, profile2.target_process)
        self.assertEqual(profile.toggle_button1, profile2.toggle_button1)
        self.assertEqual(profile.combo_buffer_ms, profile2.combo_buffer_ms)
        self.assertEqual(profile.layers[0].name, profile2.layers[0].name)
        self.assertEqual(profile.layers[0].m1.key_char, profile2.layers[0].m1.key_char)
        self.assertTrue(profile2.layers[1].enabled)

    def test_button_state_cancel(self):
        state = models.ButtonState()
        state.pressed = True
        state.cancel_and_release()
        self.assertFalse(state.pressed)
        self.assertIsNone(state.active_bind)


class TestKeyMap(unittest.TestCase):
    def test_supported_keys_mapped(self):
        for key in ["A", "Z", "0", "9", "Space", "Enter", "ESC", "F1", "F24", "NumPad Enter"]:
            info = keymap.get_key_info(key)
            self.assertIsNotNone(info, f"Key '{key}' should be mapped in keymap")
            self.assertIsNotNone(info.scan_code or info.vk_code, f"Key '{key}' must have scan code or VK code")

    def test_scan_codes(self):
        info_a = keymap.get_key_info("A")
        self.assertIsNotNone(info_a)
        self.assertEqual(info_a.scan_code, 0x1E)
        self.assertEqual(info_a.vk_code, 0x41)

        info_esc = keymap.get_key_info("ESC")
        self.assertIsNotNone(info_esc)
        self.assertEqual(info_esc.scan_code, 0x01)

        info_np_enter = keymap.get_key_info("NumPad Enter")
        self.assertIsNotNone(info_np_enter)
        self.assertTrue(info_np_enter.is_extended)

    def test_mouse_keys(self):
        info_lc = keymap.get_key_info("LClick")
        self.assertIsNotNone(info_lc)
        self.assertTrue(info_lc.is_mouse)
        self.assertEqual(info_lc.mouse_event_down, keymap.MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(info_lc.mouse_event_up, keymap.MOUSEEVENTF_LEFTUP)


class TestMacros(unittest.TestCase):
    def test_parse_macro_text_delimiters(self):
        text = "A, B; C, D"
        tokens = macros.parse_macro_text(text)
        self.assertEqual(tokens, ["A", "B", "C", "D"])

    def test_compound_delay_action(self):
        text = "350ms. MClick; 50ms Space"
        tokens = macros.parse_macro_text(text)
        self.assertEqual(tokens, ["350ms", "MClick", "50ms", "Space"])

    def test_is_delay_token(self):
        self.assertTrue(macros.is_delay_token("100ms"))
        self.assertTrue(macros.is_delay_token("1.5s"))
        self.assertTrue(macros.is_delay_token("50ms~150ms"))
        self.assertFalse(macros.is_delay_token("A"))
        self.assertFalse(macros.is_delay_token("Space down"))
        self.assertFalse(macros.is_delay_token("MClick up"))

    def test_parse_delay_seconds(self):
        self.assertAlmostEqual(macros._parse_delay_seconds("500ms"), 0.5)
        self.assertAlmostEqual(macros._parse_delay_seconds("2s"), 2.0)
        rng = macros._parse_delay_seconds("100ms~200ms")
        self.assertIsNotNone(rng)
        self.assertTrue(0.1 <= rng <= 0.2)


class TestHardwareLogic(unittest.TestCase):
    def test_layer_cycling(self):
        profile = models.Profile()
        profile.layers[0].enabled = True
        profile.layers[1].enabled = False
        profile.layers[2].enabled = True
        profile.layers[3].enabled = False
        profile.layers[4].enabled = False

        mgr = hardware.ControllerManager(profile)
        self.assertEqual(mgr.active_layer_index, 0)
        mgr.cycle_layer()
        self.assertEqual(mgr.active_layer_index, 2)
        mgr.cycle_layer()
        self.assertEqual(mgr.active_layer_index, 0)

    def test_report_decoding_normal_mode(self):
        # Packet: Report 0xB3, normal mode (data[3] != 2)
        # s1: data[8]==1, s2: data[6]==1, s3: data[5]==1, s4: data[7]==1
        packet = [0] * 16
        packet[0] = 0xB3
        packet[3] = 0  # Not alt mode
        packet[5] = 1  # s3 (M3)
        packet[6] = 1  # s2 (M2)
        packet[7] = 0  # s4 (M4)
        packet[8] = 1  # s1 (M1)

        is_alt = packet[3] == 2
        s1 = (not is_alt) and packet[8] == 1
        s2 = (not is_alt) and packet[6] == 1
        s3 = (not is_alt) and packet[5] == 1
        s4 = (not is_alt) and packet[7] == 1

        self.assertTrue(s1)
        self.assertTrue(s2)
        self.assertTrue(s3)
        self.assertFalse(s4)

    def test_report_decoding_alt_mode(self):
        # Alt mode: data[3] == 2
        # sCmd: data[5]==1, sLib: data[6]==1
        packet = [0] * 16
        packet[0] = 0xB3
        packet[3] = 2  # Alt mode
        packet[5] = 1  # Command
        packet[6] = 0  # Library

        is_alt = packet[3] == 2
        s1 = (not is_alt) and packet[8] == 1
        s_cmd = is_alt and packet[5] == 1
        s_lib = is_alt and packet[6] == 1

        self.assertFalse(s1)
        self.assertTrue(s_cmd)
        self.assertFalse(s_lib)

    def test_is_valid_paddle_packet(self):
        # Valid normal mode packet (mode 0 or mode != 2)
        normal_pkt = [0xB3, 0, 0, 0, 0, 1, 0, 1, 0] + [0] * 7
        self.assertTrue(hardware.is_valid_paddle_packet(normal_pkt))

        # Valid normal mode packet with non-zero header bytes from firmware (seq counter, flags)
        normal_pkt_headers = [0xB3, 0x10, 0x02, 1, 0x05, 0, 1, 0, 0] + [0] * 7
        self.assertTrue(hardware.is_valid_paddle_packet(normal_pkt_headers))

        # Valid alt mode packet (Command=1, Library=0)
        alt_pkt = [0xB3, 0, 0, 2, 0, 1, 0, 0, 0] + [0] * 7
        self.assertTrue(hardware.is_valid_paddle_packet(alt_pkt))

        # Too short (< 9 bytes)
        self.assertFalse(hardware.is_valid_paddle_packet([0xB3, 0, 0, 0]))

        # Wrong report ID
        self.assertFalse(hardware.is_valid_paddle_packet([0x01, 0, 0, 0, 0, 1, 0, 1, 0]))

        # Aura RGB / command packet where data[5..8] are not discrete 0 or 1
        aura_pkt1 = [0xB3, 0x51, 0x00, 0x00, 0x00, 0x05, 0x01, 0x00, 0x00]
        self.assertFalse(hardware.is_valid_paddle_packet(aura_pkt1))

        aura_pkt2 = [0xB3, 0x52, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00]
        self.assertFalse(hardware.is_valid_paddle_packet(aura_pkt2))

        # Empty data
        self.assertFalse(hardware.is_valid_paddle_packet([]))

    def test_send_key_scancode_and_vk(self):
        # Verify that SendInput passes both wVk and wScan for full application compatibility
        captured_inputs = []
        orig_send = keymap._SendInput

        def mock_send(n, p_inp, sz):
            inp = getattr(p_inp, '_obj', p_inp)
            captured_inputs.append((inp.union.ki.wVk, inp.union.ki.wScan, inp.union.ki.dwFlags))
            return 1

        try:
            keymap._SendInput = mock_send
            # "Tab" has vk_code 0x09 and scan_code 0x0F
            keymap.send_key_down("Tab")
            self.assertEqual(len(captured_inputs), 1)
            vk, scan, flags = captured_inputs[0]
            self.assertEqual(vk, 0x09, "wVk must be preserved alongside scancode")
            self.assertEqual(scan, 0x0F)
            self.assertTrue(flags & keymap.KEYEVENTF_SCANCODE)

            keymap.send_key_up("Tab")
            self.assertEqual(len(captured_inputs), 2)
            vk_up, scan_up, flags_up = captured_inputs[1]
            self.assertEqual(vk_up, 0x09, "wVk must be preserved on key up")
            self.assertEqual(scan_up, 0x0F)
            self.assertTrue(flags_up & keymap.KEYEVENTF_KEYUP)
        finally:
            keymap._SendInput = orig_send

    def test_disconnect_releases_paddles(self):
        # Verify that if a paddle was pressed and then the controller disconnects / sleeps,
        # all held buttons are immediately released cleanly.
        down_keys = []
        up_keys = []
        orig_down = keymap.send_key_down
        orig_up = keymap.send_key_up

        keymap.send_key_down = lambda k: down_keys.append(k) or True
        keymap.send_key_up = lambda k: up_keys.append(k) or True

        try:
            profile = models.Profile(name="TestDisconnect")
            profile.layers[0].m2.enabled = True
            profile.layers[0].m2.key_char = "Tab"
            profile.combo_buffer_ms = 0

            mgr = hardware.ControllerManager(profile)
            mgr.controller_link_status = hardware.DeviceStatus.CONNECTED

            # Mock HID device
            class MockHid:
                def __init__(self):
                    self.packets = [
                        # First packet: M2 pressed (byte 6 = 1)
                        [0xB3, 0, 0, 0, 0, 0, 1, 0, 0] + [0] * 7
                    ]
                def read(self, size, timeout_ms=0):
                    if self.packets:
                        return self.packets.pop(0)
                    time.sleep(0.01)
                    return []
                def close(self):
                    pass

            mgr._hid_device = MockHid()
            mgr._is_hid_connected = True
            mgr._running = True

            # Run reader loop in a thread
            t = threading.Thread(target=mgr._hid_reader_loop, daemon=True)
            t.start()

            # Wait up to 200ms for M2 down
            deadline = time.time() + 0.25
            while time.time() < deadline:
                if "Tab" in down_keys:
                    break
                time.sleep(0.01)

            self.assertIn("Tab", down_keys, "Tab should have fired on initial packet")

            # Simulate controller turning off / sleeping
            mgr.controller_link_status = hardware.DeviceStatus.DISCONNECTED

            # Wait for release
            deadline = time.time() + 0.25
            while time.time() < deadline:
                if "Tab" in up_keys:
                    break
                time.sleep(0.01)

            mgr._running = False
            t.join(timeout=0.5)

            self.assertIn("Tab", up_keys, "Tab must be released automatically when controller disconnects")
            self.assertFalse(mgr.m2_state.pressed, "m2_state.pressed must be False after release")
        finally:
            keymap.send_key_down = orig_down
            keymap.send_key_up = orig_up


class TestConfig(unittest.TestCase):
    def test_save_and_load_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "TestGame.json"
            p = models.Profile(name="TestGame", target_process="game.exe")
            p.layers[0].m1.key_char = "Q"

            config.save_profile(p, file_path)
            self.assertTrue(file_path.exists())

            loaded = config.load_profile(file_path)
            self.assertEqual(loaded.name, "TestGame")
            self.assertEqual(loaded.target_process, "game.exe")
            self.assertEqual(loaded.layers[0].m1.key_char, "Q")

    def test_import_properties_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prop_file = Path(tmpdir) / "Legacy.properties"
            prop_file.write_text(
                "TARGET_PROCESS=legacy.exe\n"
                "TOGGLE_BTN_1=M1\n"
                "COMBO_BUFFER_MS=50\n"
                "LAYER1_NAME=Default Layer\n"
                "LAYER1_EN=true\n"
                "M1_KEY=F5\n"
                "M1_EN=true\n"
                "M1_SH=true\n"
                "M2_KEY=LClick\n",
                encoding="utf-8"
            )

            p = config.import_properties_profile(prop_file)
            self.assertEqual(p.name, "Legacy")
            self.assertEqual(p.target_process, "legacy.exe")
            self.assertEqual(p.toggle_button1, "M1")
            self.assertEqual(p.combo_buffer_ms, 50)
            self.assertEqual(p.layers[0].name, "Default Layer")
            self.assertEqual(p.layers[0].m1.key_char, "F5")
            self.assertTrue(p.layers[0].m1.shift)
            self.assertEqual(p.layers[0].m2.key_char, "LClick")


if __name__ == "__main__":
    unittest.main()

