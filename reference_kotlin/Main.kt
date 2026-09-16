package com.retholtz.shadowlink

import com.sun.jna.platform.win32.Kernel32
import com.sun.jna.platform.win32.User32
import com.sun.jna.platform.win32.WinNT
import com.sun.jna.platform.win32.WinDef.HWND
import com.sun.jna.ptr.IntByReference
import java.awt.*
import java.io.File
import javax.swing.*
import javax.swing.event.DocumentEvent
import javax.swing.event.DocumentListener
import javax.swing.filechooser.FileNameExtensionFilter
import java.nio.channels.FileChannel
import java.nio.channels.FileLock
import java.nio.file.StandardOpenOption
import kotlin.system.exitProcess

// --- GLOBAL STATE ---
const val APP_VERSION = "1.40"
const val GITHUB_REPO = "retholtz/ShadowLink"

var profiles = mutableListOf<Profile>()
var activeProfile: Profile = Profile()
var autoSwitchEnabled = true
var startMinimized = false
var loadOnStartup = false
var isDarkMode = true
var osdPosition = "Bottom Right"
var controllerScanInterval = 5000

@Volatile var activeLayer = 1

val appDataPath = System.getenv("APPDATA") ?: System.getProperty("user.home")
val dataDir = File(appDataPath, "ShadowLink").apply { if (!exists()) mkdirs() }
val rootDir = File(dataDir, "profiles").apply { if (!exists()) mkdirs() }
val globalConfigFile = File(dataDir, "config.properties")

// --- UI GLOBALS ---
lateinit var frame: JFrame
lateinit var profileCombo: JComboBox<String>
lateinit var processField: JTextField
lateinit var tabbedPane: JTabbedPane
lateinit var t1Combo: JComboBox<String>
lateinit var t2Combo: JComboBox<String>
lateinit var bufferSpinner: JSpinner

class LayerUI(
    val nameField: JTextField, val enabledBox: JCheckBox,
    val m1: PaddleUIControls, val m2: PaddleUIControls,
    val m3: PaddleUIControls, val m4: PaddleUIControls,
    val cmd: PaddleUIControls, val lib: PaddleUIControls,
    val lb: PaddleUIControls, val rb: PaddleUIControls,
    val lt: PaddleUIControls, val rt: PaddleUIControls,
    val a: PaddleUIControls, val b: PaddleUIControls,
    val x: PaddleUIControls, val y: PaddleUIControls,
    val l3: PaddleUIControls, val r3: PaddleUIControls,
    val dUp: PaddleUIControls, val dDown: PaddleUIControls,
    val dLeft: PaddleUIControls, val dRight: PaddleUIControls,
    val m1_m2: PaddleUIControls, val m1_m3: PaddleUIControls,
    val m1_m4: PaddleUIControls, val m2_m3: PaddleUIControls,
    val m2_m4: PaddleUIControls, val m3_m4: PaddleUIControls
)
val layerUIs = mutableListOf<LayerUI>()

// --- HELPER FOR MODERN CARD CONTAINERS ---
fun createCardPanel(title: String? = null): JPanel {
    val panel = JPanel()
    panel.layout = BoxLayout(panel, BoxLayout.Y_AXIS)
    val lineBorder = BorderFactory.createLineBorder(
        UIManager.getColor("Component.borderColor") ?: Color(70, 70, 75), 1, true
    )
    val emptyPadding = BorderFactory.createEmptyBorder(8, 12, 8, 12)
    if (title != null) {
        val titleBorder = BorderFactory.createTitledBorder(lineBorder, title)
        val defaultFont = UIManager.getFont("TitledBorder.font") ?: Font("Segoe UI", Font.BOLD, 13)
        titleBorder.titleFont = defaultFont.deriveFont(Font.BOLD, 12f)
        panel.border = BorderFactory.createCompoundBorder(titleBorder, emptyPadding)
    } else {
        panel.border = BorderFactory.createCompoundBorder(lineBorder, emptyPadding)
    }
    return panel
}

// --- DUAL STATUS INDICATOR PANEL COMPONENT ---
class StatusIndicatorsPanel : JPanel() {
    private val dongleRow: JPanel
    private val controllerRow: JPanel

    init {
        isOpaque = false
        layout = BoxLayout(this, BoxLayout.Y_AXIS)
        border = BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(UIManager.getColor("Component.borderColor") ?: Color(70, 70, 75), 1, true),
            BorderFactory.createEmptyBorder(4, 8, 4, 8)
        )

        dongleRow = createSingleIndicatorRow(
            title = "USB Dongle Status",
            shortLabel = "Dongle:",
            getStatus = { usbDongleStatus },
            getDetails = { usbDongleDetails }
        )

        controllerRow = createSingleIndicatorRow(
            title = "Controller Link Status",
            shortLabel = "Controller:",
            getStatus = { controllerLinkStatus },
            getDetails = { controllerLinkDetails }
        )

        add(dongleRow)
        add(Box.createVerticalStrut(4))
        add(controllerRow)

        onStatusUpdated = {
            repaint()
            dongleRow.toolTipText = formatTooltip("USB Dongle Status", usbDongleStatus, usbDongleDetails)
            controllerRow.toolTipText = formatTooltip("Controller Link Status", controllerLinkStatus, controllerLinkDetails)
        }
    }

    private fun formatTooltip(title: String, status: DeviceStatus, details: String): String {
        return "<html><b>$title:</b> ${status.label}<br><i>$details</i></html>"
    }

    private fun createSingleIndicatorRow(
        title: String,
        shortLabel: String,
        getStatus: () -> DeviceStatus,
        getDetails: () -> String
    ): JPanel {
        val row = object : JPanel() {
            override fun paintComponent(g: Graphics) {
                super.paintComponent(g)
                val g2 = g.create() as Graphics2D
                g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
                g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)

                val status = getStatus()
                val circleSize = 10
                val circleX = 4
                val circleY = (height - circleSize) / 2

                // Outer Glow ring
                g2.color = Color(status.color.red, status.color.green, status.color.blue, 60)
                g2.fillOval(circleX - 2, circleY - 2, circleSize + 4, circleSize + 4)

                // Fill LED
                g2.color = status.color
                g2.fillOval(circleX, circleY, circleSize, circleSize)

                // Highlight specular reflection
                g2.color = Color(255, 255, 255, 160)
                g2.fillOval(circleX + 2, circleY + 1, 3, 3)

                // Border ring
                g2.color = status.color.darker()
                g2.drawOval(circleX, circleY, circleSize, circleSize)

                // Label
                g2.color = UIManager.getColor("Label.foreground") ?: Color.BLACK
                g2.font = font.deriveFont(Font.BOLD, 11f)
                val fm = g2.fontMetrics
                val textY = (height - fm.height) / 2 + fm.ascent
                g2.drawString("$shortLabel ${status.label}", circleX + circleSize + 8, textY)

                g2.dispose()
            }
        }
        row.isOpaque = false
        row.preferredSize = Dimension(175, 18)
        row.toolTipText = formatTooltip(title, getStatus(), getDetails())
        return row
    }
}

// --- SINGLE INSTANCE LOCK ---
private var appLockChannel: FileChannel? = null
private var appLock: FileLock? = null

fun checkSingleInstance(): Boolean {
    return try {
        val lockFile = File(dataDir, "app.lock")
        val channel = FileChannel.open(
            lockFile.toPath(),
            StandardOpenOption.CREATE,
            StandardOpenOption.WRITE
        )
        val lock = channel.tryLock()
        if (lock != null) {
            appLockChannel = channel
            appLock = lock
            Runtime.getRuntime().addShutdownHook(Thread {
                try {
                    lock.release()
                    channel.close()
                } catch (_: Exception) {}
            })
            true
        } else {
            channel.close()
            false
        }
    } catch (e: Exception) {
        Logger.warn("Single instance lock check failed: ${e.message}")
        false
    }
}

fun tryToFocusExistingWindow() {
    try {
        val windowTitle = "ShadowLink - ROG Raikiri II - v$APP_VERSION"
        val hwnd = User32.INSTANCE.FindWindow(null, windowTitle)
        if (hwnd != null) {
            User32.INSTANCE.ShowWindow(hwnd, User32.SW_RESTORE)
            User32.INSTANCE.SetForegroundWindow(hwnd)
        }
    } catch (e: Exception) {
        Logger.warn("Could not focus existing window: ${e.message}")
    }
}

// --- MAIN ENTRY ---
fun main() {
    System.setProperty("java.awt.headless", "false")
    System.setProperty("awt.useSystemAAFontSettings", "lcd_hrgb")
    System.setProperty("swing.aatext", "true")

    if (!checkSingleInstance()) {
        Logger.warn("Another instance of ShadowLink is already running. Exiting.")
        applyTheme()
        tryToFocusExistingWindow()
        JOptionPane.showMessageDialog(
            null,
            "ShadowLink is already running.",
            "ShadowLink",
            JOptionPane.WARNING_MESSAGE
        )
        exitProcess(0)
    }

    Logger.info("Starting ShadowLink v$APP_VERSION...")

    loadAllProfiles()
    applyTheme()

    SwingUtilities.invokeLater {
        createMainUI()
        setupSystemTray(frame)
        if (!startMinimized) {
            frame.isVisible = true
        }

        // Checks for updates silently in the background on load
        Thread { checkForUpdates(frame, silent = true) }.start()
    }

    Thread { runControllerSniffer() }.start()
    Thread { runAutoSwitchWatchdog() }.start()
}

fun applyTheme() {
    try {
        if (isDarkMode) UIManager.setLookAndFeel("com.formdev.flatlaf.FlatDarkLaf")
        else UIManager.setLookAndFeel("com.formdev.flatlaf.FlatLightLaf")

        // FlatLaf Component Geometry & Visual Polish
        UIManager.put("Button.arc", 12)
        UIManager.put("Component.arc", 10)
        UIManager.put("TextComponent.arc", 10)
        UIManager.put("CheckBox.arc", 6)
        UIManager.put("ProgressBar.arc", 8)
        UIManager.put("TabbedPane.showTabSeparators", true)
        UIManager.put("TabbedPane.tabSeparatorsFullHeight", true)
        UIManager.put("TabbedPane.hasFullBorder", false)
        UIManager.put("TabbedPane.tabArc", 12)
        UIManager.put("ScrollBar.showButtons", false)
        UIManager.put("ScrollBar.thumbArc", 999)
        UIManager.put("ScrollBar.thumbInsets", Insets(2, 2, 2, 2))
        UIManager.put("TextField.padding", Insets(3, 8, 3, 8))
        UIManager.put("ComboBox.padding", Insets(3, 8, 3, 8))

        val baseFont = Font("Segoe UI", Font.PLAIN, 13)
        UIManager.put("defaultFont", baseFont)
        UIManager.put("TitledBorder.font", baseFont.deriveFont(Font.BOLD, 13f))
    } catch (e: Exception) {
        try { UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName()) } catch (ex: Exception) {}
    }
}

// --- CORE UI GENERATION ---
fun createMainUI() {
    frame = JFrame("ShadowLink - ROG Raikiri II - v$APP_VERSION")
    frame.defaultCloseOperation = JFrame.EXIT_ON_CLOSE
    frame.setSize(1280, 880)
    frame.setLocationRelativeTo(null)
    frame.layout = BorderLayout(12, 12)

    // Window padding for clean whitespace
    (frame.contentPane as JComponent).border = BorderFactory.createEmptyBorder(12, 12, 12, 12)

    val topPanel = JPanel()
    topPanel.layout = BoxLayout(topPanel, BoxLayout.Y_AXIS)

    // --- CARD 1: PROFILE MANAGEMENT ---
    val profileCard = createCardPanel("Profile Management")
    val profileRowWrapper = JPanel(BorderLayout(10, 0))

    val profileRowLeft = JPanel(FlowLayout(FlowLayout.LEFT, 8, 4))
    profileRowLeft.add(StatusIndicatorsPanel())
    profileRowLeft.add(Box.createHorizontalStrut(6))

    val profileLabel = JLabel("Current Profile: ").apply { font = font.deriveFont(Font.BOLD) }
    profileRowLeft.add(profileLabel)

    profileCombo = JComboBox(profiles.map { it.name }.toTypedArray())
    profileCombo.preferredSize = Dimension(180, 30)
    profileCombo.selectedItem = activeProfile.name
    profileCombo.addActionListener {
        val selected = profileCombo.selectedItem as? String ?: return@addActionListener
        if (selected != activeProfile.name) {
            switchActiveProfile(selected)
            refreshUI()
        }
    }
    profileRowLeft.add(profileCombo)

    val newBtn = JButton("New Profile")
    newBtn.addActionListener {
        val name = JOptionPane.showInputDialog(frame, "Enter Profile Name:")
        if (!name.isNullOrBlank()) {
            val p = Profile(name = name)
            profiles.add(p)
            saveProfile(p)
            profileCombo.addItem(name)
            profileCombo.selectedItem = name
        }
    }

    val cloneBtn = JButton("Clone Profile")
    cloneBtn.toolTipText = "Duplicate current profile"
    cloneBtn.addActionListener {
        val name = JOptionPane.showInputDialog(frame, "Enter New Profile Name (Clone of ${activeProfile.name}):")
        if (!name.isNullOrBlank()) {
            val clonedLayers = activeProfile.layers.map { layer ->
                layer.copy(
                    m1 = layer.m1.copy(), m2 = layer.m2.copy(), m3 = layer.m3.copy(), m4 = layer.m4.copy(),
                    cmd = layer.cmd.copy(), lib = layer.lib.copy(),
                    lb = layer.lb.copy(), rb = layer.rb.copy(), lt = layer.lt.copy(), rt = layer.rt.copy(),
                    a = layer.a.copy(), b = layer.b.copy(), x = layer.x.copy(), y = layer.y.copy(),
                    l3 = layer.l3.copy(), r3 = layer.r3.copy(),
                    dUp = layer.dUp.copy(), dDown = layer.dDown.copy(), dLeft = layer.dLeft.copy(), dRight = layer.dRight.copy(),
                    m1_m2 = layer.m1_m2.copy(), m1_m3 = layer.m1_m3.copy(), m1_m4 = layer.m1_m4.copy(),
                    m2_m3 = layer.m2_m3.copy(), m2_m4 = layer.m2_m4.copy(), m3_m4 = layer.m3_m4.copy()
                )
            }
            val p = activeProfile.copy(name = name, layers = clonedLayers)
            profiles.add(p)
            saveProfile(p)
            reloadProfileDropdown()
            profileCombo.selectedItem = name
            refreshUI()
        }
    }

    val deleteBtn = JButton("Delete Profile")
    deleteBtn.addActionListener {
        if (profiles.size <= 1) return@addActionListener
        val current = activeProfile
        profiles.remove(current)
        File(rootDir, "${current.name}.properties").delete()
        profileCombo.removeItem(current.name)
        switchActiveProfile(profiles[0].name)
        refreshUI()
    }

    val importBtn = JButton("Import")
    importBtn.addActionListener {
        val chooser = JFileChooser().apply { fileFilter = FileNameExtensionFilter("ShadowLink Profile (*.properties)", "properties") }
        if (chooser.showOpenDialog(frame) == JFileChooser.APPROVE_OPTION) {
            try {
                val file = chooser.selectedFile
                val dest = File(rootDir, file.name)
                file.copyTo(dest, overwrite = true)
                profiles.clear()
                loadAllProfiles()
                switchActiveProfile(file.nameWithoutExtension)
                reloadProfileDropdown()
                refreshUI()
                JOptionPane.showMessageDialog(frame, "Profile '${file.nameWithoutExtension}' Imported Successfully!", "Import Success", JOptionPane.INFORMATION_MESSAGE)
            } catch (e: Exception) {
                JOptionPane.showMessageDialog(frame, "Failed to import profile:\n${e.message}", "Import Error", JOptionPane.ERROR_MESSAGE)
            }
        }
    }

    val exportBtn = JButton("Export")
    exportBtn.addActionListener {
        val chooser = JFileChooser().apply {
            dialogTitle = "Export Profile"
            selectedFile = File("${activeProfile.name}.properties")
            fileFilter = FileNameExtensionFilter("ShadowLink Profile (*.properties)", "properties")
        }
        if (chooser.showSaveDialog(frame) == JFileChooser.APPROVE_OPTION) {
            try {
                val source = File(rootDir, "${activeProfile.name}.properties")
                val dest = chooser.selectedFile
                val finalDest = if (dest.name.endsWith(".properties")) dest else File(dest.parentFile, "${dest.name}.properties")
                source.copyTo(finalDest, overwrite = true)
                JOptionPane.showMessageDialog(frame, "Profile Exported Successfully!", "Export Success", JOptionPane.INFORMATION_MESSAGE)
            } catch (e: Exception) {
                JOptionPane.showMessageDialog(frame, "Failed to export profile:\n${e.message}", "Export Error", JOptionPane.ERROR_MESSAGE)
            }
        }
    }

    profileRowLeft.add(newBtn)
    profileRowLeft.add(cloneBtn)
    profileRowLeft.add(deleteBtn)
    profileRowLeft.add(importBtn)
    profileRowLeft.add(exportBtn)
    profileRowWrapper.add(profileRowLeft, BorderLayout.WEST)

    val profileRowRight = JPanel(FlowLayout(FlowLayout.RIGHT, 8, 4))
    val themeToggleBtn = JToggleButton(if (isDarkMode) "Dark Mode" else "Light Mode", isDarkMode)
    themeToggleBtn.addActionListener {
        isDarkMode = themeToggleBtn.isSelected
        themeToggleBtn.text = if (isDarkMode) "Dark Mode" else "Light Mode"
        applyTheme()
        SwingUtilities.updateComponentTreeUI(frame)
    }
    profileRowRight.add(themeToggleBtn)
    profileRowWrapper.add(profileRowRight, BorderLayout.EAST)
    profileCard.add(profileRowWrapper)

    // --- CARD 2: AUTO-SWITCHING & APP PREFERENCES ---
    val switchCard = createCardPanel("Auto-Switching & App Preferences")
    val switchRow = JPanel(FlowLayout(FlowLayout.LEFT, 10, 4))
    processField = JTextField(activeProfile.targetProcess, 15)
    processField.preferredSize = Dimension(150, 30)

    val browseBtn = JButton("Browse...")
    browseBtn.addActionListener {
        val chooser = JFileChooser().apply { fileFilter = FileNameExtensionFilter("Executables (*.exe)", "exe") }
        if (chooser.showOpenDialog(frame) == JFileChooser.APPROVE_OPTION) {
            processField.text = chooser.selectedFile.name.lowercase()
        }
    }

    val activeAppsBtn = JButton("Active Apps...")
    activeAppsBtn.addActionListener { showActiveProcessDialog(frame) }

    val autoSwitchBox = JCheckBox("Auto-Switch Enabled", autoSwitchEnabled)
    autoSwitchBox.addActionListener { autoSwitchEnabled = autoSwitchBox.isSelected }

    val minimizedBox = JCheckBox("Start Minimized", startMinimized)
    minimizedBox.addActionListener { startMinimized = minimizedBox.isSelected }

    val startupBox = JCheckBox("Load on Startup", loadOnStartup)
    startupBox.addActionListener { loadOnStartup = startupBox.isSelected }

    val processLabel = JLabel("Auto-Switch Executable: ").apply { font = font.deriveFont(Font.BOLD) }
    switchRow.add(processLabel)
    switchRow.add(processField)
    switchRow.add(browseBtn)
    switchRow.add(activeAppsBtn)
    switchRow.add(Box.createHorizontalStrut(10))
    switchRow.add(autoSwitchBox)
    switchRow.add(minimizedBox)
    switchRow.add(startupBox)
    switchCard.add(switchRow)

    topPanel.add(profileCard)
    topPanel.add(Box.createVerticalStrut(8))
    topPanel.add(switchCard)
    frame.add(topPanel, BorderLayout.NORTH)

    // --- TABBED PANE FOR LAYERS AND GLOBAL SETTINGS ---
    tabbedPane = JTabbedPane()
    layerUIs.clear()

    // Create 5 Tabs for Layers
    for (i in 0 until 5) {
        val layerPanel = JPanel(BorderLayout())
        val header = JPanel(FlowLayout(FlowLayout.LEFT, 15, 10))
        val layerLabel = JLabel("Layer Name:").apply { font = font.deriveFont(Font.BOLD) }
        header.add(layerLabel)

        val nameField = JTextField(activeProfile.layers[i].name, 15)
        header.add(nameField)

        val enabledBox = JCheckBox("Enable this layer", activeProfile.layers[i].enabled)
        if (i == 0) {
            enabledBox.isSelected = true
            enabledBox.isEnabled = false
        }
        header.add(enabledBox)
        layerPanel.add(header, BorderLayout.NORTH)

        // Nested Left-Side Tabs for Categories
        val sectionTabs = JTabbedPane(JTabbedPane.LEFT)
        sectionTabs.font = Font("Segoe UI", Font.BOLD, 13)

        fun wrapInScroll(p: JPanel): JScrollPane {
            val wrapper = JPanel(BorderLayout())
            wrapper.add(p, BorderLayout.NORTH)
            val scroll = JScrollPane(wrapper)
            scroll.border = BorderFactory.createEmptyBorder(8, 8, 8, 8)
            scroll.verticalScrollBar.unitIncrement = 16
            return scroll
        }

        // SECTION 1: Back Paddles
        val paddlesPanel = JPanel(GridLayout(6, 1, 6, 6))
        val cmdC = createPaddleRow("Command", activeProfile.layers[i].cmd)
        val libC = createPaddleRow("Library", activeProfile.layers[i].lib)
        val m1C = createPaddleRow("M1 (Bot-L)", activeProfile.layers[i].m1)
        val m2C = createPaddleRow("M2 (Top-L)", activeProfile.layers[i].m2)
        val m3C = createPaddleRow("M3 (Top-R)", activeProfile.layers[i].m3)
        val m4C = createPaddleRow("M4 (Bot-R)", activeProfile.layers[i].m4)

        paddlesPanel.add(cmdC.panel); paddlesPanel.add(libC.panel)
        paddlesPanel.add(m1C.panel); paddlesPanel.add(m2C.panel)
        paddlesPanel.add(m3C.panel); paddlesPanel.add(m4C.panel)

        sectionTabs.addTab(" Back Paddles ", wrapInScroll(paddlesPanel))

        // SECTION 2: Paddle Combos
        val combosPanel = JPanel(GridLayout(6, 1, 6, 6))
        val m1_m2C = createPaddleRow("M1 + M2", activeProfile.layers[i].m1_m2)
        val m1_m3C = createPaddleRow("M1 + M3", activeProfile.layers[i].m1_m3)
        val m1_m4C = createPaddleRow("M1 + M4", activeProfile.layers[i].m1_m4)
        val m2_m3C = createPaddleRow("M2 + M3", activeProfile.layers[i].m2_m3)
        val m2_m4C = createPaddleRow("M2 + M4", activeProfile.layers[i].m2_m4)
        val m3_m4C = createPaddleRow("M3 + M4", activeProfile.layers[i].m3_m4)

        combosPanel.add(m1_m2C.panel); combosPanel.add(m1_m3C.panel); combosPanel.add(m1_m4C.panel)
        combosPanel.add(m2_m3C.panel); combosPanel.add(m2_m4C.panel); combosPanel.add(m3_m4C.panel)

        sectionTabs.addTab(" Paddle Combos ", wrapInScroll(combosPanel))

        // SECTION 3: Triggers, Face & D-Pad
        val standardPanel = JPanel(GridLayout(14, 1, 6, 6))
        val lbC = createPaddleRow("LB (Left Bumper)", activeProfile.layers[i].lb)
        val rbC = createPaddleRow("RB (Right Bumper)", activeProfile.layers[i].rb)
        val ltC = createPaddleRow("LT (Left Trigger)", activeProfile.layers[i].lt)
        val rtC = createPaddleRow("RT (Right Trigger)", activeProfile.layers[i].rt)
        val aC = createPaddleRow("A Button", activeProfile.layers[i].a)
        val bC = createPaddleRow("B Button", activeProfile.layers[i].b)
        val xC = createPaddleRow("X Button", activeProfile.layers[i].x)
        val yC = createPaddleRow("Y Button", activeProfile.layers[i].y)
        val l3C = createPaddleRow("L3 (Left Stick Click)", activeProfile.layers[i].l3)
        val r3C = createPaddleRow("R3 (Right Stick Click)", activeProfile.layers[i].r3)
        val dUpC = createPaddleRow("D-Pad Up", activeProfile.layers[i].dUp)
        val dDownC = createPaddleRow("D-Pad Down", activeProfile.layers[i].dDown)
        val dLeftC = createPaddleRow("D-Pad Left", activeProfile.layers[i].dLeft)
        val dRightC = createPaddleRow("D-Pad Right", activeProfile.layers[i].dRight)

        standardPanel.add(lbC.panel); standardPanel.add(rbC.panel); standardPanel.add(ltC.panel); standardPanel.add(rtC.panel)
        standardPanel.add(aC.panel); standardPanel.add(bC.panel); standardPanel.add(xC.panel); standardPanel.add(yC.panel)
        standardPanel.add(l3C.panel); standardPanel.add(r3C.panel)
        standardPanel.add(dUpC.panel); standardPanel.add(dDownC.panel); standardPanel.add(dLeftC.panel); standardPanel.add(dRightC.panel)

        sectionTabs.addTab(" Triggers, Face & D-Pad ", wrapInScroll(standardPanel))

        layerPanel.add(sectionTabs, BorderLayout.CENTER)

        val tabTitle = if (i == 0) "Layer 1: ${activeProfile.layers[0].name}" else "Layer ${i+1}: ${activeProfile.layers[i].name}"
        tabbedPane.addTab(tabTitle, layerPanel)

        nameField.document.addDocumentListener(object: DocumentListener {
            fun update() { tabbedPane.setTitleAt(i, "Layer ${i+1}: ${nameField.text}") }
            override fun insertUpdate(e: DocumentEvent?) = update()
            override fun removeUpdate(e: DocumentEvent?) = update()
            override fun changedUpdate(e: DocumentEvent?) = update()
        })

        layerUIs.add(LayerUI(
            nameField, enabledBox,
            m1C, m2C, m3C, m4C, cmdC, libC,
            lbC, rbC, ltC, rtC, aC, bC, xC, yC, l3C, r3C, dUpC, dDownC, dLeftC, dRightC,
            m1_m2C, m1_m3C, m1_m4C, m2_m3C, m2_m4C, m3_m4C
        ))
    }

    // --- TAB 6: CONTROLLER & LAYER SETTINGS ---
    val layerSettingsPanel = JPanel()
    layerSettingsPanel.layout = BoxLayout(layerSettingsPanel, BoxLayout.Y_AXIS)
    layerSettingsPanel.border = BorderFactory.createEmptyBorder(12, 12, 12, 12)

    val toggleCard = createCardPanel("Profile Layer Toggle Assignment")
    val toggleInfo = JLabel("<html>Select which buttons will cycle through your enabled layers <b>for this profile</b>. Selecting a Single Button toggle will reserve it globally for this layout, but using a Dual Combo allows both buttons to remain active individually!</html>")
    toggleInfo.border = BorderFactory.createEmptyBorder(0, 0, 10, 0)
    toggleCard.add(toggleInfo)

    val toggleOptions = arrayOf("None", "M1", "M2", "M3", "M4", "Command", "Library")

    val t1Panel = JPanel(FlowLayout(FlowLayout.LEFT))
    t1Panel.add(JLabel("Primary Layer Toggle Button: "))
    t1Combo = JComboBox(toggleOptions).apply { selectedItem = activeProfile.toggleButton1 }
    t1Panel.add(t1Combo)
    toggleCard.add(t1Panel)

    val t2Panel = JPanel(FlowLayout(FlowLayout.LEFT))
    t2Panel.add(JLabel("Secondary Layer Toggle Button (Optional Double-Input Combo): "))
    t2Combo = JComboBox(toggleOptions).apply { selectedItem = activeProfile.toggleButton2 }
    t2Panel.add(t2Combo)
    toggleCard.add(t2Panel)

    t1Combo.addActionListener { refreshLayerLocks() }
    t2Combo.addActionListener { refreshLayerLocks() }

    layerSettingsPanel.add(toggleCard)
    layerSettingsPanel.add(Box.createVerticalStrut(12))

    // Advanced Hardware & Delay Settings Card
    val advancedCard = createCardPanel("Advanced Hardware Settings")
    val advancedInfo = JLabel("<html><b>Controller Auto-Detect Rate</b> <i>(Global)</i>: How often the app searches for a new controller.<br><b>Combo Input Delay</b> <i>(Profile)</i>: Adds a tiny buffer allowing you to trigger combos without misfiring single buttons!</html>")
    advancedInfo.border = BorderFactory.createEmptyBorder(0, 0, 10, 0)
    advancedCard.add(advancedInfo)

    val advancedPanel = JPanel(GridLayout(2, 1, 5, 5))

    val scanPanel = JPanel(FlowLayout(FlowLayout.LEFT))
    scanPanel.add(JLabel("Controller Auto-Detect Rate: "))
    val scanMap = mapOf(1000 to "1000 ms (Fastest)", 2000 to "2000 ms (Fast)", 5000 to "5000 ms (Default)", 10000 to "10000 ms (Slow)")
    val scanCombo = JComboBox(scanMap.values.toTypedArray())
    scanCombo.selectedItem = scanMap[controllerScanInterval] ?: scanMap[5000]
    scanCombo.addActionListener {
        val selectedText = scanCombo.selectedItem as String
        controllerScanInterval = scanMap.entries.firstOrNull { it.value == selectedText }?.key ?: 5000
    }
    scanPanel.add(scanCombo)
    advancedPanel.add(scanPanel)

    val bufferPanel = JPanel(FlowLayout(FlowLayout.LEFT))
    bufferPanel.add(JLabel("Combo Input Delay (Microlag Buffer): "))
    bufferSpinner = JSpinner(SpinnerNumberModel(activeProfile.comboBufferMs, 0, 500, 5))
    bufferPanel.add(bufferSpinner)
    bufferPanel.add(JLabel("ms (0 = Instant/No Buffer, 30 = Recommended)"))
    advancedPanel.add(bufferPanel)

    advancedCard.add(advancedPanel)
    layerSettingsPanel.add(advancedCard)

    tabbedPane.addTab("Controller/Layer Settings", layerSettingsPanel)

    frame.add(tabbedPane, BorderLayout.CENTER)

    // --- BOTTOM ACTION PANEL ---
    val bottomPanel = JPanel(BorderLayout())
    val optionsPanel = JPanel(FlowLayout(FlowLayout.LEFT, 10, 6))

    val osdPositions = arrayOf("Bottom Right", "Bottom Left", "Top Right", "Top Left")
    val osdCombo = JComboBox(osdPositions).apply { selectedItem = osdPosition }
    osdCombo.addActionListener { osdPosition = osdCombo.selectedItem as String }
    optionsPanel.add(JLabel("OSD Corner:"))
    optionsPanel.add(osdCombo)

    val helpBtn = JButton("Macro Help")
    helpBtn.addActionListener { showMacroInstructions(frame) }
    optionsPanel.add(helpBtn)

    val layerHelpBtn = JButton("Layer Help")
    layerHelpBtn.addActionListener { showLayerInstructions(frame) }
    optionsPanel.add(layerHelpBtn)

    val updateBtn = JButton("Check for Updates")
    updateBtn.addActionListener { checkForUpdates(frame, silent = false) }
    optionsPanel.add(updateBtn)

    val exportLogBtn = JButton("Export Log")
    exportLogBtn.toolTipText = "Export diagnostic log file for developer support"
    exportLogBtn.addActionListener { Logger.exportLogs(frame) }
    optionsPanel.add(exportLogBtn)

    bottomPanel.add(optionsPanel, BorderLayout.WEST)

    val saveBtn = JButton("Save & Apply Settings").apply {
        font = Font("Segoe UI", Font.BOLD, 14)
        preferredSize = Dimension(220, 36)
        putClientProperty("JButton.buttonType", "accent")
    }
    saveBtn.addActionListener {
        updateActiveProfileFromUI()
        saveProfile(activeProfile)
        saveGlobalConfig()
        updateStartupRegistry(loadOnStartup)
        JOptionPane.showMessageDialog(frame, "Settings & Profile '${activeProfile.name}' Saved!")
    }
    bottomPanel.add(saveBtn, BorderLayout.EAST)
    frame.add(bottomPanel, BorderLayout.SOUTH)

    refreshLayerLocks()
}

// --- UI HELPERS ---

class PaddleUIControls(
    val panel: JPanel, val enabledBox: JCheckBox, val isMacroBox: JCheckBox,
    val repeatMacroBox: JCheckBox, val stepThroughBox: JCheckBox, val macroField: JTextField,
    val shiftBox: JCheckBox, val ctrlBox: JCheckBox,
    val altBox: JCheckBox, val winBox: JCheckBox, val keyDropdown: JComboBox<String>,
    val reservedLabel: JLabel, val recordBtn: JButton, val editBtn: JButton
) {
    var isReserved: Boolean = false

    fun refreshVis() {
        val e = enabledBox.isSelected; val m = isMacroBox.isSelected

        enabledBox.isVisible = !isReserved
        isMacroBox.isVisible = !isReserved

        isMacroBox.isEnabled = e
        macroField.isEnabled = e && m
        recordBtn.isEnabled = e && m
        editBtn.isEnabled = e && m

        if (repeatMacroBox.isSelected) stepThroughBox.isSelected = false
        if (stepThroughBox.isSelected) repeatMacroBox.isSelected = false

        repeatMacroBox.isEnabled = e && m
        stepThroughBox.isEnabled = e && m

        keyDropdown.isEnabled = e && !m
        shiftBox.isEnabled = e && !m; ctrlBox.isEnabled = e && !m
        altBox.isEnabled = e && !m; winBox.isEnabled = e && !m

        macroField.isVisible = m && !isReserved; repeatMacroBox.isVisible = m && !isReserved
        stepThroughBox.isVisible = m && !isReserved; recordBtn.isVisible = m && !isReserved
        editBtn.isVisible = m && !isReserved

        keyDropdown.isVisible = !m && !isReserved; shiftBox.isVisible = !m && !isReserved; ctrlBox.isVisible = !m && !isReserved
        altBox.isVisible = !m && !isReserved; winBox.isVisible = !m && !isReserved

        reservedLabel.isVisible = isReserved
        panel.revalidate()
        panel.repaint()
    }
}

fun createPaddleRow(name: String, bind: PaddleBind): PaddleUIControls {
    val panel = JPanel(FlowLayout(FlowLayout.LEFT, 6, 4)).apply {
        border = BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(UIManager.getColor("Component.borderColor") ?: Color(70, 70, 75), 1, true),
            BorderFactory.createEmptyBorder(2, 6, 2, 6)
        )
    }

    val label = JLabel("$name: ")
    label.preferredSize = Dimension(160, 20)
    panel.add(label)

    val en = JCheckBox("Enabled", bind.enabled).apply { margin = Insets(0, 0, 0, 0) }
    val mac = JCheckBox("Macro", bind.isMacro).apply { margin = Insets(0, 0, 0, 0) }
    val rep = JCheckBox("Repeat", bind.repeatMacro).apply { margin = Insets(0, 0, 0, 0) }
    val stp = JCheckBox("Step", bind.stepThrough).apply { margin = Insets(0, 0, 0, 0) }
    val txt = JTextField(bind.macroText, 18).apply { margin = Insets(2, 6, 2, 6) }

    val sh = JCheckBox("Shift", bind.shift).apply { margin = Insets(0, 0, 0, 0) }
    val ct = JCheckBox("Ctrl", bind.ctrl).apply { margin = Insets(0, 0, 0, 0) }
    val al = JCheckBox("Alt", bind.alt).apply { margin = Insets(0, 0, 0, 0) }
    val wi = JCheckBox("Win", bind.win).apply { margin = Insets(0, 0, 0, 0) }

    val key = JComboBox(SUPPORTED_KEYS).apply { selectedItem = bind.keyChar }

    val resLbl = JLabel("Reserved for Layer Toggle").apply {
        foreground = Color.GRAY
        font = font.deriveFont(Font.ITALIC)
        isVisible = false
    }

    val recBtn = JButton("Rec").apply {
        foreground = Color.RED
        margin = Insets(2, 4, 2, 4)
        toolTipText = "Open Live Macro Recorder"
        addActionListener { openMacroRecorder(frame, txt) }
    }

    val editBtn = JButton("Edit").apply {
        margin = Insets(2, 4, 2, 4)
        toolTipText = "Open Large Macro Editor"
        addActionListener { openMacroEditor(frame, txt, name) }
    }

    val uiControls = PaddleUIControls(panel, en, mac, rep, stp, txt, sh, ct, al, wi, key, resLbl, recBtn, editBtn)

    en.addActionListener { uiControls.refreshVis() }
    mac.addActionListener { uiControls.refreshVis() }
    rep.addActionListener { if (rep.isSelected) stp.isSelected = false; uiControls.refreshVis() }
    stp.addActionListener { if (stp.isSelected) rep.isSelected = false; uiControls.refreshVis() }

    panel.add(en); panel.add(mac); panel.add(rep); panel.add(stp)
    panel.add(sh); panel.add(ct); panel.add(al); panel.add(wi); panel.add(key)
    panel.add(recBtn); panel.add(editBtn); panel.add(txt); panel.add(resLbl)

    uiControls.refreshVis()
    return uiControls
}

fun refreshPaddleRow(c: PaddleUIControls, b: PaddleBind) {
    c.enabledBox.isSelected = b.enabled
    c.isMacroBox.isSelected = b.isMacro
    c.repeatMacroBox.isSelected = b.repeatMacro
    c.stepThroughBox.isSelected = b.stepThrough
    c.macroField.text = b.macroText
    c.shiftBox.isSelected = b.shift
    c.ctrlBox.isSelected = b.ctrl
    c.altBox.isSelected = b.alt
    c.winBox.isSelected = b.win
    c.keyDropdown.selectedItem = b.keyChar
    c.refreshVis()
}

fun updateBindFromUI(b: PaddleBind, c: PaddleUIControls) {
    b.enabled = c.enabledBox.isSelected
    b.isMacro = c.isMacroBox.isSelected
    b.repeatMacro = c.repeatMacroBox.isSelected; b.stepThrough = c.stepThroughBox.isSelected
    b.macroText = c.macroField.text
    b.keyChar = c.keyDropdown.selectedItem?.toString() ?: "A"
    b.shift = c.shiftBox.isSelected; b.ctrl = c.ctrlBox.isSelected
    b.alt = c.altBox.isSelected; b.win = c.winBox.isSelected
}

fun refreshLayerLocks() {
    val t1 = t1Combo.selectedItem as String
    val t2 = t2Combo.selectedItem as String

    val isCombo = t1 != "None" && t2 != "None" && t1 != t2
    val reservedBtn = if (!isCombo) {
        if (t1 != "None") t1 else if (t2 != "None") t2 else "None"
    } else {
        "None"
    }

    val reservedCombo = if (isCombo) {
        val sorted = listOf(t1, t2).sorted()
        "${sorted[0]}+${sorted[1]}"
    } else {
        "None"
    }

    for (ui in layerUIs) {
        ui.m1.isReserved = (reservedBtn == "M1"); ui.m1.refreshVis()
        ui.m2.isReserved = (reservedBtn == "M2"); ui.m2.refreshVis()
        ui.m3.isReserved = (reservedBtn == "M3"); ui.m3.refreshVis()
        ui.m4.isReserved = (reservedBtn == "M4"); ui.m4.refreshVis()
        ui.cmd.isReserved = (reservedBtn == "Command"); ui.cmd.refreshVis()
        ui.lib.isReserved = (reservedBtn == "Library"); ui.lib.refreshVis()

        ui.m1_m2.isReserved = (reservedCombo == "M1+M2"); ui.m1_m2.refreshVis()
        ui.m1_m3.isReserved = (reservedCombo == "M1+M3"); ui.m1_m3.refreshVis()
        ui.m1_m4.isReserved = (reservedCombo == "M1+M4"); ui.m1_m4.refreshVis()
        ui.m2_m3.isReserved = (reservedCombo == "M2+M3"); ui.m2_m3.refreshVis()
        ui.m2_m4.isReserved = (reservedCombo == "M2+M4"); ui.m2_m4.refreshVis()
        ui.m3_m4.isReserved = (reservedCombo == "M3+M4"); ui.m3_m4.refreshVis()
    }
}

fun reloadProfileDropdown() {
    profileCombo.removeAllItems()
    profiles.forEach { profileCombo.addItem(it.name) }
    profileCombo.selectedItem = activeProfile.name
}

fun refreshUI() {
    processField.text = activeProfile.targetProcess
    profileCombo.selectedItem = activeProfile.name
    t1Combo.selectedItem = activeProfile.toggleButton1
    t2Combo.selectedItem = activeProfile.toggleButton2
    bufferSpinner.value = activeProfile.comboBufferMs

    for (i in 0 until 5) {
        val config = activeProfile.layers[i]
        val ui = layerUIs[i]

        ui.nameField.text = config.name
        ui.enabledBox.isSelected = config.enabled

        refreshPaddleRow(ui.m1, config.m1)
        refreshPaddleRow(ui.m2, config.m2)
        refreshPaddleRow(ui.m3, config.m3)
        refreshPaddleRow(ui.m4, config.m4)
        refreshPaddleRow(ui.cmd, config.cmd)
        refreshPaddleRow(ui.lib, config.lib)

        refreshPaddleRow(ui.lb, config.lb); refreshPaddleRow(ui.rb, config.rb)
        refreshPaddleRow(ui.lt, config.lt); refreshPaddleRow(ui.rt, config.rt)
        refreshPaddleRow(ui.a, config.a); refreshPaddleRow(ui.b, config.b)
        refreshPaddleRow(ui.x, config.x); refreshPaddleRow(ui.y, config.y)
        refreshPaddleRow(ui.l3, config.l3); refreshPaddleRow(ui.r3, config.r3)
        refreshPaddleRow(ui.dUp, config.dUp); refreshPaddleRow(ui.dDown, config.dDown)
        refreshPaddleRow(ui.dLeft, config.dLeft); refreshPaddleRow(ui.dRight, config.dRight)

        refreshPaddleRow(ui.m1_m2, config.m1_m2)
        refreshPaddleRow(ui.m1_m3, config.m1_m3)
        refreshPaddleRow(ui.m1_m4, config.m1_m4)
        refreshPaddleRow(ui.m2_m3, config.m2_m3)
        refreshPaddleRow(ui.m2_m4, config.m2_m4)
        refreshPaddleRow(ui.m3_m4, config.m3_m4)
    }
    refreshLayerLocks()
}

fun updateActiveProfileFromUI() {
    activeProfile.targetProcess = processField.text.trim().lowercase()
    activeProfile.toggleButton1 = t1Combo.selectedItem as String
    activeProfile.toggleButton2 = t2Combo.selectedItem as String
    activeProfile.comboBufferMs = bufferSpinner.value as Int

    for (i in 0 until 5) {
        val config = activeProfile.layers[i]
        val ui = layerUIs[i]

        config.name = ui.nameField.text.trim()
        config.enabled = ui.enabledBox.isSelected

        updateBindFromUI(config.m1, ui.m1)
        updateBindFromUI(config.m2, ui.m2)
        updateBindFromUI(config.m3, ui.m3)
        updateBindFromUI(config.m4, ui.m4)
        updateBindFromUI(config.cmd, ui.cmd)
        updateBindFromUI(config.lib, ui.lib)

        updateBindFromUI(config.lb, ui.lb); updateBindFromUI(config.rb, ui.rb)
        updateBindFromUI(config.lt, ui.lt); updateBindFromUI(config.rt, ui.rt)
        updateBindFromUI(config.a, ui.a); updateBindFromUI(config.b, ui.b)
        updateBindFromUI(config.x, ui.x); updateBindFromUI(config.y, ui.y)
        updateBindFromUI(config.l3, ui.l3); updateBindFromUI(config.r3, ui.r3)
        updateBindFromUI(config.dUp, ui.dUp); updateBindFromUI(config.dDown, ui.dDown)
        updateBindFromUI(config.dLeft, ui.dLeft); updateBindFromUI(config.dRight, ui.dRight)

        updateBindFromUI(config.m1_m2, ui.m1_m2)
        updateBindFromUI(config.m1_m3, ui.m1_m3)
        updateBindFromUI(config.m1_m4, ui.m1_m4)
        updateBindFromUI(config.m2_m3, ui.m2_m3)
        updateBindFromUI(config.m2_m4, ui.m2_m4)
        updateBindFromUI(config.m3_m4, ui.m3_m4)
    }
}

// --- PROCESS WATCHDOG LOGIC ---
fun getProcessNameFromHwnd(hwnd: HWND): String {
    val processId = IntByReference()
    User32.INSTANCE.GetWindowThreadProcessId(hwnd, processId)
    val processHandle = Kernel32.INSTANCE.OpenProcess(WinNT.PROCESS_QUERY_INFORMATION or WinNT.PROCESS_VM_READ, false, processId.value)
    if (processHandle != null) {
        val buffer = CharArray(1024)
        val size = IntByReference(buffer.size)
        val success = Kernel32.INSTANCE.QueryFullProcessImageName(processHandle, 0, buffer, size)
        Kernel32.INSTANCE.CloseHandle(processHandle)
        if (success) return File(String(buffer, 0, size.value)).name
    }
    return ""
}

fun getForegroundProcessName(): String {
    val hwnd = User32.INSTANCE.GetForegroundWindow() ?: return ""
    return getProcessNameFromHwnd(hwnd)
}

fun switchActiveProfile(name: String) {
    val found = profiles.find { it.name == name }
    if (found != null) {
        activeProfile = found
        activeLayer = 1
        println("Switched to profile: ${found.name}")
    }
}

fun runAutoSwitchWatchdog() {
    while (true) {
        if (autoSwitchEnabled) {
            val activeProcess = getForegroundProcessName().lowercase()
            if (activeProcess.isNotEmpty()) {
                val matchingProfile = profiles.find { it.targetProcess.isNotEmpty() && it.targetProcess == activeProcess }

                if (matchingProfile != null && matchingProfile.name != activeProfile.name) {
                    switchActiveProfile(matchingProfile.name)
                    SwingUtilities.invokeLater {
                        profileCombo.selectedItem = matchingProfile.name
                        showOSD("Profile: ${matchingProfile.name}")
                    }
                }
            }
        }
        Thread.sleep(2000)
    }
}