"""
Data models for ShadowLink profiles, layers, paddle bindings, and runtime button states.
Ported from Models.kt with support for Python dataclasses and JSON serialization.
"""

from __future__ import annotations
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class DeviceStatus(str, Enum):
    DISCONNECTED = "Disconnected"
    ERROR = "Error"
    CONNECTED = "Connected"


@dataclass
class PaddleBind:
    enabled: bool = True
    is_macro: bool = False
    repeat_macro: bool = False
    step_through: bool = False
    macro_text: str = ""
    key_char: str = "A"
    shift: bool = False
    ctrl: bool = False
    alt: bool = False
    win: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "is_macro": self.is_macro,
            "repeat_macro": self.repeat_macro,
            "step_through": self.step_through,
            "macro_text": self.macro_text,
            "key_char": self.key_char,
            "shift": self.shift,
            "ctrl": self.ctrl,
            "alt": self.alt,
            "win": self.win,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaddleBind:
        return cls(
            enabled=data.get("enabled", True),
            is_macro=data.get("is_macro", data.get("isMacro", False)),
            repeat_macro=data.get("repeat_macro", data.get("repeatMacro", False)),
            step_through=data.get("step_through", data.get("stepThrough", False)),
            macro_text=data.get("macro_text", data.get("macroText", "")),
            key_char=data.get("key_char", data.get("keyChar", "A")),
            shift=data.get("shift", False),
            ctrl=data.get("ctrl", False),
            alt=data.get("alt", False),
            win=data.get("win", False),
        )


@dataclass
class LayerConfig:
    name: str = "Layer"
    enabled: bool = False

    # Back Paddles
    m1: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="3"))
    m2: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="4"))
    m3: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="5"))
    m4: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="6"))
    cmd: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="1"))
    lib: PaddleBind = field(default_factory=lambda: PaddleBind(key_char="2"))

    # Triggers & Face Buttons
    lb: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_LB"))
    rb: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_RB"))
    lt: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_LT"))
    rt: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_RT"))
    a: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_A"))
    b: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_B"))
    x: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_X"))
    y: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_Y"))
    l3: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_L3"))
    r3: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_R3"))
    d_up: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_DUp"))
    d_down: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_DDown"))
    d_left: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_DLeft"))
    d_right: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False, key_char="Xbox_DRight"))

    # Combo Binds (Disabled by default)
    m1_m2: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    m1_m3: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    m1_m4: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    m2_m3: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    m2_m4: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    m3_m4: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))
    cmd_lib: PaddleBind = field(default_factory=lambda: PaddleBind(enabled=False))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "enabled": self.enabled,
        }
        for attr in [
            "m1", "m2", "m3", "m4", "cmd", "lib",
            "lb", "rb", "lt", "rt", "a", "b", "x", "y",
            "l3", "r3", "d_up", "d_down", "d_left", "d_right",
            "m1_m2", "m1_m3", "m1_m4", "m2_m3", "m2_m4", "m3_m4", "cmd_lib"
        ]:
            bind_obj = getattr(self, attr)
            result[attr] = bind_obj.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerConfig:
        config = cls(
            name=data.get("name", "Layer"),
            enabled=data.get("enabled", False),
        )
        field_map = {
            "m1": "m1", "m2": "m2", "m3": "m3", "m4": "m4", "cmd": "cmd", "lib": "lib",
            "lb": "lb", "rb": "rb", "lt": "lt", "rt": "rt", "a": "a", "b": "b",
            "x": "x", "y": "y", "l3": "l3", "r3": "r3",
            "d_up": "d_up", "dUp": "d_up",
            "d_down": "d_down", "dDown": "d_down",
            "d_left": "d_left", "dLeft": "d_left",
            "d_right": "d_right", "dRight": "d_right",
            "m1_m2": "m1_m2", "m1M2": "m1_m2",
            "m1_m3": "m1_m3", "m1M3": "m1_m3",
            "m1_m4": "m1_m4", "m1M4": "m1_m4",
            "m2_m3": "m2_m3", "m2M3": "m2_m3",
            "m2_m4": "m2_m4", "m2M4": "m2_m4",
            "m3_m4": "m3_m4", "m3M4": "m3_m4",
            "cmd_lib": "cmd_lib", "cmdLib": "cmd_lib",
        }
        for key, val in data.items():
            if key in field_map and isinstance(val, dict):
                setattr(config, field_map[key], PaddleBind.from_dict(val))
        return config


def create_default_layers() -> list[LayerConfig]:
    return [
        LayerConfig("Layer 1", enabled=True),
        LayerConfig("Layer 2", enabled=False),
        LayerConfig("Layer 3", enabled=False),
        LayerConfig("Layer 4", enabled=False),
        LayerConfig("Layer 5", enabled=False),
    ]


@dataclass
class Profile:
    name: str = "Default"
    target_process: str = ""
    toggle_button1: str = "None"
    toggle_button2: str = "None"
    combo_buffer_ms: int = 30
    layers: list[LayerConfig] = field(default_factory=create_default_layers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_process": self.target_process,
            "toggle_button1": self.toggle_button1,
            "toggle_button2": self.toggle_button2,
            "combo_buffer_ms": self.combo_buffer_ms,
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        layers_raw = data.get("layers", [])
        if layers_raw:
            layers = [LayerConfig.from_dict(l) for l in layers_raw]
        else:
            layers = create_default_layers()

        return cls(
            name=data.get("name", "Default"),
            target_process=data.get("target_process", data.get("targetProcess", "")),
            toggle_button1=data.get("toggle_button1", data.get("toggleButton1", "None")),
            toggle_button2=data.get("toggle_button2", data.get("toggleButton2", "None")),
            combo_buffer_ms=int(data.get("combo_buffer_ms", data.get("comboBufferMs", 30))),
            layers=layers,
        )


class ButtonState:
    """
    Thread-safe tracker for physical and logical button states,
    debouncing, and macro lifecycle.
    """

    def __init__(self) -> None:
        self.pressed: bool = False
        self.macro_thread: Optional[threading.Thread] = None
        self.stop_macro_event: Optional[threading.Event] = None
        self.step_index: int = 0
        self.active_bind: Optional[PaddleBind] = None
        self.single_action_fired: bool = False
        self.combo_consumed: bool = False
        self.pending_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()

    def cancel_pending(self) -> None:
        with self._lock:
            if self.pending_timer is not None:
                self.pending_timer.cancel()
                self.pending_timer = None

    def fire(
        self,
        bind: PaddleBind,
        press_action_fn: Optional[Callable[[PaddleBind], None]] = None,
        macro_exec_fn: Optional[Callable[[PaddleBind, ButtonState], tuple[threading.Thread, threading.Event]]] = None,
        step_exec_fn: Optional[Callable[[PaddleBind, ButtonState], None]] = None,
    ) -> None:
        with self._lock:
            if self.stop_macro_event is not None:
                self.stop_macro_event.set()
                self.stop_macro_event = None
            self.macro_thread = None

            self.active_bind = bind
            if bind.is_macro:
                if bind.step_through:
                    if step_exec_fn:
                        step_exec_fn(bind, self)
                else:
                    if macro_exec_fn:
                        thread, stop_evt = macro_exec_fn(bind, self)
                        self.macro_thread = thread
                        self.stop_macro_event = stop_evt
            else:
                if press_action_fn:
                    press_action_fn(bind)

    def release_if_active(
        self,
        release_action_fn: Optional[Callable[[PaddleBind], None]] = None,
    ) -> None:
        with self._lock:
            target = self.active_bind
            if target is not None and target.enabled:
                if target.is_macro:
                    if target.repeat_macro:
                        if self.stop_macro_event is not None:
                            self.stop_macro_event.set()
                            self.stop_macro_event = None
                        self.macro_thread = None
                else:
                    if release_action_fn:
                        release_action_fn(target)
            self.active_bind = None

    def cancel_and_release(
        self,
        release_action_fn: Optional[Callable[[PaddleBind], None]] = None,
    ) -> None:
        with self._lock:
            self.cancel_pending()
            self.release_if_active(release_action_fn)
            self.pressed = False

