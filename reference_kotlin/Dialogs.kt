package com.retholtz.shadowlink

import com.sun.jna.platform.win32.User32
import java.awt.*
import java.awt.event.*
import java.awt.image.BufferedImage
import java.io.File
import javax.imageio.ImageIO
import javax.swing.*
import javax.swing.event.DocumentEvent
import javax.swing.event.DocumentListener

// --- OSD SYSTEM ---
var osdWindow: JWindow? = null
var osdTimer: javax.swing.Timer? = null

fun showOSD(message: String) {
    SwingUtilities.invokeLater {
        osdWindow?.dispose()
        osdTimer?.stop()

        val w = JWindow()
        w.isAlwaysOnTop = true
        w.focusableWindowState = false
        w.background = Color(0, 0, 0, 0)

        val panel = object : JPanel() {
            override fun paintComponent(g: Graphics) {
                val g2 = g as Graphics2D
                g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

                g2.color = Color(0, 0, 0, 180)
                g2.fillRoundRect(0, 0, width, height, 25, 25)

                g2.color = Color.WHITE
                g2.font = Font("Segoe UI", Font.BOLD, 22)
                val fm = g2.fontMetrics
                val x = (width - fm.stringWidth(message)) / 2
                val y = (height - fm.height) / 2 + fm.ascent
                g2.drawString(message, x, y)
            }
        }
        panel.isOpaque = false

        val dummyImg = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
        val fm = dummyImg.createGraphics().apply { font = Font("Segoe UI", Font.BOLD, 22) }.fontMetrics
        val wWidth = fm.stringWidth(message) + 80
        val wHeight = fm.height + 40

        w.contentPane.add(panel)
        w.setSize(wWidth, wHeight)

        val ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
        val gd = ge.defaultScreenDevice
        val bounds = gd.defaultConfiguration.bounds

        val margin = 40
        val x = when (osdPosition) {
            "Bottom Right", "Top Right" -> bounds.width - wWidth - margin
            else -> bounds.x + margin
        }
        val y = when (osdPosition) {
            "Bottom Right", "Bottom Left" -> bounds.height - wHeight - margin
            else -> bounds.y + margin
        }
        w.setLocation(x, y)

        w.isVisible = true
        osdWindow = w

        osdTimer = javax.swing.Timer(2000) {
            w.dispose()
        }.apply {
            isRepeats = false
            start()
        }
    }
}

// --- ACTIVE PROCESS DIALOG ---
fun showActiveProcessDialog(parent: JFrame) {
    val dialog = JDialog(parent, "Select Running App", true)
    dialog.layout = BorderLayout(10, 10)
    dialog.setSize(500, 550)
    dialog.setLocationRelativeTo(parent)

    val topContainer = JPanel(BorderLayout(5, 5))
    topContainer.border = BorderFactory.createEmptyBorder(15, 15, 5, 15)
    topContainer.add(JLabel("Search for an open app:"), BorderLayout.NORTH)

    val searchField = JTextField()
    topContainer.add(searchField, BorderLayout.CENTER)
    dialog.add(topContainer, BorderLayout.NORTH)

    val processMap = mutableMapOf<String, String>()
    User32.INSTANCE.EnumWindows({ hwnd, _ ->
        if (User32.INSTANCE.IsWindowVisible(hwnd)) {
            val titleLength = User32.INSTANCE.GetWindowTextLength(hwnd)
            if (titleLength > 0) {
                val titleArr = CharArray(titleLength + 1)
                User32.INSTANCE.GetWindowText(hwnd, titleArr, titleLength + 1)
                val title = String(titleArr).trim { it <= ' ' || it == '\u0000' }

                val exeName = getProcessNameFromHwnd(hwnd)
                if (exeName.isNotEmpty() && !exeName.equals("explorer.exe", true)) {
                    processMap[exeName] = title
                }
            }
        }
        true
    }, null)

    val sortedKeys = processMap.keys.sortedBy { it.lowercase() }
    val listModel = DefaultListModel<String>()
    sortedKeys.forEach { listModel.addElement(it) }

    val list = JList(listModel)
    list.font = Font("Segoe UI", Font.PLAIN, 14)
    list.selectionMode = ListSelectionModel.SINGLE_SELECTION

    list.cellRenderer = object : DefaultListCellRenderer() {
        override fun getListCellRendererComponent(l: JList<*>?, v: Any?, i: Int, s: Boolean, f: Boolean): Component {
            val comp = super.getListCellRendererComponent(l, v, i, s, f) as JLabel
            val name = v as String
            comp.text = "<html><b>$name</b> <font color='gray'>(${processMap[name]})</font></html>"
            comp.border = BorderFactory.createEmptyBorder(2, 5, 2, 5)
            return comp
        }
    }

    searchField.document.addDocumentListener(object : DocumentListener {
        fun update() {
            val query = searchField.text.lowercase()
            listModel.clear()
            sortedKeys.filter { it.lowercase().contains(query) || (processMap[it]?.lowercase()?.contains(query) == true) }
                .forEach { listModel.addElement(it) }
        }
        override fun insertUpdate(e: DocumentEvent?) = update()
        override fun removeUpdate(e: DocumentEvent?) = update()
        override fun changedUpdate(e: DocumentEvent?) = update()
    })

    val scroll = JScrollPane(list)
    scroll.border = BorderFactory.createEmptyBorder(5, 15, 10, 15)
    dialog.add(scroll, BorderLayout.CENTER)

    val btnPanel = JPanel(FlowLayout(FlowLayout.RIGHT, 15, 10))
    val selectBtn = JButton("Use Selected Process")
    selectBtn.addActionListener {
        val selected = list.selectedValue
        if (selected != null) {
            processField.text = selected.lowercase()
            dialog.dispose()
        }
    }
    btnPanel.add(selectBtn)
    dialog.add(btnPanel, BorderLayout.SOUTH)

    dialog.isVisible = true
}

// --- LARGE TEXT MACRO EDITOR DIALOG ---
fun openMacroEditor(parent: JFrame, targetField: JTextField, title: String) {
    val d = JDialog(parent, "Macro Text Editor - $title", true)
    d.setSize(550, 380) // Height increased slightly to prevent text compression
    d.setLocationRelativeTo(parent)
    d.layout = BorderLayout(10, 10)

    val textArea = JTextArea(targetField.text).apply {
        lineWrap = true
        wrapStyleWord = true
        font = Font("Monospaced", Font.PLAIN, 14)
    }

    val textScroll = JScrollPane(textArea).apply {
        border = BorderFactory.createTitledBorder("Edit Macro String:")
    }

    val infoLabel = JLabel("<html><body style='color:gray;'>Actions separated by commas. (e.g. <code>LClick, 100ms, 3</code>)</body></html>")

    val btnPanel = JPanel(FlowLayout(FlowLayout.RIGHT, 0, 0))
    val cancelBtn = JButton("Cancel")
    cancelBtn.addActionListener { d.dispose() }
    val saveBtn = JButton("Save")
    saveBtn.addActionListener {
        targetField.text = textArea.text.trim()
        d.dispose()
    }
    btnPanel.add(cancelBtn)
    btnPanel.add(Box.createHorizontalStrut(10))
    btnPanel.add(saveBtn)

    // Using vertical BoxLayout for the footer to cleanly stack text over the buttons
    val bottomContainer = JPanel().apply {
        layout = BoxLayout(this, BoxLayout.Y_AXIS)
        border = BorderFactory.createEmptyBorder(5, 15, 10, 15)
    }

    val infoPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
    infoPanel.add(infoLabel)

    bottomContainer.add(infoPanel)
    bottomContainer.add(Box.createVerticalStrut(10)) // Visual separator
    bottomContainer.add(btnPanel)

    d.add(textScroll, BorderLayout.CENTER)
    d.add(bottomContainer, BorderLayout.SOUTH)

    d.isVisible = true
}

// --- MACRO RECORDER DIALOG ---
fun openMacroRecorder(parent: JFrame, targetField: JTextField) {
    val d = JDialog(parent, "Live Macro Recorder", true)
    d.setSize(600, 450)
    d.setLocationRelativeTo(parent)
    d.layout = BorderLayout(10, 10)

    val textArea = JTextArea().apply {
        isEditable = false
        lineWrap = true
        wrapStyleWord = true
        text = targetField.text
        font = Font("Monospaced", Font.PLAIN, 14)
    }

    val textScroll = JScrollPane(textArea).apply {
        border = BorderFactory.createTitledBorder("Recorded Macro String:")
    }

    var recording = false
    var lastTime = 0L
    val tokens = mutableListOf<String>()
    if (textArea.text.isNotBlank()) {
        tokens.addAll(textArea.text.split(",").map { it.trim() })
    }

    fun addToken(t: String) {
        if (!recording) return
        val now = System.currentTimeMillis()
        if (lastTime > 0L) {
            val delay = now - lastTime
            if (delay > 10) tokens.add("${delay}ms")
        }
        tokens.add(t)
        lastTime = now
        SwingUtilities.invokeLater { textArea.text = tokens.joinToString(", ") }
    }

    val capturePanel = object : JPanel() {
        init {
            isFocusable = true
            background = UIManager.getColor("Panel.background")
            border = BorderFactory.createTitledBorder("Click here to focus, then perform your Macro...")
            preferredSize = Dimension(450, 80)

            addKeyListener(object : KeyAdapter() {
                override fun keyPressed(e: KeyEvent) {
                    val mapped = KEY_MAP.entries.find { it.value == e.keyCode }?.key ?: return
                    addToken("$mapped down")
                }
                override fun keyReleased(e: KeyEvent) {
                    val mapped = KEY_MAP.entries.find { it.value == e.keyCode }?.key ?: return
                    addToken("$mapped up")
                }
            })

            addMouseListener(object : MouseAdapter() {
                override fun mousePressed(e: MouseEvent) {
                    val btn = when(e.button) { 1 -> "LClick down"; 2 -> "MClick down"; 3 -> "RClick down"; else -> return }
                    addToken(btn)
                }
                override fun mouseReleased(e: MouseEvent) {
                    val btn = when(e.button) { 1 -> "LClick up"; 2 -> "MClick up"; 3 -> "RClick up"; else -> return }
                    addToken(btn)
                }
            })
        }
    }

    val btnPanel = JPanel(FlowLayout())
    val startBtn = JButton("Start Recording")
    val stopBtn = JButton("Stop").apply { isEnabled = false }
    val clearBtn = JButton("Clear")
    val saveBtn = JButton("Save to Macro")

    startBtn.addActionListener {
        recording = true
        lastTime = 0L
        startBtn.isEnabled = false
        stopBtn.isEnabled = true
        capturePanel.requestFocusInWindow()
        capturePanel.background = Color(255, 200, 200)
    }

    stopBtn.addActionListener {
        recording = false
        lastTime = 0L
        startBtn.isEnabled = true
        stopBtn.isEnabled = false
        capturePanel.background = UIManager.getColor("Panel.background")
    }

    clearBtn.addActionListener {
        tokens.clear()
        textArea.text = ""
    }

    saveBtn.addActionListener {
        targetField.text = tokens.joinToString(", ")
        d.dispose()
    }

    btnPanel.add(startBtn); btnPanel.add(stopBtn); btnPanel.add(clearBtn); btnPanel.add(saveBtn)

    val bottomContainer = JPanel(BorderLayout())
    bottomContainer.add(capturePanel, BorderLayout.CENTER)
    bottomContainer.add(btnPanel, BorderLayout.SOUTH)

    d.add(textScroll, BorderLayout.CENTER)
    d.add(bottomContainer, BorderLayout.SOUTH)

    d.isVisible = true
}

// --- INFO DIALOGS ---
fun showMacroInstructions(parent: JFrame) {
    val helpText = """
        <html>
        <body style='width: 450px; font-family: sans-serif;'>
        <h2>Advanced Macro Creation Guide</h2>
        <p>Macros allow you to execute sequences of keystrokes, delays, and mouse movements. Separate each action with a comma.</p>
        
        <h3>Action Types:</h3>
        <ul>
            <li><b>Tap a Key:</b> Type the key name. <i>(e.g., <b>A</b> or <b>Enter</b>)</i></li>
            <li><b>Mouse Clicks:</b> Use <b>LClick</b>, <b>RClick</b>, or <b>MClick</b>.</li>
            <li><b>Hold a Key:</b> Type the key name followed by "down". <i>(e.g., <b>Ctrl down</b>)</i></li>
            <li><b>Release a Key:</b> Type the key name followed by "up". <i>(e.g., <b>Ctrl up</b>)</i></li>
            <li><b>Static Delay:</b> Type a number to wait in milliseconds. <i>(e.g., <b>500</b>)</i></li>
            <li><b>Random Delay:</b> Type a range separated by a tilde to humanize inputs! <i>(e.g., <b>50~150</b> waits a random amount of time between 50ms and 150ms)</i></li>
            <li><b>Mouse Moves:</b> Use absolute coordinates <i>(e.g., <b>MouseAbs 1920 1080</b>)</i> or relative moves <i>(e.g., <b>MouseDelta 0 50</b> moves the mouse 50 pixels down)</i>.</li>
        </ul>
        
        <h3>Step-Through Macros:</h3>
        <p>Checking <b>Step</b> changes how the macro fires. Every time you press the paddle, it will execute <b>only the next action</b> in your list, cycling back to the start when finished.</p>
        <br>
        <p style='color: #D32F2F;'><b>⚠️  Pro-Tip for Step Macros:</b> Do not use the Live Recorder for Step macros! The recorder captures individual "down", "delay", and "up" events, meaning you will have to press the paddle 3-4 times just to type one letter. For Step macros, manually type clean, comma-separated lists like: <code>A, B, C</code>.</p>
        </body>
        </html>
    """.trimIndent()

    val label = JLabel(helpText)
    JOptionPane.showMessageDialog(parent, label, "Macro Instructions", JOptionPane.INFORMATION_MESSAGE)
}

fun showLayerInstructions(parent: JFrame) {
    val helpText = """
        <html>
        <body style='width: 400px; font-family: sans-serif;'>
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
        </body>
        </html>
    """.trimIndent()

    val label = JLabel(helpText)
    JOptionPane.showMessageDialog(parent, label, "Layer & Combo Instructions", JOptionPane.INFORMATION_MESSAGE)
}

// --- SYSTEM TRAY ---
fun setupSystemTray(frame: JFrame) {
    if (!SystemTray.isSupported()) { frame.isVisible = true; return }
    val tray = SystemTray.getSystemTray()

    var img: Image? = null
    try {
        val stream = PaddleBind::class.java.getResourceAsStream("/icon.png")
            ?: PaddleBind::class.java.classLoader.getResourceAsStream("icon.png")
        if (stream != null) {
            img = ImageIO.read(stream)
        }
    } catch (e: Exception) {}

    if (img == null) {
        val paths = arrayOf("icon.png", "app/src/main/resources/icon.png", "src/main/resources/icon.png")
        for (path in paths) {
            val f = File(path)
            if (f.exists()) {
                try {
                    img = ImageIO.read(f)
                    break
                } catch (e: Exception) {}
            }
        }
    }

    val trayImg: Image = if (img != null) {
        frame.iconImage = img
        img
    } else {
        val fallback = BufferedImage(32, 32, BufferedImage.TYPE_INT_ARGB)
        fallback.createGraphics().run {
            setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            color = Color(0, 150, 255); fillOval(4, 4, 24, 24)
            color = Color.WHITE; font = Font("Arial", Font.BOLD, 12); drawString("SL", 8, 20); dispose()
        }
        fallback
    }

    val icon = TrayIcon(trayImg, "ShadowLink")
    icon.isImageAutoSize = true
    val menu = PopupMenu().apply {
        add(MenuItem("Open").apply { addActionListener { frame.isVisible = true; frame.state = Frame.NORMAL } })
        add(MenuItem("Exit").apply { addActionListener { System.exit(0) } })
    }
    icon.popupMenu = menu
    icon.addMouseListener(object : MouseAdapter() {
        override fun mouseClicked(e: MouseEvent) { if (e.button == MouseEvent.BUTTON1) { frame.isVisible = true; frame.state = Frame.NORMAL } }
    })
    try { tray.add(icon) } catch (e: Exception) {}
    frame.addWindowStateListener { if (it.newState == Frame.ICONIFIED) frame.isVisible = false }
    frame.isVisible = !startMinimized
}