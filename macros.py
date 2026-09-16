"""
Macro parsing and execution engine for ShadowLink.
Supports delays (static and randomized), mouse coordinates (abs and delta),
key/mouse hold and tap actions, repeating macros, and step-through execution.
"""

from __future__ import annotations
import logging
import random
import re
import threading
import time
from typing import TYPE_CHECKING, Optional

import keymap
from keymap import (
    get_key_info,
    is_mouse_key,
    send_key_down,
    send_key_up,
    send_mouse_abs,
    send_mouse_delta,
    send_mouse_down,
    send_mouse_up,
)

if TYPE_CHECKING:
    from models import ButtonState, PaddleBind

logger = logging.getLogger("ShadowLink.Macros")

# Regex to detect compound delay followed by action e.g. "350ms. MClick" or "350ms MClick"
_COMPOUND_REGEX = re.compile(
    r"^(\d+(?:\.\d+)?(?:ms|s)?)(?:\s*\.\s*|\s+)([a-zA-Z_].*)$",
    re.IGNORECASE
)


def parse_macro_text(macro_text: str) -> list[str]:
    """
    Splits macro text by commas and semicolons, expanding compound delay+action tokens.
    Matches Kotlin parseMacroText.
    """
    if not macro_text:
        return []

    result: list[str] = []
    raw_tokens = [t.strip() for t in re.split(r"[,;]", macro_text) if t.strip()]

    for raw in raw_tokens:
        match = _COMPOUND_REGEX.match(raw)
        if match:
            result.append(match.group(1).strip())
            result.append(match.group(2).strip())
        else:
            result.append(raw)

    return result


def is_delay_token(token: str) -> bool:
    """Check if token is a delay (ms, s, or range ~)."""
    t = token.strip().lower()
    if "~" in t:
        return True
    if t.endswith("ms"):
        num_str = t[:-2].strip()
        try:
            float(num_str)
            return True
        except ValueError:
            return False
    if t.endswith("s") and not (t.endswith(" down") or t.endswith(" up")):
        num_str = t[:-1].strip()
        try:
            float(num_str)
            return True
        except ValueError:
            return False
    return False


def _parse_delay_seconds(token: str) -> Optional[float]:
    """Parse delay in seconds from token, handling random ranges and static units."""
    t = token.strip().lower()

    # Dynamic range e.g. "50ms~150ms", "50~150ms", "0.1s~0.5s"
    if "~" in t:
        parts = t.split("~")
        if len(parts) == 2:
            p0 = parts[0].strip()
            p1 = parts[1].strip()

            is_seconds = p0.endswith("s") and not p0.endswith("ms") or p1.endswith("s") and not p1.endswith("ms")

            s0 = p0.rstrip("ms").rstrip("s").strip()
            s1 = p1.rstrip("ms").rstrip("s").strip()
            try:
                val0 = float(s0)
                val1 = float(s1)
                low = min(val0, val1)
                high = max(val0, val1)
                chosen = random.uniform(low, high)
                return chosen if is_seconds else (chosen / 1000.0)
            except ValueError:
                return None

    # Static delays
    if t.endswith("ms"):
        s = t[:-2].strip()
        try:
            ms = float(s)
            return max(0.0, ms / 1000.0)
        except ValueError:
            return None

    if t.endswith("s") and not (t.endswith(" down") or t.endswith(" up")):
        s = t[:-1].strip()
        try:
            sec = float(s)
            return max(0.0, sec)
        except ValueError:
            return None

    return None


def process_macro_token(
    token: str,
    pressed_keys: set[str],
    pressed_mouse: set[str],
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    Process an individual macro token (delay, mouse position, key/mouse press/tap).
    Matches Kotlin processMacroToken.
    """
    t = token.strip()
    if not t:
        return
    if stop_event is not None and stop_event.is_set():
        return

    # 1. Delays
    delay_sec = _parse_delay_seconds(t)
    if delay_sec is not None:
        if delay_sec > 0:
            if stop_event is not None:
                stop_event.wait(delay_sec)
            else:
                time.sleep(delay_sec)
        return

    # 2. Mouse Absolute and Delta
    parts = t.split()
    if len(parts) >= 3 and parts[0].lower() == "mouseabs":
        try:
            x = int(parts[1])
            y = int(parts[2])
            send_mouse_abs(x, y)
        except ValueError:
            pass
        return

    if len(parts) >= 3 and parts[0].lower() == "mousedelta":
        try:
            dx = int(parts[1])
            dy = int(parts[2])
            send_mouse_delta(dx, dy)
        except ValueError:
            pass
        return

    # 3. Key and Mouse actions: [Key] down, [Key] up, [Key] (tap)
    t_lower = t.lower()
    if t_lower.endswith(" down"):
        act = "down"
        key_str = t[:-5].strip()
    elif t_lower.endswith(" up"):
        act = "up"
        key_str = t[:-3].strip()
    else:
        act = "tap"
        key_str = t

    if key_str.lower().startswith("xbox_"):
        return

    info = get_key_info(key_str)
    if not info:
        logger.warning(f"Unrecognized macro key token: '{key_str}'")
        return

    if info.is_mouse:
        if act == "down":
            send_mouse_down(key_str)
            pressed_mouse.add(key_str)
        elif act == "up":
            send_mouse_up(key_str)
            pressed_mouse.discard(key_str)
        else:  # TAP
            send_mouse_down(key_str)
            pressed_mouse.add(key_str)
            if stop_event is not None:
                stop_event.wait(0.05)
            else:
                time.sleep(0.05)
            send_mouse_up(key_str)
            pressed_mouse.discard(key_str)
    else:
        if act == "down":
            send_key_down(key_str)
            pressed_keys.add(key_str)
        elif act == "up":
            send_key_up(key_str)
            pressed_keys.discard(key_str)
        else:  # TAP
            send_key_down(key_str)
            pressed_keys.add(key_str)
            if stop_event is not None:
                stop_event.wait(0.05)
            else:
                time.sleep(0.05)
            send_key_up(key_str)
            pressed_keys.discard(key_str)


def execute_macro(
    bind: PaddleBind,
    state: ButtonState,
) -> tuple[threading.Thread, threading.Event]:
    """
    Spawns background worker thread to execute the macro.
    Returns (thread, stop_event).
    """
    stop_event = threading.Event()

    def run_worker() -> None:
        pressed_keys: set[str] = set()
        pressed_mouse: set[str] = set()
        try:
            while not stop_event.is_set():
                tokens = parse_macro_text(bind.macro_text)
                for token in tokens:
                    if stop_event.is_set():
                        break
                    process_macro_token(token, pressed_keys, pressed_mouse, stop_event)

                if not bind.repeat_macro:
                    break
        except Exception as e:
            logger.error(f"Error in macro thread: {e}", exc_info=True)
        finally:
            # Clean up any keys or mouse buttons held down by the macro
            for k in list(pressed_keys):
                try:
                    send_key_up(k)
                except Exception:
                    pass
            for m in list(pressed_mouse):
                try:
                    send_mouse_up(m)
                except Exception:
                    pass

    thread = threading.Thread(
        target=run_worker,
        name=f"ShadowLink-Macro-{bind.key_char}",
        daemon=True,
    )
    thread.start()
    return thread, stop_event


def execute_macro_step(bind: PaddleBind, state: ButtonState) -> None:
    """
    Executes a single step in step-through macro mode, advancing step_index.
    Ignores delay tokens.
    """
    tokens = [t for t in parse_macro_text(bind.macro_text) if not is_delay_token(t)]
    if not tokens:
        return

    def step_worker() -> None:
        with state._lock:
            try:
                token = tokens[state.step_index % len(tokens)]
                pressed_keys: set[str] = set()
                pressed_mouse: set[str] = set()

                process_macro_token(token, pressed_keys, pressed_mouse)

                # If the step was a tap, clean up happened, but if down/up,
                # we don't leave down stranded indefinitely
                state.step_index = (state.step_index + 1) % len(tokens)
            except Exception as e:
                logger.error(f"Error in step macro: {e}", exc_info=True)

    thread = threading.Thread(target=step_worker, daemon=True)
    thread.start()

