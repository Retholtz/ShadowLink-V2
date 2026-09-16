"""
Custom UI components for ShadowLink:
- StatusIndicatorsWidget (Dual LED Dongle and Controller link monitor)
- CardPanel (Windows 11 rounded card container)
- PaddleRowWidget (Complete paddle binding row with Single Key and Macro modes)
"""

from __future__ import annotations
import logging
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from keymap import SUPPORTED_KEYS
from models import DeviceStatus, PaddleBind

logger = logging.getLogger("ShadowLink.Widgets")


class LedIndicator(QWidget):
    """Circular LED light indicator with specular highlight and outer glow."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._color = QColor(220, 53, 69)  # Default red

    def set_color(self, color: QColor) -> None:
        if self._color != color:
            self._color = color
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = min(w, h) / 2.0 - 1.0

        # Outer soft glow
        glow_color = QColor(self._color)
        glow_color.setAlpha(60)
        painter.setBrush(glow_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(int(w / 2), int(h / 2)), int(radius + 1.0), int(radius + 1.0))

        # Main LED body
        painter.setBrush(self._color)
        painter.setPen(QPen(self._color.darker(140), 1))
        painter.drawEllipse(QPoint(int(w / 2), int(h / 2)), int(radius), int(radius))

        # Specular reflection highlight
        highlight = QColor(255, 255, 255, 170)
        painter.setBrush(highlight)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(w / 2 - radius / 2.5), int(h / 2 - radius / 2.5), 3, 3)


class StatusIndicatorsWidget(QFrame):
    """
    Dual LED status indicator panel monitoring USB Dongle and Controller link.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Dongle Row
        dongle_layout = QHBoxLayout()
        dongle_layout.setContentsMargins(0, 0, 0, 0)
        dongle_layout.setSpacing(6)
        self.dongle_led = LedIndicator()
        self.dongle_label = QLabel("Dongle: Disconnected")
        self.dongle_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        dongle_layout.addWidget(self.dongle_led)
        dongle_layout.addWidget(self.dongle_label)
        dongle_layout.addStretch()
        layout.addLayout(dongle_layout)

        # Controller Row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(6)
        self.ctrl_led = LedIndicator()
        self.ctrl_label = QLabel("Controller: Disconnected")
        self.ctrl_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        ctrl_layout.addWidget(self.ctrl_led)
        ctrl_layout.addWidget(self.ctrl_label)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        self.update_dongle_status(DeviceStatus.DISCONNECTED, "USB Dongle unplugged")
        self.update_controller_status(DeviceStatus.DISCONNECTED, "Controller turned off or sleeping")

    def _get_status_color(self, status: DeviceStatus) -> QColor:
        if status == DeviceStatus.CONNECTED:
            return QColor(40, 167, 69)  # Green
        elif status == DeviceStatus.ERROR:
            return QColor(255, 193, 7)  # Yellow
        else:
            return QColor(220, 53, 69)  # Red

    def update_dongle_status(self, status: DeviceStatus, details: str) -> None:
        color = self._get_status_color(status)
        self.dongle_led.set_color(color)
        self.dongle_label.setText(f"Dongle: {status.value}")
        self.dongle_label.setToolTip(f"<b>USB Dongle Status:</b> {status.value}<br><i>{details}</i>")

    def update_controller_status(self, status: DeviceStatus, details: str) -> None:
        color = self._get_status_color(status)
        self.ctrl_led.set_color(color)
        self.ctrl_label.setText(f"Controller: {status.value}")
        self.ctrl_label.setToolTip(f"<b>Controller Link Status:</b> {status.value}<br><i>{details}</i>")


class CardPanel(QFrame):
    """Container with rounded border and optional header title."""

    def __init__(self, title: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardPanel")
        self.setFrameShape(QFrame.StyledPanel)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 12)
        self.main_layout.setSpacing(8)

        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            self.main_layout.addWidget(title_label)


class PaddleRowWidget(QFrame):
    """
    UI row representing a single button/paddle/combo bind.
    Seamlessly switches between Single Key and Macro modes with live validation.
    """

    open_recorder = Signal(str, object)  # (name, QLineEdit)
    open_editor = Signal(str, object)    # (name, QLineEdit)

    def __init__(self, display_name: str, bind: PaddleBind, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.display_name = display_name
        self.bind = bind
        self.is_reserved = False

        self.setObjectName("cardPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # 1. Label
        self.name_label = QLabel(f"{display_name}:")
        self.name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.name_label.setFixedWidth(145)
        layout.addWidget(self.name_label)

        # 2. Enabled Checkbox
        self.enabled_cb = QCheckBox("Enabled")
        self.enabled_cb.setChecked(bind.enabled)
        layout.addWidget(self.enabled_cb)

        # 3. Macro Toggle Checkbox
        self.macro_cb = QCheckBox("Macro")
        self.macro_cb.setChecked(bind.is_macro)
        layout.addWidget(self.macro_cb)

        # --- SINGLE KEY CONTROLS ---
        self.shift_cb = QCheckBox("Shift")
        self.shift_cb.setChecked(bind.shift)
        self.ctrl_cb = QCheckBox("Ctrl")
        self.ctrl_cb.setChecked(bind.ctrl)
        self.alt_cb = QCheckBox("Alt")
        self.alt_cb.setChecked(bind.alt)
        self.win_cb = QCheckBox("Win")
        self.win_cb.setChecked(bind.win)

        self.key_combo = QComboBox()
        self.key_combo.setMinimumWidth(110)
        self.key_combo.addItems(SUPPORTED_KEYS)
        idx = self.key_combo.findText(bind.key_char, Qt.MatchFixedString)
        if idx >= 0:
            self.key_combo.setCurrentIndex(idx)
        else:
            self.key_combo.setCurrentText(bind.key_char)

        layout.addWidget(self.shift_cb)
        layout.addWidget(self.ctrl_cb)
        layout.addWidget(self.alt_cb)
        layout.addWidget(self.win_cb)
        layout.addWidget(self.key_combo)

        # --- MACRO CONTROLS ---
        self.repeat_cb = QCheckBox("Repeat")
        self.repeat_cb.setChecked(bind.repeat_macro)
        self.step_cb = QCheckBox("Step")
        self.step_cb.setChecked(bind.step_through)

        self.macro_edit = QLineEdit(bind.macro_text)
        self.macro_edit.setPlaceholderText("e.g. 100ms, A down, 50ms, A up")
        self.macro_edit.setMinimumWidth(180)

        self.rec_btn = QPushButton("Rec")
        self.rec_btn.setToolTip("Launch live macro recorder")
        self.rec_btn.setStyleSheet("color: #ff5252; font-weight: bold;")
        self.rec_btn.clicked.connect(lambda: self.open_recorder.emit(self.display_name, self.macro_edit))

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setToolTip("Open full-size macro editor")
        self.edit_btn.clicked.connect(lambda: self.open_editor.emit(self.display_name, self.macro_edit))

        layout.addWidget(self.repeat_cb)
        layout.addWidget(self.step_cb)
        layout.addWidget(self.rec_btn)
        layout.addWidget(self.edit_btn)
        layout.addWidget(self.macro_edit)

        # 4. Reserved Label (For Layer Toggles)
        self.reserved_label = QLabel("Reserved for Layer Toggle")
        self.reserved_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Normal, italic=True))
        self.reserved_label.setStyleSheet("color: #888888;")
        self.reserved_label.setVisible(False)
        layout.addWidget(self.reserved_label)

        layout.addStretch()

        # Connect inter-control logic
        self.enabled_cb.toggled.connect(self.refresh_visibility)
        self.macro_cb.toggled.connect(self.refresh_visibility)
        self.repeat_cb.toggled.connect(self._on_repeat_toggled)
        self.step_cb.toggled.connect(self._on_step_toggled)

        self.refresh_visibility()

    def _on_repeat_toggled(self, checked: bool) -> None:
        if checked:
            self.step_cb.setChecked(False)

    def _on_step_toggled(self, checked: bool) -> None:
        if checked:
            self.repeat_cb.setChecked(False)

    def set_reserved(self, is_reserved: bool) -> None:
        self.is_reserved = is_reserved
        self.refresh_visibility()

    def refresh_visibility(self) -> None:
        is_en = self.enabled_cb.isChecked()
        is_mac = self.macro_cb.isChecked()
        res = self.is_reserved

        self.reserved_label.setVisible(res)
        self.enabled_cb.setVisible(not res)
        self.macro_cb.setVisible(not res)

        # Single key visibility
        single_visible = (not is_mac) and (not res)
        self.shift_cb.setVisible(single_visible)
        self.ctrl_cb.setVisible(single_visible)
        self.alt_cb.setVisible(single_visible)
        self.win_cb.setVisible(single_visible)
        self.key_combo.setVisible(single_visible)

        self.shift_cb.setEnabled(is_en)
        self.ctrl_cb.setEnabled(is_en)
        self.alt_cb.setEnabled(is_en)
        self.win_cb.setEnabled(is_en)
        self.key_combo.setEnabled(is_en)

        # Macro visibility
        macro_visible = is_mac and (not res)
        self.repeat_cb.setVisible(macro_visible)
        self.step_cb.setVisible(macro_visible)
        self.rec_btn.setVisible(macro_visible)
        self.edit_btn.setVisible(macro_visible)
        self.macro_edit.setVisible(macro_visible)

        self.repeat_cb.setEnabled(is_en)
        self.step_cb.setEnabled(is_en)
        self.rec_btn.setEnabled(is_en)
        self.edit_btn.setEnabled(is_en)
        self.macro_edit.setEnabled(is_en)

    def load_from_bind(self, bind: PaddleBind) -> None:
        self.bind = bind
        self.enabled_cb.setChecked(bind.enabled)
        self.macro_cb.setChecked(bind.is_macro)
        self.repeat_cb.setChecked(bind.repeat_macro)
        self.step_cb.setChecked(bind.step_through)
        self.macro_edit.setText(bind.macro_text)

        self.shift_cb.setChecked(bind.shift)
        self.ctrl_cb.setChecked(bind.ctrl)
        self.alt_cb.setChecked(bind.alt)
        self.win_cb.setChecked(bind.win)

        idx = self.key_combo.findText(bind.key_char, Qt.MatchFixedString)
        if idx >= 0:
            self.key_combo.setCurrentIndex(idx)
        else:
            self.key_combo.setCurrentText(bind.key_char)

        self.refresh_visibility()

    def save_to_bind(self, bind: Optional[PaddleBind] = None) -> PaddleBind:
        target = bind or self.bind
        target.enabled = self.enabled_cb.isChecked()
        target.is_macro = self.macro_cb.isChecked()
        target.repeat_macro = self.repeat_cb.isChecked()
        target.step_through = self.step_cb.isChecked()
        target.macro_text = self.macro_edit.text().strip()

        target.shift = self.shift_cb.isChecked()
        target.ctrl = self.ctrl_cb.isChecked()
        target.alt = self.alt_cb.isChecked()
        target.win = self.win_cb.isChecked()
        target.key_char = self.key_combo.currentText()

        return target

