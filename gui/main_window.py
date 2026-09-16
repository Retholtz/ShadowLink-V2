"""
Main Application Window for ShadowLink.
Assembles the Windows 11 GUI: Profile header, dual status LEDs, Auto-Switch preferences,
5 Layer binding tabs, Controller/Layer settings, System Tray integration, and thread-safe hardware bridges.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
import sys
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from config import (
    AutoSwitchWatchdog,
    create_desktop_shortcut,
    get_app_icon,
    get_profiles_directory,
    get_resource_path,
    load_all_profiles,
    load_global_config,
    save_global_config,
    save_profile,
)
import hardware
from hardware import ControllerManager
import keymap
from models import DeviceStatus, LayerConfig, PaddleBind, Profile
from gui.dialogs import (
    ActiveProcessDialog,
    MacroEditorDialog,
    MacroRecorderDialog,
    show_layer_instructions,
    show_macro_instructions,
)
from gui.osd import show_osd
from gui.theme import get_fluent_stylesheet, is_windows_dark_mode
from gui.widgets import CardPanel, PaddleRowWidget, StatusIndicatorsWidget

logger = logging.getLogger("ShadowLink.MainWindow")


class HardwareBridge(QObject):
    """Bridges callbacks from background hardware threads into Qt main thread signals."""
    status_updated = Signal(object, str, object, str)  # dongle_status, dongle_desc, ctrl_status, ctrl_desc
    layer_changed = Signal(int, str)                   # layer_num, layer_name
    paddle_event = Signal(str, bool, bool)             # name, raw_pressed, debounced
    auto_switched = Signal(object)                     # Profile


class MainWindow(QMainWindow):
    def __init__(self, manager: ControllerManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.all_profiles = load_all_profiles()
        self.global_cfg = load_global_config()

        # Find initial profile
        target_name = self.global_cfg.get("active_profile", "Default")
        self.active_profile = next(
            (p for p in self.all_profiles if p.name.lower() == target_name.lower()),
            self.all_profiles[0]
        )
        self.manager.set_profile(self.active_profile)

        self.setWindowTitle(f"ShadowLink - ASUS ROG Controller Remapper")
        self.resize(1240, 820)
        self.setMinimumSize(1000, 700)

        # Thread bridge
        self.bridge = HardwareBridge()
        self.bridge.status_updated.connect(self._on_status_updated)
        self.bridge.layer_changed.connect(self._on_layer_changed)
        self.bridge.paddle_event.connect(self._on_paddle_event)
        self.bridge.auto_switched.connect(self._on_auto_switched)

        self.manager.on_status_updated = lambda ds, dd, cs, cd: self.bridge.status_updated.emit(ds, dd, cs, cd)
        self.manager.on_layer_changed = lambda idx, name: self.bridge.layer_changed.emit(idx, name)
        self.manager.on_paddle_event = lambda name, raw, deb: self.bridge.paddle_event.emit(name, raw, deb)

        # Build UI layout
        self._init_app_icon()
        self._init_ui()
        self._init_system_tray()
        self.refresh_layer_locks()

        # Start AutoSwitch watchdog if enabled
        self.auto_switcher: Optional[AutoSwitchWatchdog] = None
        if self.global_cfg.get("auto_switch", True):
            self._start_auto_switcher()

        # Center on primary screen
        self._center_window()

    def _init_app_icon(self) -> None:
        self.app_icon = get_app_icon()
        self.setWindowIcon(self.app_icon)

    def _center_window(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            x = screen_geom.x() + (screen_geom.width() - self.width()) // 2
            y = screen_geom.y() + (screen_geom.height() - self.height()) // 2
            self.move(x, y)

    def _init_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # 1. TOP CARDS
        header_layout = QVBoxLayout()
        header_layout.setSpacing(8)

        # Card 1: Profile Management & Status
        profile_card = CardPanel("Profile Management")
        p_layout = QHBoxLayout()
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(10)

        self.status_widget = StatusIndicatorsWidget()
        p_layout.addWidget(self.status_widget)

        p_label = QLabel("Current Profile:")
        p_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p_layout.addWidget(p_label)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self._reload_profile_dropdown()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        p_layout.addWidget(self.profile_combo)

        self.new_btn = QPushButton("New Profile")
        self.new_btn.clicked.connect(self._on_new_profile)
        self.clone_btn = QPushButton("Clone Profile")
        self.clone_btn.clicked.connect(self._on_clone_profile)
        self.del_btn = QPushButton("Delete Profile")
        self.del_btn.clicked.connect(self._on_delete_profile)
        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self._on_import_profile)
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export_profile)

        p_layout.addWidget(self.new_btn)
        p_layout.addWidget(self.clone_btn)
        p_layout.addWidget(self.del_btn)
        p_layout.addWidget(self.import_btn)
        p_layout.addWidget(self.export_btn)
        p_layout.addStretch()

        # Theme toggle button
        self.theme_btn = QPushButton("Toggle Theme")
        self.theme_btn.clicked.connect(self._on_toggle_theme)
        p_layout.addWidget(self.theme_btn)

        profile_card.main_layout.addLayout(p_layout)
        header_layout.addWidget(profile_card)

        # Card 2: Auto-Switching & App Preferences
        pref_card = CardPanel("Auto-Switching & App Preferences")
        pref_layout = QHBoxLayout()
        pref_layout.setContentsMargins(0, 0, 0, 0)
        pref_layout.setSpacing(10)

        target_lbl = QLabel("Auto-Switch Executable:")
        target_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        pref_layout.addWidget(target_lbl)

        self.process_field = QLineEdit(self.active_profile.target_process)
        self.process_field.setPlaceholderText("e.g. game.exe")
        self.process_field.setMinimumWidth(160)
        pref_layout.addWidget(self.process_field)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_exe)
        self.active_apps_btn = QPushButton("Active Apps...")
        self.active_apps_btn.clicked.connect(self._on_open_active_apps)
        pref_layout.addWidget(self.browse_btn)
        pref_layout.addWidget(self.active_apps_btn)

        pref_layout.addSpacing(15)

        self.auto_switch_cb = QCheckBox("Auto-Switch Enabled")
        self.auto_switch_cb.setChecked(self.global_cfg.get("auto_switch", True))
        self.auto_switch_cb.toggled.connect(self._on_auto_switch_toggled)

        self.minimized_cb = QCheckBox("Start Minimized")
        self.minimized_cb.setChecked(self.global_cfg.get("start_minimized", False))

        self.startup_cb = QCheckBox("Load on Startup")
        self.startup_cb.setChecked(self.global_cfg.get("load_on_startup", False))

        pref_layout.addWidget(self.auto_switch_cb)
        pref_layout.addWidget(self.minimized_cb)
        pref_layout.addWidget(self.startup_cb)
        pref_layout.addStretch()

        pref_card.main_layout.addLayout(pref_layout)
        header_layout.addWidget(pref_card)

        main_layout.addLayout(header_layout)

        # 2. MAIN TABS (5 LAYERS + SETTINGS)
        self.main_tabs = QTabWidget()
        self.layer_ui_rows: list[dict[str, PaddleRowWidget]] = []
        self.layer_name_edits: list[QLineEdit] = []
        self.layer_enable_cbs: list[QCheckBox] = []

        for i in range(5):
            layer_config = self.active_profile.layers[i]
            layer_tab = self._create_layer_tab(i, layer_config)
            tab_title = f"Layer {i+1}: {layer_config.name}"
            self.main_tabs.addTab(layer_tab, tab_title)

        # Tab 6: Settings
        settings_tab = self._create_settings_tab()
        self.main_tabs.addTab(settings_tab, "Controller / Layer Settings")

        main_layout.addWidget(self.main_tabs, 1)

        # 3. FOOTER ACTION PANEL
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(10)

        # OSD Corner Selector
        osd_lbl = QLabel("OSD Corner:")
        footer_layout.addWidget(osd_lbl)
        self.osd_combo = QComboBox()
        self.osd_combo.addItems(["Bottom Right", "Bottom Left", "Top Right", "Top Left"])
        self.osd_combo.setCurrentText(self.global_cfg.get("osd_position", "Bottom Right"))
        footer_layout.addWidget(self.osd_combo)

        # Help & Log Buttons
        self.macro_help_btn = QPushButton("Macro Help")
        self.macro_help_btn.clicked.connect(lambda: show_macro_instructions(self))
        self.layer_help_btn = QPushButton("Layer Help")
        self.layer_help_btn.clicked.connect(lambda: show_layer_instructions(self))
        self.export_log_btn = QPushButton("Export Log")
        self.export_log_btn.clicked.connect(self._on_export_log)

        footer_layout.addWidget(self.macro_help_btn)
        footer_layout.addWidget(self.layer_help_btn)
        footer_layout.addWidget(self.export_log_btn)
        footer_layout.addStretch()

        # Save Button
        self.save_btn = QPushButton("Save & Apply Settings")
        self.save_btn.setObjectName("accentButton")
        self.save_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.save_btn.setMinimumHeight(38)
        self.save_btn.setMinimumWidth(220)
        self.save_btn.clicked.connect(self._on_save_all)
        footer_layout.addWidget(self.save_btn)

        main_layout.addLayout(footer_layout)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("ShadowLink ready.")

    def _create_layer_tab(self, layer_index: int, layer_config: LayerConfig) -> QWidget:
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top Bar: Name & Enabled checkbox
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 4, 4, 4)
        top_bar.setSpacing(10)

        name_lbl = QLabel("Layer Name:")
        name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        top_bar.addWidget(name_lbl)

        name_edit = QLineEdit(layer_config.name)
        name_edit.setMaximumWidth(200)
        name_edit.textChanged.connect(lambda txt: self._update_layer_tab_title(layer_index, txt))
        self.layer_name_edits.append(name_edit)
        top_bar.addWidget(name_edit)

        enable_cb = QCheckBox("Enable this layer")
        enable_cb.setChecked(layer_config.enabled)
        if layer_index == 0:
            enable_cb.setChecked(True)
            enable_cb.setEnabled(False)  # Layer 1 is always active
        self.layer_enable_cbs.append(enable_cb)
        top_bar.addWidget(enable_cb)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        # Sub-tabs for categorization
        sub_tabs = QTabWidget()
        sub_tabs.setTabPosition(QTabWidget.West)

        rows_map: dict[str, PaddleRowWidget] = {}

        def create_scroll_panel(items: list[tuple[str, str, PaddleBind]]) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(6, 6, 6, 6)
            c_layout.setSpacing(6)

            for key_id, display_title, bind_obj in items:
                row = PaddleRowWidget(display_title, bind_obj)
                row.open_recorder.connect(self._open_macro_recorder)
                row.open_editor.connect(self._open_macro_editor)
                rows_map[key_id] = row
                c_layout.addWidget(row)

            c_layout.addStretch()
            scroll.setWidget(container)
            return scroll

        # 1. Back Paddles
        back_paddles = [
            ("cmd", "Command", layer_config.cmd),
            ("lib", "Library", layer_config.lib),
            ("m1", "M1 (Bot-L)", layer_config.m1),
            ("m2", "M2 (Top-L)", layer_config.m2),
            ("m3", "M3 (Top-R)", layer_config.m3),
            ("m4", "M4 (Bot-R)", layer_config.m4),
        ]
        sub_tabs.addTab(create_scroll_panel(back_paddles), " Back Paddles ")

        # 2. Paddle Combos
        combos = [
            ("m1_m2", "M1 + M2", layer_config.m1_m2),
            ("m1_m3", "M1 + M3", layer_config.m1_m3),
            ("m1_m4", "M1 + M4", layer_config.m1_m4),
            ("m2_m3", "M2 + M3", layer_config.m2_m3),
            ("m2_m4", "M2 + M4", layer_config.m2_m4),
            ("m3_m4", "M3 + M4", layer_config.m3_m4),
            ("cmd_lib", "Cmd + Lib", layer_config.cmd_lib),
        ]
        sub_tabs.addTab(create_scroll_panel(combos), " Paddle Combos ")

        # 3. Standard Inputs
        standards = [
            ("lb", "LB (Left Bumper)", layer_config.lb),
            ("rb", "RB (Right Bumper)", layer_config.rb),
            ("lt", "LT (Left Trigger)", layer_config.lt),
            ("rt", "RT (Right Trigger)", layer_config.rt),
            ("a", "A Button", layer_config.a),
            ("b", "B Button", layer_config.b),
            ("x", "X Button", layer_config.x),
            ("y", "Y Button", layer_config.y),
            ("l3", "L3 (Left Stick Click)", layer_config.l3),
            ("r3", "R3 (Right Stick Click)", layer_config.r3),
            ("d_up", "D-Pad Up", layer_config.d_up),
            ("d_down", "D-Pad Down", layer_config.d_down),
            ("d_left", "D-Pad Left", layer_config.d_left),
            ("d_right", "D-Pad Right", layer_config.d_right),
        ]
        sub_tabs.addTab(create_scroll_panel(standards), " Triggers & Face ")

        self.layer_ui_rows.append(rows_map)
        layout.addWidget(sub_tabs)
        return tab_widget

    def _create_settings_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Card 1: Layer Toggle Assignment
        toggle_card = CardPanel("Profile Layer Toggle Assignment")
        t_info = QLabel(
            "Select which buttons will cycle through your enabled layers <b>for this profile</b>.<br>"
            "Assigning a <b>Single Button</b> toggle reserves it globally, while assigning a <b>Dual Combo</b> "
            "allows both buttons to remain active individually!"
        )
        t_info.setWordWrap(True)
        t_info.setStyleSheet("color: #a0a0a0; margin-bottom: 8px;")
        toggle_card.main_layout.addWidget(t_info)

        toggle_options = ["None", "M1", "M2", "M3", "M4", "Command", "Library"]

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Primary Layer Toggle Button:"))
        self.t1_combo = QComboBox()
        self.t1_combo.addItems(toggle_options)
        self.t1_combo.setCurrentText(self.active_profile.toggle_button1)
        self.t1_combo.currentTextChanged.connect(lambda _: self.refresh_layer_locks())
        row1.addWidget(self.t1_combo)
        row1.addStretch()
        toggle_card.main_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Secondary Layer Toggle Button (Optional Dual-Combo):"))
        self.t2_combo = QComboBox()
        self.t2_combo.addItems(toggle_options)
        self.t2_combo.setCurrentText(self.active_profile.toggle_button2)
        self.t2_combo.currentTextChanged.connect(lambda _: self.refresh_layer_locks())
        row2.addWidget(self.t2_combo)
        row2.addStretch()
        toggle_card.main_layout.addLayout(row2)

        layout.addWidget(toggle_card)

        # Card 2: Advanced Hardware Settings
        hw_card = CardPanel("Advanced Hardware Settings")
        hw_info = QLabel(
            "<b>Controller Auto-Detect Rate:</b> How frequently the app scans for an unplugged or sleeping controller.<br>"
            "<b>Combo Input Delay:</b> Micro-buffer allowing you to press combo paddles together without misfiring single presses."
        )
        hw_info.setWordWrap(True)
        hw_info.setStyleSheet("color: #a0a0a0; margin-bottom: 8px;")
        hw_card.main_layout.addWidget(hw_info)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Controller Auto-Detect Scan Rate:"))
        self.scan_combo = QComboBox()
        self.scan_combo.addItem("1000 ms (Fastest)", 1000)
        self.scan_combo.addItem("2000 ms (Fast)", 2000)
        self.scan_combo.addItem("5000 ms (Default)", 5000)
        self.scan_combo.addItem("10000 ms (Slow)", 10000)
        curr_rate = self.global_cfg.get("scan_interval_ms", 5000)
        idx = self.scan_combo.findData(curr_rate)
        if idx >= 0:
            self.scan_combo.setCurrentIndex(idx)
        row3.addWidget(self.scan_combo)
        row3.addStretch()
        hw_card.main_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Combo Input Delay (Microlag Buffer):"))
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(0, 500)
        self.buffer_spin.setSingleStep(5)
        self.buffer_spin.setValue(self.active_profile.combo_buffer_ms)
        self.buffer_spin.setSuffix(" ms")
        row4.addWidget(self.buffer_spin)
        row4.addWidget(QLabel("(0 = Instant, 30 ms = Recommended)"))
        row4.addStretch()
        hw_card.main_layout.addLayout(row4)

        layout.addWidget(hw_card)

        # Card 3: Windows Desktop & Shortcut Integration
        desk_card = CardPanel("Windows Desktop & Shortcut Integration")
        desk_info = QLabel(
            "Place a shortcut for ShadowLink directly on your Windows Desktop configured with the custom "
            "ROG icon and silent background execution (no flashing console window)."
        )
        desk_info.setWordWrap(True)
        desk_info.setStyleSheet("color: #a0a0a0; margin-bottom: 8px;")
        desk_card.main_layout.addWidget(desk_info)

        row5 = QHBoxLayout()
        self.create_shortcut_btn = QPushButton("Create Desktop Shortcut")
        self.create_shortcut_btn.setIcon(self.app_icon)
        self.create_shortcut_btn.setMinimumHeight(32)
        self.create_shortcut_btn.clicked.connect(self._on_create_desktop_shortcut)
        row5.addWidget(self.create_shortcut_btn)

        self.shortcut_status_lbl = QLabel("")
        self.shortcut_status_lbl.setStyleSheet("color: #28a745; font-weight: bold;")
        row5.addWidget(self.shortcut_status_lbl)
        row5.addStretch()
        desk_card.main_layout.addLayout(row5)

        layout.addWidget(desk_card)
        layout.addStretch()

        return container

    def _update_layer_tab_title(self, layer_index: int, name: str) -> None:
        self.main_tabs.setTabText(layer_index, f"Layer {layer_index + 1}: {name.strip()}")

    def refresh_layer_locks(self) -> None:
        """Locks out paddles that are reserved as single-button layer toggles."""
        t1 = self.t1_combo.currentText()
        t2 = self.t2_combo.currentText()

        is_single = (
            (t1 != "None" and t2 == "None")
            or (t1 == "None" and t2 != "None")
            or (t1 != "None" and t1 == t2)
        )
        reserved_key = (t1 if t1 != "None" else t2).lower() if is_single else None

        alias_map = {
            "m1": "m1", "m2": "m2", "m3": "m3", "m4": "m4",
            "command": "cmd", "library": "lib"
        }
        target_id = alias_map.get(reserved_key, "") if reserved_key else ""

        for layer_rows in self.layer_ui_rows:
            for key_id, widget in layer_rows.items():
                widget.set_reserved(bool(target_id and key_id == target_id))

    def _reload_profile_dropdown(self) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in self.all_profiles:
            self.profile_combo.addItem(p.name)
        self.profile_combo.setCurrentText(self.active_profile.name)
        self.profile_combo.blockSignals(False)

    def _sync_ui_to_profile(self) -> None:
        """Write current UI state into self.active_profile."""
        self.active_profile.target_process = self.process_field.text().strip().lower()
        self.active_profile.toggle_button1 = self.t1_combo.currentText()
        self.active_profile.toggle_button2 = self.t2_combo.currentText()
        self.active_profile.combo_buffer_ms = self.buffer_spin.value()

        for i in range(5):
            layer_config = self.active_profile.layers[i]
            layer_config.name = self.layer_name_edits[i].text().strip()
            layer_config.enabled = self.layer_enable_cbs[i].isChecked()

            rows = self.layer_ui_rows[i]
            for key_id, widget in rows.items():
                bind_obj = getattr(layer_config, key_id, None)
                if bind_obj:
                    widget.save_to_bind(bind_obj)

    def _load_profile_into_ui(self, profile: Profile) -> None:
        """Populate GUI widgets from the given profile."""
        self.active_profile = profile
        self.manager.set_profile(profile)

        self.process_field.setText(profile.target_process)
        self.t1_combo.setCurrentText(profile.toggle_button1)
        self.t2_combo.setCurrentText(profile.toggle_button2)
        self.buffer_spin.setValue(profile.combo_buffer_ms)

        for i in range(5):
            layer_config = profile.layers[i]
            self.layer_name_edits[i].setText(layer_config.name)
            self.layer_enable_cbs[i].setChecked(layer_config.enabled)
            self._update_layer_tab_title(i, layer_config.name)

            rows = self.layer_ui_rows[i]
            for key_id, widget in rows.items():
                bind_obj = getattr(layer_config, key_id, None)
                if bind_obj:
                    widget.load_from_bind(bind_obj)

        self.refresh_layer_locks()
        self.status_bar.showMessage(f"Loaded profile '{profile.name}'")

    # --- PROFILE ACTIONS ---

    def _on_profile_selected(self, name: str) -> None:
        if not name or name == self.active_profile.name:
            return
        found = next((p for p in self.all_profiles if p.name == name), None)
        if found:
            self._sync_ui_to_profile()
            self._load_profile_into_ui(found)

    def _on_new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New Profile", "Enter Profile Name:")
        if ok and name.strip():
            p_name = name.strip()
            new_p = Profile(name=p_name)
            self.all_profiles.append(new_p)
            save_profile(new_p)
            self._reload_profile_dropdown()
            self.profile_combo.setCurrentText(p_name)
            self._load_profile_into_ui(new_p)

    def _on_clone_profile(self) -> None:
        curr_name = self.active_profile.name
        name, ok = QInputDialog.getText(self, "Clone Profile", f"Enter New Profile Name (Copy of {curr_name}):")
        if ok and name.strip():
            self._sync_ui_to_profile()
            d = self.active_profile.to_dict()
            d["name"] = name.strip()
            cloned = Profile.from_dict(d)
            self.all_profiles.append(cloned)
            save_profile(cloned)
            self._reload_profile_dropdown()
            self.profile_combo.setCurrentText(cloned.name)
            self._load_profile_into_ui(cloned)

    def _on_delete_profile(self) -> None:
        if len(self.all_profiles) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "You must keep at least one profile.")
            return

        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Are you sure you want to delete profile '{self.active_profile.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            target = self.active_profile
            file_path = get_profiles_directory() / f"{target.name}.json"
            if file_path.exists():
                file_path.unlink()
            self.all_profiles.remove(target)
            self._load_profile_into_ui(self.all_profiles[0])
            self._reload_profile_dropdown()

    def _on_import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "Profile Files (*.json *.properties)"
        )
        if path:
            p_path = Path(path)
            try:
                if p_path.suffix.lower() == ".properties":
                    imported = config.import_properties_profile(p_path)
                else:
                    imported = config.load_profile(p_path)

                # Save into profiles directory
                save_profile(imported)
                self.all_profiles = load_all_profiles()
                self._reload_profile_dropdown()
                self.profile_combo.setCurrentText(imported.name)
                self._load_profile_into_ui(imported)
                QMessageBox.information(self, "Import Success", f"Profile '{imported.name}' imported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import profile:\n{e}")

    def _on_export_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile", f"{self.active_profile.name}.json", "JSON Profile (*.json)"
        )
        if path:
            self._sync_ui_to_profile()
            try:
                save_profile(self.active_profile, Path(path))
                QMessageBox.information(self, "Export Success", f"Profile exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export profile:\n{e}")

    def _on_browse_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Executable", "", "Executables (*.exe)")
        if path:
            self.process_field.setText(Path(path).name.lower())

    def _on_open_active_apps(self) -> None:
        dlg = ActiveProcessDialog(self.process_field, self)
        dlg.exec()

    def _open_macro_recorder(self, name: str, edit_field: QLineEdit) -> None:
        dlg = MacroRecorderDialog(edit_field, self)
        dlg.exec()

    def _open_macro_editor(self, name: str, edit_field: QLineEdit) -> None:
        dlg = MacroEditorDialog(name, edit_field, self)
        dlg.exec()

    def _on_save_all(self) -> None:
        self._sync_ui_to_profile()
        save_profile(self.active_profile)

        # Update global config
        self.global_cfg["active_profile"] = self.active_profile.name
        self.global_cfg["auto_switch"] = self.auto_switch_cb.isChecked()
        self.global_cfg["start_minimized"] = self.minimized_cb.isChecked()
        self.global_cfg["load_on_startup"] = self.startup_cb.isChecked()
        self.global_cfg["osd_position"] = self.osd_combo.currentText()
        self.global_cfg["scan_interval_ms"] = self.scan_combo.currentData()
        save_global_config(self.global_cfg)

        self._update_startup_registry(self.startup_cb.isChecked())
        self.status_bar.showMessage("Settings and profile successfully saved & applied!", 4000)
        show_osd(f"Saved: {self.active_profile.name}", corner=self.osd_combo.currentText())

    def _update_startup_registry(self, enable: bool) -> None:
        """Configures Windows Run registry key for launch on login."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    if getattr(sys, "frozen", False):
                        val = f'"{sys.executable}"'
                    else:
                        venv_pythonw = Path(sys.executable).parent / "pythonw.exe"
                        exe_path = str(venv_pythonw) if venv_pythonw.exists() else sys.executable
                        script_path = str(Path(__file__).resolve().parent.parent / "main.py")
                        val = f'"{exe_path}" "{script_path}"'
                    winreg.SetValueEx(key, "ShadowLink", 0, winreg.REG_SZ, val)
                else:
                    try:
                        winreg.DeleteValue(key, "ShadowLink")
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logger.warning(f"Could not update startup registry: {e}")

    def _on_create_desktop_shortcut(self) -> None:
        """Handler for manually creating or refreshing the Desktop shortcut."""
        try:
            shortcut_path = create_desktop_shortcut()
            self.shortcut_status_lbl.setText(f"Shortcut created: {shortcut_path.name}")
            self.status_bar.showMessage(f"Desktop shortcut created: {shortcut_path}", 5000)
            show_osd("Desktop Shortcut Created", corner=self.osd_combo.currentText())
            QMessageBox.information(
                self,
                "Desktop Shortcut Created",
                f"A shortcut with the custom ShadowLink icon has been placed on your Desktop:\n\n{shortcut_path}",
            )
        except Exception as e:
            logger.error(f"Failed to create desktop shortcut: {e}")
            QMessageBox.critical(self, "Shortcut Error", f"Could not create desktop shortcut:\n{e}")

    def _on_export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "ShadowLink_Diagnostic_Log.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"ShadowLink Diagnostic Export\n")
                f.write(f"Active Profile: {self.active_profile.name}\n")
                f.write(f"Dongle: {self.status_widget.dongle_label.text()}\n")
                f.write(f"Controller: {self.status_widget.ctrl_label.text()}\n")
            QMessageBox.information(self, "Log Exported", f"Log saved to:\n{path}")

    # --- THEME & EVENT HANDLING ---

    def _on_toggle_theme(self) -> None:
        curr_dark = getattr(self, "_forced_dark", is_windows_dark_mode())
        new_dark = not curr_dark
        self._forced_dark = new_dark
        self.apply_theme(new_dark)

    def apply_theme(self, is_dark: bool) -> None:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_fluent_stylesheet(is_dark))

    # --- SYSTEM TRAY ---

    def _init_system_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("ShadowLink - ASUS ROG Controller Remapper")

        menu = QMenu()
        open_action = QAction("Open ShadowLink", self)
        open_action.triggered.connect(self._restore_from_tray)
        menu.addAction(open_action)
        menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.hide()
                self.tray_icon.showMessage(
                    "ShadowLink",
                    "ShadowLink is running in the background.",
                    QSystemTrayIcon.Information,
                    2000
                )
        super().changeEvent(event)

    # --- HARDWARE & AUTOSWITCH BRIDGES ---

    def _start_auto_switcher(self) -> None:
        if self.auto_switcher:
            self.auto_switcher.stop()

        self.auto_switcher = AutoSwitchWatchdog(
            profiles_provider=lambda: self.all_profiles,
            active_profile_provider=lambda: self.active_profile,
            switch_profile_callback=lambda p: self.bridge.auto_switched.emit(p),
        )
        self.auto_switcher.start()

    def _on_auto_switch_toggled(self, checked: bool) -> None:
        if checked:
            self._start_auto_switcher()
        else:
            if self.auto_switcher:
                self.auto_switcher.stop()
                self.auto_switcher = None

    @Slot(object, str, object, str)
    def _on_status_updated(self, dongle_s: DeviceStatus, dongle_d: str, ctrl_s: DeviceStatus, ctrl_d: str) -> None:
        self.status_widget.update_dongle_status(dongle_s, dongle_d)
        self.status_widget.update_controller_status(ctrl_s, ctrl_d)

    @Slot(int, str)
    def _on_layer_changed(self, layer_num: int, layer_name: str) -> None:
        self.status_bar.showMessage(f"Switched to Layer {layer_num}: {layer_name}", 3000)
        show_osd(f"Layer {layer_num}: {layer_name}", corner=self.osd_combo.currentText())

    @Slot(str, bool, bool)
    def _on_paddle_event(self, name: str, raw: bool, debounced: bool) -> None:
        if debounced:
            self.status_bar.showMessage(f"Paddle Pressed: {name}", 1500)

    @Slot(object)
    def _on_auto_switched(self, new_profile: Profile) -> None:
        self._load_profile_into_ui(new_profile)
        self.profile_combo.setCurrentText(new_profile.name)
        show_osd(f"Profile: {new_profile.name}", corner=self.osd_combo.currentText())
