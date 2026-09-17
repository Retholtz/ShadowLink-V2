"""
ShadowLink Desktop Application Launcher.
Initializes PySide6, installs Windows 11 dynamic theme listener,
starts hardware controller sniffer, and launches the MainWindow.
"""

import ctypes
import logging
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

import config
from hardware import ControllerManager
from gui.main_window import MainWindow
from gui.theme import ThemeChangeNotifier, Win32ThemeEventFilter, get_fluent_stylesheet, is_windows_dark_mode

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ShadowLink.App")


def main() -> None:
    # Set Windows Application User Model ID so the custom icon appears in the Taskbar
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ShadowLink")
    except Exception as e:
        logger.debug(f"Could not set AppUserModelID: {e}")

    # High-DPI scaling is enabled by default in Qt 6
    app = QApplication(sys.argv)
    app.setApplicationName("ShadowLink")
    app.setOrganizationName("Retholtz")
    app.setApplicationVersion(config.APP_VERSION)

    logger.info(f"Starting ShadowLink v{config.APP_VERSION}...")

    # Set icon on the application level
    app_icon = config.get_app_icon()
    app.setWindowIcon(app_icon)

    # Set base font to Segoe UI
    app.setFont(QFont("Segoe UI", 10))

    # Determine initial theme and apply styling
    initial_dark = is_windows_dark_mode()
    app.setStyleSheet(get_fluent_stylesheet(initial_dark))

    # Load initial active profile & global settings
    profiles = config.load_all_profiles()
    global_cfg = config.load_global_config()

    target_name = global_cfg.get("active_profile", "Default")
    active_profile = next((p for p in profiles if p.name.lower() == target_name.lower()), profiles[0])

    # Instantiate and start hardware sniffer manager
    manager = ControllerManager(active_profile)
    manager.start()

    # Create MainWindow
    window = MainWindow(manager)

    # Install native Win32 WM_SETTINGCHANGE event filter for live theme switching
    theme_notifier = ThemeChangeNotifier()
    theme_notifier.theme_changed.connect(window.apply_theme)
    event_filter = Win32ThemeEventFilter(theme_notifier)
    app.installNativeEventFilter(event_filter)

    # Show window unless user requested start minimized
    start_minimized = global_cfg.get("start_minimized", False)
    if not start_minimized:
        window.show()
    else:
        logger.info("Starting ShadowLink minimized to system tray")

    # Clean shutdown on application exit
    exit_code = app.exec()
    manager.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

