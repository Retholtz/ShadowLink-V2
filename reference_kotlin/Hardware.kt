package com.retholtz.shadowlink

import com.sun.jna.Native
import com.sun.jna.Structure
import com.sun.jna.win32.StdCallLibrary
import com.sun.jna.win32.W32APIOptions
import org.hid4java.HidDevice
import org.hid4java.HidManager
import org.hid4java.HidServicesListener
import org.hid4java.HidServicesSpecification
import org.hid4java.ScanMode
import org.hid4java.event.HidServicesEvent
import org.hid4java.jna.HidApi
import org.hid4java.jna.HidDeviceInfoStructure
import java.awt.MouseInfo
import java.awt.Robot
import java.awt.event.KeyEvent
import javax.swing.SwingUtilities
import kotlin.random.Random

// --- XINPUT JNA BINDINGS ---
interface XInputLibrary : StdCallLibrary {
    companion object {
        val INSTANCE: XInputLibrary? = try {
            Native.load("xinput1_4", XInputLibrary::class.java, W32APIOptions.DEFAULT_OPTIONS)
        } catch (e: Exception) {
            try { Native.load("xinput9_1_0", XInputLibrary::class.java, W32APIOptions.DEFAULT_OPTIONS) } catch (e2: Exception) { null }
        }
    }

    @Structure.FieldOrder("wButtons", "bLeftTrigger", "bRightTrigger", "sThumbLX", "sThumbLY", "sThumbRX", "sThumbRY")
    open class XINPUT_GAMEPAD : Structure() {
        @JvmField var wButtons: Short = 0
        @JvmField var bLeftTrigger: Byte = 0
        @JvmField var bRightTrigger: Byte = 0
        @JvmField var sThumbLX: Short = 0
        @JvmField var sThumbLY: Short = 0
        @JvmField var sThumbRX: Short = 0
        @JvmField var sThumbRY: Short = 0
    }

    @Structure.FieldOrder("dwPacketNumber", "Gamepad")
    open class XINPUT_STATE : Structure() {
        @JvmField var dwPacketNumber: Int = 0
        @JvmField var Gamepad: XINPUT_GAMEPAD = XINPUT_GAMEPAD()
    }

    fun XInputGetState(dwUserIndex: Int, pState: XINPUT_STATE): Int
}

// --- STATUS MONITORING (USB DONGLE & CONTROLLER LINK) ---
enum class DeviceStatus(val label: String, val color: java.awt.Color) {
    DISCONNECTED("Disconnected", java.awt.Color(220, 53, 69)),  // Red
    ERROR("Error", java.awt.Color(255, 193, 7)),               // Yellow
    CONNECTED("Connected", java.awt.Color(40, 167, 69))         // Green
}

@Volatile var usbDongleStatus: DeviceStatus = DeviceStatus.DISCONNECTED
@Volatile var usbDongleDetails: String = "USB Dongle unplugged"

@Volatile var controllerLinkStatus: DeviceStatus = DeviceStatus.DISCONNECTED
@Volatile var controllerLinkDetails: String = "Controller turned off or sleeping"

var onStatusUpdated: (() -> Unit)? = null

@Volatile var lastHidDataTime = 0L
@Volatile var lastXInputDataTime = 0L
@Volatile var lastDongleSeenTime = 0L
@Volatile var lastConnectionError: String? = null

fun updateUsbDongleStatus(status: DeviceStatus, details: String) {
    if (usbDongleStatus != status || usbDongleDetails != details) {
        usbDongleStatus = status
        usbDongleDetails = details
        Logger.info("USB Dongle Status: $status ($details)")
        SwingUtilities.invokeLater { onStatusUpdated?.invoke() }
    }
}

fun updateControllerLinkStatus(status: DeviceStatus, details: String) {
    if (controllerLinkStatus != status || controllerLinkDetails != details) {
        controllerLinkStatus = status
        controllerLinkDetails = details
        Logger.info("Controller Link Status: $status ($details)")
        SwingUtilities.invokeLater { onStatusUpdated?.invoke() }
    }
}

// --- CONTROLLER POLLING ---
fun findRaikiriHidDevices(): List<HidDevice> {
    val devices = mutableListOf<HidDevice>()
    val root = try {
        HidApi.enumerateDevices(0x0B05, 0)
    } catch (e: Exception) {
        null
    }
    if (root != null) {
        var curr: HidDeviceInfoStructure? = root
        while (curr != null) {
            devices.add(HidDevice(curr, null))
            curr = curr.next()
        }
        HidApi.freeEnumeration(root)
    }
    return devices
}

fun runControllerSniffer() {
    val spec = HidServicesSpecification().apply {
        scanMode = ScanMode.NO_SCAN
        scanInterval = 0
        isAutoStart = false
    }
    val hidServices = HidManager.getHidServices(spec)
    val robot = Robot().apply { isAutoWaitForIdle = false }

    // Start Dedicated XInput Thread for Standard Inputs (Triggers, Bumpers, Face, D-Pad)
    Thread {
        val xState = XInputLibrary.XINPUT_STATE()
        val standardStates = Array(14) { ButtonState() }

        while (true) {
            val xInput = XInputLibrary.INSTANCE
            if (xInput != null) {
                var wButtons = 0
                var ltVal = 0
                var rtVal = 0
                var anyConnected = false

                // Scan all 4 Xbox Player slots and merge the inputs.
                for (i in 0..3) {
                    val res = xInput.XInputGetState(i, xState)
                    if (res == 0) { // SUCCESS
                        anyConnected = true
                        wButtons = wButtons or (xState.Gamepad.wButtons.toInt() and 0xFFFF)
                        val lt = xState.Gamepad.bLeftTrigger.toInt() and 0xFF
                        val rt = xState.Gamepad.bRightTrigger.toInt() and 0xFF
                        if (lt > ltVal) ltVal = lt
                        if (rt > rtVal) rtVal = rt
                    }
                }

                if (anyConnected) {
                    lastXInputDataTime = System.currentTimeMillis()

                    val sLb = (wButtons and 0x0100) != 0
                    val sRb = (wButtons and 0x0200) != 0
                    val sLt = ltVal > 128
                    val sRt = rtVal > 128
                    val sA = (wButtons and 0x1000) != 0
                    val sB = (wButtons and 0x2000) != 0
                    val sX = (wButtons and 0x4000) != 0
                    val sY = (wButtons and 0x8000) != 0
                    val sL3 = (wButtons and 0x0040) != 0
                    val sR3 = (wButtons and 0x0080) != 0
                    val sDUp = (wButtons and 0x0001) != 0
                    val sDDown = (wButtons and 0x0002) != 0
                    val sDLeft = (wButtons and 0x0004) != 0
                    val sDRight = (wButtons and 0x0008) != 0

                    val cl = activeProfile.layers[activeLayer - 1]

                    fun checkStdState(s: Boolean, bs: ButtonState, bind: PaddleBind) {
                        if (s && !bs.pressed) {
                            bs.pressed = true
                            bs.singleActionFired = false
                            if (bind.enabled) {
                                bs.singleActionFired = true
                                bs.fire(robot, bind)
                            }
                        } else if (!s && bs.pressed) {
                            bs.cancelPending()
                            if (bind.enabled && !bs.singleActionFired) bs.fire(robot, bind)
                            bs.releaseIfActive(robot)
                            bs.pressed = false
                        }
                    }

                    checkStdState(sLb, standardStates[0], cl.lb)
                    checkStdState(sRb, standardStates[1], cl.rb)
                    checkStdState(sLt, standardStates[2], cl.lt)
                    checkStdState(sRt, standardStates[3], cl.rt)
                    checkStdState(sA, standardStates[4], cl.a)
                    checkStdState(sB, standardStates[5], cl.b)
                    checkStdState(sX, standardStates[6], cl.x)
                    checkStdState(sY, standardStates[7], cl.y)
                    checkStdState(sL3, standardStates[8], cl.l3)
                    checkStdState(sR3, standardStates[9], cl.r3)
                    checkStdState(sDUp, standardStates[10], cl.dUp)
                    checkStdState(sDDown, standardStates[11], cl.dDown)
                    checkStdState(sDLeft, standardStates[12], cl.dLeft)
                    checkStdState(sDRight, standardStates[13], cl.dRight)
                } else {
                    // Clear states if no XInput controllers are connected
                    standardStates.forEach { bs ->
                        if (bs.pressed) { bs.cancelPending(); bs.releaseIfActive(robot); bs.pressed = false }
                    }
                }
            } else {
                standardStates.forEach { bs -> if (bs.pressed) { bs.cancelPending(); bs.releaseIfActive(robot); bs.pressed = false } }
            }
            Thread.sleep(10)
        }
    }.start()

    val controllerListener = object : HidServicesListener {
        @Volatile var isConnected = false
        @Volatile var attachedRaikiri: HidDevice? = null
        var readingThread: Thread? = null

        override fun hidDeviceAttached(event: HidServicesEvent) {
            val device = event.hidDevice
            if (device.vendorId == 0x0B05) {
                attachedRaikiri = device
                Logger.info("HID Device attached: ${device.product} (VID: 0x${Integer.toHexString(device.vendorId)})")
                updateUsbDongleStatus(DeviceStatus.CONNECTED, "ROG Raikiri II USB Dongle plugged in")
                if (Integer.toHexString(device.usagePage).endsWith("c3")) {
                    startReading(device)
                }
            }
        }

        override fun hidDeviceDetached(event: HidServicesEvent) {
            val device = event.hidDevice
            if (device.vendorId == 0x0B05) {
                Logger.info("HID Device detached: ${device.product}")
                if (device == attachedRaikiri) {
                    attachedRaikiri = null
                }
                if (Integer.toHexString(device.usagePage).endsWith("c3")) {
                    isConnected = false
                    readingThread?.interrupt()
                }
            }
        }

        override fun hidFailure(event: HidServicesEvent) {
            val device = event.hidDevice
            if (device?.vendorId == 0x0B05) {
                val deviceName = device.product ?: "Unknown Device"
                val msg = "HID Failure detected on device: $deviceName"
                Logger.error(msg)
                lastConnectionError = msg
                updateUsbDongleStatus(DeviceStatus.ERROR, msg)
            }
        }

        @Synchronized
        fun startReading(raikiri: HidDevice) {
            if (isConnected) return
            Logger.info("Attempting to open ROG Raikiri II HID device...")
            if (raikiri.open()) {
                isConnected = true
                lastConnectionError = null
                Logger.info("ROG Raikiri II HID device successfully opened")

                // Pause USB bus polling while connected to prevent crashing other peripherals
                hidServices.stop()

                readingThread = Thread {
                    val actionTimer = java.util.Timer("ShadowLink-ActionTimer", true)

                    val m1State = ButtonState(); val m2State = ButtonState()
                    val m3State = ButtonState(); val m4State = ButtonState()
                    val cmdState = ButtonState(); val libState = ButtonState()

                    val m1m2State = ButtonState(); val m1m3State = ButtonState()
                    val m1m4State = ButtonState(); val m2m3State = ButtonState()
                    val m2m4State = ButtonState(); val m3m4State = ButtonState()
                    val cmdLibState = ButtonState()

                    var wasToggleTriggered = false

                    // Physical Input State Variables
                    var s1 = false; var s2 = false; var s3 = false; var s4 = false
                    var sCmd = false; var sLib = false

                    // Last High Timestamps
                    var lastM1Time = 0L; var lastM2Time = 0L
                    var lastM3Time = 0L; var lastM4Time = 0L
                    var lastCmdTime = 0L; var lastLibTime = 0L

                    try {
                        while (isConnected) {
                            try {
                                val data = ByteArray(64)
                                // Rapid non-blocking 10ms read allowing continuous off-delay checks
                                val read = raikiri.read(data, 10)

                                if (read > 0 && (data[0].toInt() and 0xFF) == 0xB3) {
                                    lastHidDataTime = System.currentTimeMillis()
                                    val isAltMode = data[3].toInt() == 2

                                    s1 = !isAltMode && data[8].toInt() == 1
                                    s2 = !isAltMode && data[6].toInt() == 1
                                    s3 = !isAltMode && data[5].toInt() == 1
                                    s4 = !isAltMode && data[7].toInt() == 1

                                    sCmd = isAltMode && data[5].toInt() == 1
                                    sLib = isAltMode && data[6].toInt() == 1
                                } else if (read < 0) {
                                    isConnected = false
                                    raikiri.close()
                                    break
                                }

                                val p = activeProfile
                                val now = System.currentTimeMillis()
                                val offDelayMs = 20L // 20ms of microswitch bounce filtering on release

                                if (s1) lastM1Time = now
                                if (s2) lastM2Time = now
                                if (s3) lastM3Time = now
                                if (s4) lastM4Time = now
                                if (sCmd) lastCmdTime = now
                                if (sLib) lastLibTime = now

                                // Zero-input-lag eager press, cleanly debounced off-delay on release
                                val debouncedS1 = s1 || (now - lastM1Time < offDelayMs)
                                val debouncedS2 = s2 || (now - lastM2Time < offDelayMs)
                                val debouncedS3 = s3 || (now - lastM3Time < offDelayMs)
                                val debouncedS4 = s4 || (now - lastM4Time < offDelayMs)
                                val debouncedSCmd = sCmd || (now - lastCmdTime < offDelayMs)
                                val debouncedSLib = sLib || (now - lastLibTime < offDelayMs)

                                val states = mapOf(
                                    "M1" to debouncedS1,
                                    "M2" to debouncedS2,
                                    "M3" to debouncedS3,
                                    "M4" to debouncedS4,
                                    "Command" to debouncedSCmd,
                                    "Library" to debouncedSLib
                                )

                                val t1 = p.toggleButton1
                                val t2 = p.toggleButton2

                                val t1Pressed = if (t1 != "None") states[t1] == true else false
                                val t2Pressed = if (t2 != "None") states[t2] == true else false

                                val isSingleToggle = (t1 != "None" && t2 == "None") || (t1 == "None" && t2 != "None") || (t1 != "None" && t1 == t2)
                                val singleToggleBtn = if (t1 != "None") t1 else t2

                                val isComboTriggered = if (!isSingleToggle && t1 != "None" && t2 != "None") {
                                    t1Pressed && t2Pressed
                                } else if (isSingleToggle) {
                                    if (t1 != "None") t1Pressed else t2Pressed
                                } else {
                                    false
                                }

                                val consumed = mutableSetOf<String>()

                                if (isComboTriggered && !wasToggleTriggered) {
                                    wasToggleTriggered = true

                                    m1State.cancelAndRelease(robot); m2State.cancelAndRelease(robot)
                                    m3State.cancelAndRelease(robot); m4State.cancelAndRelease(robot)
                                    cmdState.cancelAndRelease(robot); libState.cancelAndRelease(robot)

                                    m1m2State.cancelAndRelease(robot); m1m3State.cancelAndRelease(robot)
                                    m1m4State.cancelAndRelease(robot); m2m3State.cancelAndRelease(robot)
                                    m2m4State.cancelAndRelease(robot); m3m4State.cancelAndRelease(robot)
                                    cmdLibState.cancelAndRelease(robot)

                                    val availableLayers = p.layers.mapIndexedNotNull { index, layer -> if (layer.enabled) index + 1 else null }
                                    if (availableLayers.isNotEmpty()) {
                                        val currentIndex = availableLayers.indexOf(activeLayer)
                                        activeLayer = if (currentIndex != -1 && currentIndex + 1 < availableLayers.size) {
                                            availableLayers[currentIndex + 1]
                                        } else {
                                            availableLayers[0]
                                        }
                                        showOSD(p.layers[activeLayer - 1].name)
                                    }
                                } else if (!isComboTriggered) {
                                    wasToggleTriggered = false
                                }

                                if (isComboTriggered) {
                                    if (t1 != "None") consumed.add(t1)
                                    if (t2 != "None") consumed.add(t2)
                                } else if (isSingleToggle && singleToggleBtn != "None") {
                                    consumed.add(singleToggleBtn)
                                }

                                val currentLayerConfig = p.layers[activeLayer - 1]

                                fun handleCombo(name1: String, sA: Boolean, name2: String, sB: Boolean, bs: ButtonState, bind: PaddleBind, stateA: ButtonState, stateB: ButtonState) {
                                    if (sA && sB && bind.enabled && !consumed.contains(name1) && !consumed.contains(name2)) {
                                        consumed.add(name1); consumed.add(name2)
                                        if (!bs.pressed) {
                                            stateA.cancelPending(); stateB.cancelPending()
                                            if (stateA.singleActionFired) stateA.releaseIfActive(robot)
                                            if (stateB.singleActionFired) stateB.releaseIfActive(robot)
                                            stateA.comboConsumed = true; stateB.comboConsumed = true

                                            bs.pressed = true; bs.singleActionFired = true
                                            bs.fire(robot, bind)
                                        }
                                    } else {
                                        if (bs.pressed) { bs.releaseIfActive(robot); bs.pressed = false }
                                    }
                                }

                                handleCombo("M1", debouncedS1, "M2", debouncedS2, m1m2State, currentLayerConfig.m1_m2, m1State, m2State)
                                handleCombo("M1", debouncedS1, "M3", debouncedS3, m1m3State, currentLayerConfig.m1_m3, m1State, m3State)
                                handleCombo("M1", debouncedS1, "M4", debouncedS4, m1m4State, currentLayerConfig.m1_m4, m1State, m4State)
                                handleCombo("M2", debouncedS2, "M3", debouncedS3, m2m3State, currentLayerConfig.m2_m3, m2State, m3State)
                                handleCombo("M2", debouncedS2, "M4", debouncedS4, m2m4State, currentLayerConfig.m2_m4, m2State, m4State)
                                handleCombo("M3", debouncedS3, "M4", debouncedS4, m3m4State, currentLayerConfig.m3_m4, m3State, m4State)
                                handleCombo("Command", debouncedSCmd, "Library", debouncedSLib, cmdLibState, currentLayerConfig.cmd_lib, cmdState, libState)

                                fun handleSingle(name: String, state: Boolean, bs: ButtonState, bind: PaddleBind) {
                                    if (consumed.contains(name)) {
                                        if (!bs.pressed) bs.pressed = true
                                        bs.cancelPending()
                                        if (bs.singleActionFired) { bs.releaseIfActive(robot); bs.singleActionFired = false }
                                        bs.comboConsumed = true
                                        return
                                    }

                                    if (state && !bs.pressed) {
                                        bs.pressed = true; bs.singleActionFired = false; bs.comboConsumed = false
                                        if (bind.enabled) {
                                            if (p.comboBufferMs > 0) {
                                                bs.pendingTask = object : java.util.TimerTask() {
                                                    override fun run() {
                                                        if (!bs.comboConsumed) {
                                                            bs.singleActionFired = true
                                                            bs.fire(robot, bind)
                                                        }
                                                    }
                                                }
                                                actionTimer.schedule(bs.pendingTask, p.comboBufferMs.toLong())
                                            } else {
                                                bs.singleActionFired = true
                                                bs.fire(robot, bind)
                                            }
                                        }
                                    } else if (!state && bs.pressed) {
                                        bs.cancelPending()
                                        if (bind.enabled && !bs.singleActionFired && !bs.comboConsumed) bs.fire(robot, bind)
                                        bs.releaseIfActive(robot); bs.pressed = false; bs.comboConsumed = false
                                    }
                                }

                                handleSingle("M1", debouncedS1, m1State, currentLayerConfig.m1)
                                handleSingle("M2", debouncedS2, m2State, currentLayerConfig.m2)
                                handleSingle("M3", debouncedS3, m3State, currentLayerConfig.m3)
                                handleSingle("M4", debouncedS4, m4State, currentLayerConfig.m4)
                                handleSingle("Command", debouncedSCmd, cmdState, currentLayerConfig.cmd)
                                handleSingle("Library", debouncedSLib, libState, currentLayerConfig.lib)

                            } catch (e: Exception) {
                                isConnected = false
                                lastConnectionError = "HID read error: ${e.message}"
                                Logger.error("Error during Raikiri II reading loop", e)
                                raikiri.close()
                            }
                        }
                    } finally {
                        actionTimer.cancel()
                        isConnected = false
                        try { raikiri.close() } catch (e: Exception) {}
                    }
                }
                readingThread?.start()
            } else {
                lastConnectionError = "Failed to open Raikiri II HID device"
                Logger.warn("Failed to open Raikiri II HID device")
            }
        }
    }

    hidServices.addHidServicesListener(controllerListener)

    // Dedicated Watchdog Thread to continually ping & monitor USB Dongle and Controller Link
    Thread {
        while (true) {
            try {
                val now = System.currentTimeMillis()
                val recentHid = (now - lastHidDataTime) < 2500L
                val recentXInput = (now - lastXInputDataTime) < 2500L

                // 1. Target-scan ONLY for ASUS Raikiri II HID devices (VID 0x0B05)
                if (!controllerListener.isConnected) {
                    val raikiriDevices = findRaikiriHidDevices()
                    val raikiriDongle = raikiriDevices.firstOrNull()
                    val raikiriPaddleDevice = raikiriDevices.find { Integer.toHexString(it.usagePage).endsWith("c3") }

                    if (raikiriDongle != null) {
                        lastDongleSeenTime = now
                        updateUsbDongleStatus(DeviceStatus.CONNECTED, "ROG Raikiri II USB Dongle plugged in")
                    }

                    if (raikiriPaddleDevice != null) {
                        controllerListener.startReading(raikiriPaddleDevice)
                    }
                } else {
                    lastDongleSeenTime = now
                    updateUsbDongleStatus(DeviceStatus.CONNECTED, "ROG Raikiri II USB Dongle plugged in")
                }

                val isDonglePresent = (now - lastDongleSeenTime) < 2500L
                if (!isDonglePresent) {
                    updateUsbDongleStatus(DeviceStatus.DISCONNECTED, "USB Dongle unplugged / not detected")
                }

                // 2. Controller Link heartbeat (ping timeout)
                val err = lastConnectionError
                if (err != null && usbDongleStatus == DeviceStatus.CONNECTED) {
                    updateControllerLinkStatus(DeviceStatus.ERROR, err)
                } else if (recentHid || recentXInput) {
                    val desc = when {
                        recentHid && recentXInput -> "Connected (Raikiri II HID & XInput active)"
                        recentHid -> "Connected (Raikiri II HID active)"
                        else -> "Connected (XInput active)"
                    }
                    updateControllerLinkStatus(DeviceStatus.CONNECTED, desc)
                } else {
                    if (usbDongleStatus == DeviceStatus.CONNECTED) {
                        updateControllerLinkStatus(DeviceStatus.DISCONNECTED, "Controller turned off or sleeping")
                    } else {
                        updateControllerLinkStatus(DeviceStatus.DISCONNECTED, "USB Dongle unplugged")
                    }
                }

            } catch (e: Exception) {
                Logger.error("Error in status watchdog thread", e)
            }
            Thread.sleep(1000)
        }
    }.start()
}

// --- INPUT INJECTION LOGIC (THREAD-SAFE WRAPPERS) ---

fun pressKeyBind(robot: Robot, b: PaddleBind) {
    synchronized(robot) {
        try {
            if (b.keyChar.startsWith("Xbox_")) return

            if (b.win) robot.keyPress(KeyEvent.VK_WINDOWS)
            if (b.shift) robot.keyPress(KeyEvent.VK_SHIFT)
            if (b.ctrl) robot.keyPress(KeyEvent.VK_CONTROL)
            if (b.alt) robot.keyPress(KeyEvent.VK_ALT)

            val mouseMask = getMouseMask(b.keyChar)
            if (mouseMask != 0) {
                robot.mousePress(mouseMask)
            } else {
                val k = getKeyCode(b.keyChar)
                if (k != null) robot.keyPress(k)
            }
        } catch (e: Exception) {}
    }
}

fun releaseKeyBind(robot: Robot, b: PaddleBind) {
    synchronized(robot) {
        try {
            if (b.keyChar.startsWith("Xbox_")) return

            val mouseMask = getMouseMask(b.keyChar)
            if (mouseMask != 0) {
                robot.mouseRelease(mouseMask)
            } else {
                val k = getKeyCode(b.keyChar)
                if (k != null) robot.keyRelease(k)
            }

            if (b.alt) robot.keyRelease(KeyEvent.VK_ALT)
            if (b.ctrl) robot.keyRelease(KeyEvent.VK_CONTROL)
            if (b.shift) robot.keyRelease(KeyEvent.VK_SHIFT)
            if (b.win) robot.keyRelease(KeyEvent.VK_WINDOWS)
        } catch (e: Exception) {}
    }
}

// --- MACRO PARSING UTILITY ---
fun parseMacroText(macroText: String): List<String> {
    val result = mutableListOf<String>()
    // Split by common sequence delimiters: commas and semicolons
    val rawTokens = macroText.split(Regex("[,;]")).map { it.trim() }
    for (rawToken in rawTokens) {
        if (rawToken.isEmpty()) continue
        // Matches a delay number with optional unit suffix followed by an action separated by period(s) or space(s) e.g., "350ms. MClick" or "350ms MClick"
        val match = Regex("^(\\d+(?:ms|s)?)(?:\\s*\\.\\s*|\\s+)([a-zA-Z_].*)$", RegexOption.IGNORE_CASE).matchEntire(rawToken)
        if (match != null) {
            result.add(match.groupValues[1]) // Delay (e.g. 350ms)
            result.add(match.groupValues[2]) // Action (e.g. MClick)
        } else {
            result.add(rawToken)
        }
    }
    return result
}

fun processMacroToken(robot: Robot, token: String, pressedKeys: MutableSet<Int>, pressedMouse: MutableSet<Int>) {
    val t = token.trim()
    if (t.isEmpty() || Thread.currentThread().isInterrupted) return

    // Dynamic delay (e.g., 50ms~150ms or 50~150ms)
    if (t.contains("~")) {
        val parts = t.split("~")
        if (parts.size == 2) {
            val minStr = parts[0].trim().lowercase().removeSuffix("ms").removeSuffix("s")
            val maxStr = parts[1].trim().lowercase().removeSuffix("ms").removeSuffix("s")
            val min = minStr.toLongOrNull()
            val max = maxStr.toLongOrNull()
            if (min != null && max != null && min <= max) {
                val delay = Random.nextLong(min, max + 1)
                if (delay > 0) Thread.sleep(delay)
                return
            }
        }
    }

    // Explicit Static delays (Require either 'ms' or 's' suffixes)
    val tLower = t.lowercase()
    if (tLower.endsWith("ms")) {
        val d = tLower.removeSuffix("ms").trim().toLongOrNull()
        if (d != null) {
            if (d > 0) Thread.sleep(d)
            return
        }
    } else if (tLower.endsWith("s") && !tLower.endsWith(" down") && !tLower.endsWith(" up")) {
        val numPart = tLower.removeSuffix("s").trim()
        if (numPart.isNotEmpty()) {
            val d = numPart.toDoubleOrNull()
            if (d != null) {
                if (d > 0) Thread.sleep((d * 1000).toLong())
                return
            }
        }
    }

    val p = t.split(Regex("\\s+"))

    if (p[0].equals("MouseAbs", ignoreCase = true) && p.size >= 3) {
        val x = p[1].toIntOrNull() ?: return
        val y = p[2].toIntOrNull() ?: return
        try {
            synchronized(robot) { robot.mouseMove(x, y) }
        } catch (e: Exception) {}
        return
    }

    if (p[0].equals("MouseDelta", ignoreCase = true) && p.size >= 3) {
        val dx = p[1].toIntOrNull() ?: return
        val dy = p[2].toIntOrNull() ?: return
        val currentPos = MouseInfo.getPointerInfo().location
        try {
            synchronized(robot) { robot.mouseMove(currentPos.x + dx, currentPos.y + dy) }
        } catch (e: Exception) {}
        return
    }

    val act: String
    val keyStr: String

    if (tLower.endsWith(" down")) {
        act = "down"
        keyStr = t.substring(0, t.length - 5).trim()
    } else if (tLower.endsWith(" up")) {
        act = "up"
        keyStr = t.substring(0, t.length - 3).trim()
    } else {
        act = "tap"
        keyStr = t
    }

    val key = keyStr
    if (key.startsWith("Xbox_", ignoreCase = true)) return

    // Match Key or Mouse Actions FIRST
    val mouseMask = getMouseMask(key)
    val isMouse = mouseMask != 0
    val k = getKeyCode(key)
    val isKeyboardKey = k != null

    if (isMouse || isKeyboardKey) {
        if (isMouse) {
            try {
                when (act) {
                    "down" -> {
                        synchronized(robot) { robot.mousePress(mouseMask) }
                        pressedMouse.add(mouseMask)
                    }
                    "up" -> {
                        synchronized(robot) { robot.mouseRelease(mouseMask) }
                        pressedMouse.remove(mouseMask)
                    }
                    else -> { // TAP
                        synchronized(robot) { robot.mousePress(mouseMask) }
                        pressedMouse.add(mouseMask)
                        Thread.sleep(50)
                        synchronized(robot) { robot.mouseRelease(mouseMask) }
                        pressedMouse.remove(mouseMask)
                    }
                }
            } catch (e: Exception) {}
        } else if (k != null) {
            try {
                when (act) {
                    "down" -> {
                        synchronized(robot) { robot.keyPress(k) }
                        pressedKeys.add(k)
                    }
                    "up" -> {
                        synchronized(robot) { robot.keyRelease(k) }
                        pressedKeys.remove(k)
                    }
                    else -> { // TAP
                        synchronized(robot) { robot.keyPress(k) }
                        pressedKeys.add(k)
                        Thread.sleep(50)
                        synchronized(robot) { robot.keyRelease(k) }
                        pressedKeys.remove(k)
                    }
                }
            } catch (e: Exception) {}
        }
    }
}

fun executeMacro(robot: Robot, b: PaddleBind, state: ButtonState): Thread {
    val t = Thread {
        val pressedKeys = mutableSetOf<Int>()
        val pressedMouse = mutableSetOf<Int>()
        try {
            do {
                val tokens = parseMacroText(b.macroText)
                for (token in tokens) {
                    if (Thread.currentThread().isInterrupted) break
                    processMacroToken(robot, token, pressedKeys, pressedMouse)
                }
            } while (b.repeatMacro && state.activeBind === b && !Thread.currentThread().isInterrupted)
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        } catch (e: Exception) {
            // Keep executing or log silently
        } finally {
            // Clean up left-over pressed physical keys safely on release/interruption
            pressedKeys.forEach { k ->
                synchronized(robot) {
                    try { robot.keyRelease(k) } catch (e: Exception) {}
                }
            }
            pressedMouse.forEach { m ->
                synchronized(robot) {
                    try { robot.mouseRelease(m) } catch (e: Exception) {}
                }
            }
        }
    }
    t.start()
    return t
}

fun executeMacroStep(robot: Robot, b: PaddleBind, state: ButtonState) {
    val tokens = parseMacroText(b.macroText).filter { s: String ->
        val sLower = s.trim().lowercase()
        s.isNotEmpty() && !s.contains("~") &&
                !sLower.endsWith("ms") &&
                !(sLower.endsWith("s") && sLower.removeSuffix("s").trim().toDoubleOrNull() != null)
    }

    if (tokens.isEmpty()) return

    Thread {
        // Synchronize on the state itself to avoid concurrent indexing anomalies
        synchronized(state) {
            try {
                val token = tokens[state.stepIndex % tokens.size]
                val pressedKeys = mutableSetOf<Int>()
                val pressedMouse = mutableSetOf<Int>()

                processMacroToken(robot, token, pressedKeys, pressedMouse)

                state.stepIndex = (state.stepIndex + 1) % tokens.size
            } catch (e: Exception) {}
        }
    }.start()
}