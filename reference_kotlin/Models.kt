package com.retholtz.shadowlink

import java.awt.Robot

// --- DATA STRUCTURES ---

data class PaddleBind(
    var enabled: Boolean = true,
    var isMacro: Boolean = false,
    var repeatMacro: Boolean = false,
    var stepThrough: Boolean = false,
    var macroText: String = "",
    var keyChar: String = "A",
    var shift: Boolean = false,
    var ctrl: Boolean = false,
    var alt: Boolean = false,
    var win: Boolean = false
)

data class LayerConfig(
    var name: String = "Layer",
    var enabled: Boolean = false,

    // Back Paddles
    val m1: PaddleBind = PaddleBind(keyChar = "3"),
    val m2: PaddleBind = PaddleBind(keyChar = "4"),
    val m3: PaddleBind = PaddleBind(keyChar = "5"),
    val m4: PaddleBind = PaddleBind(keyChar = "6"),
    val cmd: PaddleBind = PaddleBind(keyChar = "1"),
    val lib: PaddleBind = PaddleBind(keyChar = "2"),

    // Triggers & Face Buttons
    val lb: PaddleBind = PaddleBind(enabled = false),
    val rb: PaddleBind = PaddleBind(enabled = false),
    val lt: PaddleBind = PaddleBind(enabled = false),
    val rt: PaddleBind = PaddleBind(enabled = false),
    val a: PaddleBind = PaddleBind(enabled = false),
    val b: PaddleBind = PaddleBind(enabled = false),
    val x: PaddleBind = PaddleBind(enabled = false),
    val y: PaddleBind = PaddleBind(enabled = false),
    val l3: PaddleBind = PaddleBind(enabled = false),
    val r3: PaddleBind = PaddleBind(enabled = false),
    val dUp: PaddleBind = PaddleBind(enabled = false),
    val dDown: PaddleBind = PaddleBind(enabled = false),
    val dLeft: PaddleBind = PaddleBind(enabled = false),
    val dRight: PaddleBind = PaddleBind(enabled = false),

    // Combo Binds (Disabled by default)
    val m1_m2: PaddleBind = PaddleBind(enabled = false),
    val m1_m3: PaddleBind = PaddleBind(enabled = false),
    val m1_m4: PaddleBind = PaddleBind(enabled = false),
    val m2_m3: PaddleBind = PaddleBind(enabled = false),
    val m2_m4: PaddleBind = PaddleBind(enabled = false),
    val m3_m4: PaddleBind = PaddleBind(enabled = false),
    val cmd_lib: PaddleBind = PaddleBind(enabled = false)
)

data class Profile(
    var name: String = "Default",
    var targetProcess: String = "",
    var toggleButton1: String = "None",
    var toggleButton2: String = "None",
    var comboBufferMs: Int = 30,
    val layers: List<LayerConfig> = listOf(
        LayerConfig("Layer 1", true),
        LayerConfig("Layer 2", false),
        LayerConfig("Layer 3", false),
        LayerConfig("Layer 4", false),
        LayerConfig("Layer 5", false)
    )
)

class ButtonState(
    @Volatile var pressed: Boolean = false,
    @Volatile var macroThread: Thread? = null,
    @Volatile var stepIndex: Int = 0,
    @Volatile var activeBind: PaddleBind? = null,
    @Volatile var singleActionFired: Boolean = false,
    @Volatile var comboConsumed: Boolean = false,
    var pendingTask: java.util.TimerTask? = null
) {
    @Synchronized
    fun cancelPending() {
        pendingTask?.cancel()
        pendingTask = null
    }

    @Synchronized
    fun fire(robot: Robot, bind: PaddleBind) {
        macroThread?.interrupt()
        activeBind = bind
        if (bind.isMacro) {
            if (bind.stepThrough) executeMacroStep(robot, bind, this)
            else macroThread = executeMacro(robot, bind, this)
        } else {
            pressKeyBind(robot, bind)
        }
    }

    @Synchronized
    fun releaseIfActive(robot: Robot) {
        val releaseTarget = this.activeBind
        if (releaseTarget != null && releaseTarget.enabled) {
            if (releaseTarget.isMacro) {
                if (releaseTarget.repeatMacro) {
                    this.macroThread = null
                }
            } else {
                releaseKeyBind(robot, releaseTarget)
            }
        }
        this.activeBind = null
    }

    @Synchronized
    fun cancelAndRelease(robot: Robot) {
        cancelPending()
        releaseIfActive(robot)
        pressed = false
    }
}