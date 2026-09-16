package com.retholtz.shadowlink

import java.awt.event.InputEvent
import java.awt.event.KeyEvent

// --- KEY MAPPING ---

val SUPPORTED_KEYS = arrayOf(
    "LClick", "RClick", "MClick",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace",
    "ESC", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "F13", "F14", "F15", "F16", "F17", "F18", "F19", "F20", "F21", "F22", "F23", "F24",
    "Insert", "Home", "Page Up", "Delete", "End", "Page Down",
    "Space", "Enter", "Tab", "Up", "Down", "Left", "Right",
    ",", ".", "/", "\\", ";", "'", "[", "]",
    "NumPad 0", "NumPad 1", "NumPad 2", "NumPad 3", "NumPad 4", "NumPad 5", "NumPad 6", "NumPad 7", "NumPad 8", "NumPad 9",
    "NumPad /", "NumPad *", "NumPad -", "NumPad +", "NumPad .", "NumPad Enter"
)

val KEY_MAP = mapOf(
    "A" to KeyEvent.VK_A, "B" to KeyEvent.VK_B, "C" to KeyEvent.VK_C, "D" to KeyEvent.VK_D, "E" to KeyEvent.VK_E,
    "F" to KeyEvent.VK_F, "G" to KeyEvent.VK_G, "H" to KeyEvent.VK_H, "I" to KeyEvent.VK_I, "J" to KeyEvent.VK_J,
    "K" to KeyEvent.VK_K, "L" to KeyEvent.VK_L, "M" to KeyEvent.VK_M, "N" to KeyEvent.VK_N, "O" to KeyEvent.VK_O,
    "P" to KeyEvent.VK_P, "Q" to KeyEvent.VK_Q, "R" to KeyEvent.VK_R, "S" to KeyEvent.VK_S, "T" to KeyEvent.VK_T,
    "U" to KeyEvent.VK_U, "V" to KeyEvent.VK_V, "W" to KeyEvent.VK_W, "X" to KeyEvent.VK_X, "Y" to KeyEvent.VK_Y, "Z" to KeyEvent.VK_Z,
    "0" to KeyEvent.VK_0, "1" to KeyEvent.VK_1, "2" to KeyEvent.VK_2, "3" to KeyEvent.VK_3, "4" to KeyEvent.VK_4,
    "5" to KeyEvent.VK_5, "6" to KeyEvent.VK_6, "7" to KeyEvent.VK_7, "8" to KeyEvent.VK_8, "9" to KeyEvent.VK_9,
    "F1" to KeyEvent.VK_F1, "F2" to KeyEvent.VK_F2, "F3" to KeyEvent.VK_F3, "F4" to KeyEvent.VK_F4,
    "F5" to KeyEvent.VK_F5, "F6" to KeyEvent.VK_F6, "F7" to KeyEvent.VK_F7, "F8" to KeyEvent.VK_F8,
    "F9" to KeyEvent.VK_F9, "F10" to KeyEvent.VK_F10, "F11" to KeyEvent.VK_F11, "F12" to KeyEvent.VK_F12,
    "F13" to KeyEvent.VK_F13, "F14" to KeyEvent.VK_F14, "F15" to KeyEvent.VK_F15, "F16" to KeyEvent.VK_F16,
    "F17" to KeyEvent.VK_F17, "F18" to KeyEvent.VK_F18, "F19" to KeyEvent.VK_F19, "F20" to KeyEvent.VK_F20,
    "F21" to KeyEvent.VK_F21, "F22" to KeyEvent.VK_F22, "F23" to KeyEvent.VK_F23, "F24" to KeyEvent.VK_F24,
    "Insert" to KeyEvent.VK_INSERT, "Delete" to KeyEvent.VK_DELETE, "Home" to KeyEvent.VK_HOME, "End" to KeyEvent.VK_END,
    "Page Up" to KeyEvent.VK_PAGE_UP, "Page Down" to KeyEvent.VK_PAGE_DOWN,
    "Space" to KeyEvent.VK_SPACE, "Enter" to KeyEvent.VK_ENTER, "Tab" to KeyEvent.VK_TAB, "ESC" to KeyEvent.VK_ESCAPE, "Backspace" to KeyEvent.VK_BACK_SPACE,
    "Up" to KeyEvent.VK_UP, "Down" to KeyEvent.VK_DOWN, "Left" to KeyEvent.VK_LEFT, "Right" to KeyEvent.VK_RIGHT,
    "-" to KeyEvent.VK_MINUS, "=" to KeyEvent.VK_EQUALS, "," to KeyEvent.VK_COMMA, "." to KeyEvent.VK_PERIOD,
    "/" to KeyEvent.VK_SLASH, "\\" to KeyEvent.VK_BACK_SLASH, ";" to KeyEvent.VK_SEMICOLON,
    "'" to KeyEvent.VK_QUOTE, "[" to KeyEvent.VK_OPEN_BRACKET, "]" to KeyEvent.VK_CLOSE_BRACKET,
    "`" to KeyEvent.VK_BACK_QUOTE, "Shift" to KeyEvent.VK_SHIFT, "Ctrl" to KeyEvent.VK_CONTROL, "Alt" to KeyEvent.VK_ALT, "Win" to KeyEvent.VK_WINDOWS,
    "NumPad 0" to KeyEvent.VK_NUMPAD0, "NumPad 1" to KeyEvent.VK_NUMPAD1, "NumPad 2" to KeyEvent.VK_NUMPAD2,
    "NumPad 3" to KeyEvent.VK_NUMPAD3, "NumPad 4" to KeyEvent.VK_NUMPAD4, "NumPad 5" to KeyEvent.VK_NUMPAD5,
    "NumPad 6" to KeyEvent.VK_NUMPAD6, "NumPad 7" to KeyEvent.VK_NUMPAD7, "NumPad 8" to KeyEvent.VK_NUMPAD8,
    "NumPad 9" to KeyEvent.VK_NUMPAD9, "NumPad /" to KeyEvent.VK_DIVIDE, "NumPad *" to KeyEvent.VK_MULTIPLY,
    "NumPad -" to KeyEvent.VK_SUBTRACT, "NumPad +" to KeyEvent.VK_ADD, "NumPad ." to KeyEvent.VK_DECIMAL,
    "NumPad Enter" to KeyEvent.VK_ENTER
)

fun getKeyCode(key: String): Int? {
    return KEY_MAP[key] ?: KEY_MAP.entries.find { it.key.equals(key, ignoreCase = true) }?.value
}

fun getMouseMask(key: String): Int {
    return when (key.lowercase()) {
        "lclick" -> InputEvent.BUTTON1_DOWN_MASK
        "mclick" -> InputEvent.BUTTON2_DOWN_MASK
        "rclick" -> InputEvent.BUTTON3_DOWN_MASK
        else -> 0
    }
}