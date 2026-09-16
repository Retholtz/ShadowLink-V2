"""
Dialog windows for ShadowLink:
- MacroEditorDialog: Full-size multi-line editor with syntax hints.
- MacroRecorderDialog: Live interactive key/mouse capture recorder with millisecond delay tracking.
- ActiveProcessDialog: Searchable running applications picker.
- Help dialogs for Macro and Layer instructions.
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import os
import time
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from keymap import KEY_MAP, get_key_info

logger = logging.getLogger("ShadowLink.Dialogs")


# --- MACRO TEXT EDITOR DIALOG ---

class MacroEditorDialog(QDialog):
    """
    Full-sized multi-line text editor with syntax guide and formatting tips.
    """

    def __init__(self, paddle_name: str, target_field: QLineEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.target_field = target_field
        self.setWindowTitle(f"Macro Text Editor - {paddle_name}")
        self.resize(560, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_label = QLabel("Edit Macro String:")
        header_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(header_label)

        self.editor = QPlainTextEdit(target_field.text())
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.editor)

        # Syntax hint
        hint_label = QLabel(
            "Actions separated by commas or semicolons.<br>"
            "<b>Delays:</b> <code>100ms</code>, <code>1.5s</code>, or random <code>50ms~150ms</code><br>"
            "<b>Keys:</b> <code>Space</code>, <code>A down</code>, <code>A up</code><br>"
            "<b>Mouse:</b> <code>LClick</code>, <code>MouseAbs 1920 1080</code>, <code>MouseDelta 0 50</code>"
        )
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(hint_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("accentButton")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        self.target_field.setText(self.editor.toPlainText().strip())
        self.accept()


# --- LIVE MACRO RECORDER DIALOG ---

class MacroCapturePanel(QFrame):
    """
    Interactive event capture surface recording key presses/releases and mouse clicks.
    """

    token_recorded = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(90)
        self.setObjectName("cardPanel")
        self.setFrameShape(QFrame.StyledPanel)

        self._recording = False

        layout = QVBoxLayout(self)
        self.label = QLabel("Click here to focus, then perform your Macro...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        layout.addWidget(self.label)

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        if recording:
            self.label.setText("🔴 Recording active! Perform key and mouse actions...")
            self.setStyleSheet("background-color: #3b2222; border: 1px solid #ff5252;")
            self.setFocus()
        else:
            self.label.setText("Click here to focus, then perform your Macro...")
            self.setStyleSheet("")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording or event.isAutoRepeat():
            return super().keyPressEvent(event)

        key_name = self._map_qt_key(event.key())
        if key_name:
            self.token_recorded.emit(f"{key_name} down")
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self._recording or event.isAutoRepeat():
            return super().keyReleaseEvent(event)

        key_name = self._map_qt_key(event.key())
        if key_name:
            self.token_recorded.emit(f"{key_name} up")
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._recording:
            return super().mousePressEvent(event)

        btn = None
        if event.button() == Qt.LeftButton:
            btn = "LClick down"
        elif event.button() == Qt.RightButton:
            btn = "RClick down"
        elif event.button() == Qt.MiddleButton:
            btn = "MClick down"

        if btn:
            self.token_recorded.emit(btn)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._recording:
            return super().mouseReleaseEvent(event)

        btn = None
        if event.button() == Qt.LeftButton:
            btn = "LClick up"
        elif event.button() == Qt.RightButton:
            btn = "RClick up"
        elif event.button() == Qt.MiddleButton:
            btn = "MClick up"

        if btn:
            self.token_recorded.emit(btn)
        event.accept()

    def _map_qt_key(self, qt_key: int) -> Optional[str]:
        # Mapping common Qt keys to ShadowLink KeyMap names
        _QT_KEY_MAP = {
            Qt.Key_Space: "Space", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
            Qt.Key_Escape: "ESC", Qt.Key_Tab: "Tab", Qt.Key_Backspace: "Backspace",
            Qt.Key_Shift: "Shift", Qt.Key_Control: "Ctrl", Qt.Key_Alt: "Alt", Qt.Key_Meta: "Win",
            Qt.Key_Insert: "Insert", Qt.Key_Delete: "Delete", Qt.Key_Home: "Home", Qt.Key_End: "End",
            Qt.Key_PageUp: "Page Up", Qt.Key_PageDown: "Page Down",
            Qt.Key_Up: "Up", Qt.Key_Down: "Down", Qt.Key_Left: "Left", Qt.Key_Right: "Right",
        }
        if qt_key in _QT_KEY_MAP:
            return _QT_KEY_MAP[qt_key]

        # Alphanumerics (A-Z)
        if Qt.Key_A <= qt_key <= Qt.Key_Z:
            return chr(qt_key)
        # Numbers (0-9)
        if Qt.Key_0 <= qt_key <= Qt.Key_9:
            return chr(qt_key)
        # Function keys (F1-F24)
        if Qt.Key_F1 <= qt_key <= Qt.Key_F24:
            f_num = qt_key - Qt.Key_F1 + 1
            return f"F{f_num}"

        return None


class MacroRecorderDialog(QDialog):
    """
    Live Macro Recorder capturing user actions with elapsed timings.
    """

    def __init__(self, target_field: QLineEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.target_field = target_field
        self.setWindowTitle("Live Macro Recorder")
        self.resize(620, 460)

        self._tokens: list[str] = []
        self._last_time = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_label = QLabel("Recorded Macro Sequence:")
        header_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(header_label)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(QFont("Consolas", 11))
        initial_text = target_field.text().strip()
        if initial_text:
            self._tokens = [t.strip() for t in initial_text.split(",") if t.strip()]
            self.preview_edit.setPlainText(", ".join(self._tokens))
        layout.addWidget(self.preview_edit)

        # Capture surface
        self.capture_panel = MacroCapturePanel()
        self.capture_panel.token_recorded.connect(self._on_token_recorded)
        layout.addWidget(self.capture_panel)

        # Controls bar
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Recording")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save to Macro")
        save_btn.setObjectName("accentButton")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_token_recorded(self, token: str) -> None:
        now = time.time()
        if self._last_time > 0:
            elapsed_ms = int((now - self._last_time) * 1000)
            if elapsed_ms > 10:
                self._tokens.append(f"{elapsed_ms}ms")
        self._tokens.append(token)
        self._last_time = now
        self.preview_edit.setPlainText(", ".join(self._tokens))
        self.preview_edit.verticalScrollBar().setValue(
            self.preview_edit.verticalScrollBar().maximum()
        )

    def _on_start(self) -> None:
        self._last_time = 0.0
        self.capture_panel.set_recording(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_stop(self) -> None:
        self.capture_panel.set_recording(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_clear(self) -> None:
        self._tokens.clear()
        self._last_time = 0.0
        self.preview_edit.clear()

    def _on_save(self) -> None:
        self.target_field.setText(", ".join(self._tokens))
        self.accept()


# --- ACTIVE PROCESS PICKER DIALOG ---

class ActiveProcessDialog(QDialog):
    """
    Searchable dialog enumerating running applications by process name and window title.
    """

    def __init__(self, target_field: QLineEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.target_field = target_field
        self.setWindowTitle("Select Running Application")
        self.resize(520, 560)

        self.apps_data: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        search_label = QLabel("Search for an open application:")
        search_label.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        layout.addWidget(search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type process name (e.g. game.exe) or title...")
        self.search_edit.textChanged.connect(self._filter_list)
        layout.addWidget(self.search_edit)

        self.process_list = QListWidget()
        self.process_list.itemDoubleClicked.connect(self._on_select)
        layout.addWidget(self.process_list)

        # Footer
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        select_btn = QPushButton("Use Selected Process")
        select_btn.setObjectName("accentButton")
        select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(select_btn)

        layout.addLayout(btn_layout)

        self._populate_processes()

    def _populate_processes(self) -> None:
        self.apps_data = self._enumerate_desktop_windows()
        self._filter_list(self.search_edit.text())

    def _filter_list(self, query: str) -> None:
        self.process_list.clear()
        q = query.strip().lower()
        for exe_name in sorted(self.apps_data.keys(), key=lambda s: s.lower()):
            title = self.apps_data[exe_name]
            if not q or (q in exe_name.lower()) or (q in title.lower()):
                item = QListWidgetItem()
                item.setText(f"{exe_name}  ({title})" if title else exe_name)
                item.setData(Qt.UserRole, exe_name)
                self.process_list.addItem(item)

    def _on_select(self) -> None:
        current_item = self.process_list.currentItem()
        if current_item:
            exe_name = current_item.data(Qt.UserRole)
            self.target_field.setText(exe_name.lower())
            self.accept()

    @staticmethod
    def _enumerate_desktop_windows() -> dict[str, str]:
        results: dict[str, str] = {}
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        # 1. First enumerate interactive windows
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        u32.EnumWindows.restype = wintypes.BOOL

        def enum_cb(hwnd, lparam):
            if u32.IsWindowVisible(hwnd):
                length = u32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    u32.GetWindowTextW(hwnd, title_buf, length + 1)
                    title = title_buf.value.strip()

                    pid = wintypes.DWORD()
                    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    h = k32.OpenProcess(0x1000, False, pid.value)
                    if h:
                        path_buf = ctypes.create_unicode_buffer(1024)
                        size = wintypes.DWORD(1024)
                        if k32.QueryFullProcessImageNameW(h, 0, path_buf, ctypes.byref(size)):
                            exe = os.path.basename(path_buf.value)
                            if exe.lower() not in ("explorer.exe", "shadowlink.exe"):
                                results[exe] = title
                        k32.CloseHandle(h)
            return True

        u32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # 2. If windows enumeration returned few or none, complement with Process snapshot
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        h = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h:
            pe = PROCESSENTRY32()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if k32.Process32First(h, ctypes.byref(pe)):
                while True:
                    name = pe.szExeFile.decode("mbcs", errors="ignore").strip()
                    if name and not name.startswith("[") and name.endswith(".exe"):
                        if name not in results and name.lower() not in ("services.exe", "svchost.exe", "smss.exe"):
                            results[name] = ""
                    if not k32.Process32Next(h, ctypes.byref(pe)):
                        break
            k32.CloseHandle(h)

        return results


# --- HELP & INSTRUCTION DIALOGS ---

class HelpDialog(QDialog):
    def __init__(self, title: str, html_content: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        label = QLabel(html_content)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.addWidget(label)
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


def show_macro_instructions(parent: Optional[QWidget] = None) -> None:
    content = """
    <h2>Advanced Macro Creation Guide</h2>
    <p>Macros allow you to execute sequences of keystrokes, delays, and mouse movements. Separate each action with a comma.</p>
    
    <h3>Action Types:</h3>
    <ul>
        <li><b>Tap a Key:</b> Type the key name. <i>(e.g., <b>A</b> or <b>Enter</b>)</i></li>
        <li><b>Mouse Clicks:</b> Use <b>LClick</b>, <b>RClick</b>, or <b>MClick</b>.</li>
        <li><b>Hold a Key:</b> Type the key name followed by "down". <i>(e.g., <b>Ctrl down</b>)</i></li>
        <li><b>Release a Key:</b> Type the key name followed by "up". <i>(e.g., <b>Ctrl up</b>)</i></li>
        <li><b>Static Delay:</b> Type a number to wait in milliseconds. <i>(e.g., <b>500ms</b>)</i></li>
        <li><b>Random Delay:</b> Type a range separated by a tilde to humanize inputs! <i>(e.g., <b>50ms~150ms</b> waits a random amount of time between 50ms and 150ms)</i></li>
        <li><b>Mouse Moves:</b> Use absolute coordinates <i>(e.g., <b>MouseAbs 1920 1080</b>)</i> or relative moves <i>(e.g., <b>MouseDelta 0 50</b> moves the mouse 50 pixels down)</i>.</li>
    </ul>
    
    <h3>Step-Through Macros:</h3>
    <p>Checking <b>Step</b> changes how the macro fires. Every time you press the paddle, it will execute <b>only the next action</b> in your list, cycling back to the start when finished.</p>
    <br>
    <p style='color: #ff5252;'><b>⚠️  Pro-Tip for Step Macros:</b> Do not use the Live Recorder for Step macros! The recorder captures individual "down", "delay", and "up" events, meaning you will have to press the paddle 3-4 times just to type one letter. For Step macros, manually type clean, comma-separated lists like: <code>A, B, C</code>.</p>
    """
    dlg = HelpDialog("Macro Instructions", content, parent)
    dlg.exec()


def show_layer_instructions(parent: Optional[QWidget] = None) -> None:
    content = """
    <h2>Layer & Combo System Guide</h2>
    <p>Layers allow you to switch between entirely different sets of bindings on the fly. Combos allow you to trigger actions by pressing two buttons simultaneously!</p>
    
    <h3>Using Combo Button Macros:</h3>
    <ul>
        <li>Combo macros (like <b>M1 + M2</b>) trigger when both specific buttons are pressed.</li>
        <li>When you trigger a Combo Macro, the individual actions assigned to M1 and M2 are automatically canceled so they don't fire by mistake!</li>
        <li><b>Note:</b> You must ensure Combo Buttons are checked as "Enabled" in the UI for them to override single buttons.</li>
    </ul>
    
    <h3>Single Button vs. Combo Layer Toggles:</h3>
    <ul>
        <li><b>Single Toggle (e.g., Command):</b> If you assign only one button to switch Layers in Layer Settings, it becomes permanently reserved globally. You won't be able to assign standard inputs to it.</li>
        <li><b>Combo Toggle (e.g., M1 + M4):</b> If you assign a two-button combo for your Layer shift, you can still use those buttons individually! The system pauses your single actions only when you press them both together to shift layers.</li>
    </ul>
    """
    dlg = HelpDialog("Layer & Combo Instructions", content, parent)
    dlg.exec()

