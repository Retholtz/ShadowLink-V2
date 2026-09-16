"""
Semi-transparent On-Screen Display (OSD) overlay window for ShadowLink.
Displays brief toast notifications in user-selected screen corners upon layer/profile changes.
"""

from __future__ import annotations
import logging
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("ShadowLink.OSD")


class OsdNotification(QWidget):
    """
    Non-focusable, semi-transparent toast overlay window.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._message = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, message: str, corner: str = "Bottom Right", duration_ms: int = 2000) -> None:
        self._message = message

        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(message)
        text_height = fm.height()

        padding_x = 40
        padding_y = 20
        w = text_width + (padding_x * 2)
        h = text_height + (padding_y * 2)
        self.resize(w, h)

        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            margin = 35

            if corner in ("Bottom Right", "Top Right"):
                x = geom.x() + geom.width() - w - margin
            else:
                x = geom.x() + margin

            if corner in ("Bottom Right", "Bottom Left"):
                y = geom.y() + geom.height() - h - margin
            else:
                y = geom.y() + margin

            self.move(x, y)

        self.show()
        self.update()
        self._hide_timer.start(duration_ms)

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._message:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Semi-transparent dark capsule
        painter.setBrush(QColor(15, 15, 15, 215))
        painter.setPen(QColor(80, 80, 80, 180))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

        # Accent border highlight
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignCenter, self._message)


_osd_instance: Optional[OsdNotification] = None


def get_osd() -> OsdNotification:
    global _osd_instance
    if _osd_instance is None:
        _osd_instance = OsdNotification()
    return _osd_instance


def show_osd(message: str, corner: str = "Bottom Right") -> None:
    osd = get_osd()
    osd.show_message(message, corner=corner)

