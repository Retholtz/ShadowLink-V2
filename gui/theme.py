"""
Windows 11 theme detection, real-time WM_SETTINGCHANGE listener,
and Fluent Design QSS stylesheets for Light and Dark mode.
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import winreg
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

logger = logging.getLogger("ShadowLink.Theme")

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
WM_SETTINGCHANGE = 0x001A


def is_windows_dark_mode() -> bool:
    """Queries Windows Personalize registry key to check if Dark Mode is active."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0
    except Exception as e:
        logger.warning(f"Could not read AppsUseLightTheme registry key: {e}")
        return True  # Default to Dark Mode on modern Windows


class ThemeChangeNotifier(QObject):
    theme_changed = Signal(bool)  # Emits is_dark: bool


class Win32ThemeEventFilter(QAbstractNativeEventFilter):
    """
    Native Win32 event filter listening for WM_SETTINGCHANGE messages
    dispatched whenever the user switches Windows 11 personalization or theme.
    """

    def __init__(self, notifier: ThemeChangeNotifier) -> None:
        super().__init__()
        self.notifier = notifier
        self._last_state: Optional[bool] = None

    def nativeEventFilter(self, event_type: bytes, message: int) -> tuple[bool, int]:
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_SETTINGCHANGE:
                current_dark = is_windows_dark_mode()
                if current_dark != self._last_state:
                    self._last_state = current_dark
                    logger.info(f"Windows 11 theme changed -> Dark Mode: {current_dark}")
                    self.notifier.theme_changed.emit(current_dark)
        return False, 0


def get_fluent_stylesheet(is_dark: bool) -> str:
    """Returns a modern Windows 11 Fluent Design stylesheet in QSS."""
    if is_dark:
        bg_canvas = "#202020"
        bg_card = "#2b2b2b"
        bg_card_secondary = "#323232"
        border_color = "#3d3d3d"
        border_subtle = "#363636"
        text_primary = "#ffffff"
        text_secondary = "#a0a0a0"
        accent_color = "#0078d4"
        accent_hover = "#1084d8"
        accent_pressed = "#006cc1"
        btn_bg = "#343434"
        btn_hover = "#3e3e3e"
        btn_pressed = "#2c2c2c"
        input_bg = "#2f2f2f"
        tab_bg = "#262626"
        tab_selected = "#2b2b2b"
        scrollbar_thumb = "#4f4f4f"
        scrollbar_thumb_hover = "#636363"
    else:
        bg_canvas = "#f3f3f3"
        bg_card = "#ffffff"
        bg_card_secondary = "#f9f9f9"
        border_color = "#e5e5e5"
        border_subtle = "#eeeeee"
        text_primary = "#181818"
        text_secondary = "#616161"
        accent_color = "#0067c0"
        accent_hover = "#187ad3"
        accent_pressed = "#005da6"
        btn_bg = "#fbfbfb"
        btn_hover = "#f5f5f5"
        btn_pressed = "#eaeaea"
        input_bg = "#ffffff"
        tab_bg = "#ececec"
        tab_selected = "#ffffff"
        scrollbar_thumb = "#c4c4c4"
        scrollbar_thumb_hover = "#a6a6a6"

    return f"""
    QWidget {{
        font-family: 'Segoe UI', 'Segoe UI Variable Text', sans-serif;
        font-size: 13px;
        color: {text_primary};
    }}

    QMainWindow, QDialog, #centralWidget {{
        background-color: {bg_canvas};
    }}

    QLabel, QCheckBox, QRadioButton {{
        background-color: transparent;
    }}

    /* Card Panels */
    QFrame[frameShape="1"], QFrame#cardPanel {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 8px;
    }}

    QGroupBox {{
        font-weight: 600;
        font-size: 13px;
        border: 1px solid {border_color};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 14px;
        padding-bottom: 8px;
        background-color: {bg_card};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: {text_primary};
        font-weight: bold;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {btn_bg};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 5px 14px;
        font-weight: 500;
        min-height: 20px;
    }}

    QPushButton:hover {{
        background-color: {btn_hover};
        border-color: {accent_color};
    }}

    QPushButton:pressed {{
        background-color: {btn_pressed};
    }}

    QPushButton:disabled {{
        color: {text_secondary};
        background-color: {bg_canvas};
        border-color: {border_subtle};
    }}

    QPushButton#accentButton {{
        background-color: {accent_color};
        color: #ffffff;
        border: 1px solid {accent_hover};
        font-weight: 600;
    }}

    QPushButton#accentButton:hover {{
        background-color: {accent_hover};
    }}

    QPushButton#accentButton:pressed {{
        background-color: {accent_pressed};
    }}

    QPushButton#dangerButton {{
        color: #ff5252;
    }}

    QPushButton#dangerButton:hover {{
        background-color: #3b2222;
        border-color: #ff5252;
    }}

    /* Toggle Buttons */
    QToolButton {{
        background-color: {btn_bg};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 4px 10px;
    }}

    QToolButton:hover {{
        background-color: {btn_hover};
    }}

    /* Input Fields */
    QLineEdit, QPlainTextEdit, QTextEdit {{
        background-color: {input_bg};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {accent_color};
        selection-color: #ffffff;
    }}

    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 2px solid {accent_color};
    }}

    /* Combo Boxes */
    QComboBox {{
        background-color: {input_bg};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 4px 10px 4px 8px;
        min-height: 22px;
    }}

    QComboBox:hover {{
        border-color: {accent_color};
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left-width: 0px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {accent_color};
        selection-color: #ffffff;
    }}

    /* Spin Boxes */
    QSpinBox {{
        background-color: {input_bg};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 4px 8px;
    }}

    /* Check Boxes */
    QCheckBox {{
        spacing: 6px;
        font-weight: 500;
    }}

    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border: 1px solid {border_color};
        border-radius: 4px;
        background-color: {input_bg};
    }}

    QCheckBox::indicator:hover {{
        border-color: {accent_color};
    }}

    QCheckBox::indicator:checked {{
        background-color: {accent_color};
        border-color: {accent_color};
        image: none;
    }}

    /* Tab Widget & Tabs */
    QTabWidget::pane {{
        border: 1px solid {border_color};
        border-radius: 8px;
        background-color: {bg_card};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: {tab_bg};
        color: {text_secondary};
        border: 1px solid {border_color};
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 8px 18px;
        margin-right: 3px;
        font-weight: 600;
    }}

    QTabBar::tab:hover {{
        background-color: {btn_hover};
        color: {text_primary};
    }}

    QTabBar::tab:selected {{
        background-color: {tab_selected};
        color: {accent_color};
        border-bottom-color: {tab_selected};
    }}

    /* Sub/Nested Tab Bar (Left side) */
    QTabBar[shape="2"]::tab {{
        border-top-left-radius: 6px;
        border-bottom-left-radius: 6px;
        border-top-right-radius: 0px;
        border-bottom-right-radius: 0px;
        padding: 10px 14px;
        margin-bottom: 3px;
    }}

    /* Scroll Area */
    QScrollArea, QScrollArea > QWidget > QWidget {{
        border: none;
        background: transparent;
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background: {scrollbar_thumb};
        min-height: 24px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {scrollbar_thumb_hover};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0px;
    }}

    QScrollBar::handle:horizontal {{
        background: {scrollbar_thumb};
        min-width: 24px;
        border-radius: 4px;
    }}

    /* Tooltips */
    QToolTip {{
        background-color: {bg_card};
        color: {text_primary};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}

    /* Status Bar */
    QStatusBar {{
        background-color: {bg_canvas};
        border-top: 1px solid {border_color};
        color: {text_secondary};
    }}
    """

