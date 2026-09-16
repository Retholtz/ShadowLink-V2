"""
Unit test suite for ShadowLink PySide6 GUI.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication, QLineEdit

# Ensure single QApplication instance
app = QApplication.instance() or QApplication(sys.argv)

import gui.dialogs
import gui.main_window
import gui.osd
import gui.theme
import gui.widgets
import hardware
import models


class TestGuiTheme(unittest.TestCase):
    def test_theme_query(self):
        dark = gui.theme.is_windows_dark_mode()
        self.assertIsInstance(dark, bool)

    def test_fluent_stylesheet(self):
        ss_dark = gui.theme.get_fluent_stylesheet(True)
        ss_light = gui.theme.get_fluent_stylesheet(False)
        self.assertIn("QMainWindow", ss_dark)
        self.assertIn("#0078d4", ss_dark)
        self.assertIn("QMainWindow", ss_light)
        self.assertIn("#0067c0", ss_light)


class TestGuiWidgets(unittest.TestCase):
    def test_status_indicators(self):
        status = gui.widgets.StatusIndicatorsWidget()
        status.update_dongle_status(models.DeviceStatus.CONNECTED, "Dongle connected")
        self.assertEqual(status.dongle_label.text(), "Dongle: Connected")
        status.update_controller_status(models.DeviceStatus.ERROR, "Link timeout")
        self.assertEqual(status.ctrl_label.text(), "Controller: Error")

    def test_paddle_row_widget_sync(self):
        bind = models.PaddleBind(
            enabled=True,
            is_macro=False,
            key_char="Space",
            shift=True,
            ctrl=False,
            alt=False,
            win=False,
        )
        row = gui.widgets.PaddleRowWidget("M1", bind)
        self.assertTrue(row.enabled_cb.isChecked())
        self.assertFalse(row.macro_cb.isChecked())
        self.assertTrue(row.shift_cb.isChecked())
        self.assertEqual(row.key_combo.currentText(), "Space")

        # Switch to macro mode
        row.macro_cb.setChecked(True)
        row.macro_edit.setText("100ms, A down, 50ms, A up")
        row.repeat_cb.setChecked(True)

        saved_bind = row.save_to_bind()
        self.assertTrue(saved_bind.is_macro)
        self.assertTrue(saved_bind.repeat_macro)
        self.assertEqual(saved_bind.macro_text, "100ms, A down, 50ms, A up")

    def test_paddle_row_lockout(self):
        bind = models.PaddleBind()
        row = gui.widgets.PaddleRowWidget("Command", bind)
        self.assertFalse(row.is_reserved)
        self.assertTrue(row.reserved_label.isHidden())

        row.set_reserved(True)
        self.assertTrue(row.is_reserved)
        self.assertFalse(row.reserved_label.isHidden())
        self.assertTrue(row.key_combo.isHidden())


class TestGuiDialogs(unittest.TestCase):
    def test_macro_editor_dialog(self):
        target = QLineEdit("Initial Macro")
        dlg = gui.dialogs.MacroEditorDialog("M1", target)
        dlg.editor.setPlainText("Updated Macro")
        dlg._on_save()
        self.assertEqual(target.text(), "Updated Macro")

    def test_macro_recorder_tokens(self):
        target = QLineEdit()
        dlg = gui.dialogs.MacroRecorderDialog(target)
        dlg._on_token_recorded("Space down")
        self.assertIn("Space down", dlg._tokens)

    def test_active_process_enumeration(self):
        apps = gui.dialogs.ActiveProcessDialog._enumerate_desktop_windows()
        self.assertIsInstance(apps, dict)


class TestMainWindow(unittest.TestCase):
    def test_main_window_init(self):
        p = models.Profile(name="TestGUIProfile")
        mgr = hardware.ControllerManager(p)
        win = gui.main_window.MainWindow(mgr)
        self.assertIsNotNone(win)
        self.assertEqual(win.main_tabs.count(), 6)  # 5 layers + 1 settings
        self.assertEqual(len(win.layer_ui_rows), 5)
        # Check window and system tray icon are loaded
        self.assertFalse(win.windowIcon().isNull())
        self.assertFalse(win.tray_icon.icon().isNull())
        self.assertIsNotNone(win.create_shortcut_btn)


class TestDesktopIntegration(unittest.TestCase):
    def test_desktop_directory(self):
        import config
        desk = config.get_desktop_directory()
        self.assertTrue(desk.exists())

    def test_create_desktop_shortcut(self):
        import config
        # Create a test shortcut in desktop directory
        shortcut = config.create_desktop_shortcut("ShadowLink_Test.lnk")
        self.assertTrue(shortcut.exists())
        self.assertGreater(shortcut.stat().st_size, 0)
        # Clean up test shortcut
        try:
            shortcut.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()

