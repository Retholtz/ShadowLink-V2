package com.retholtz.shadowlink

import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.URI
import java.util.Properties
import javax.swing.JFrame
import javax.swing.JOptionPane
import javax.swing.SwingUtilities

// --- PERSISTENCE & SYSTEM ---

fun loadAllProfiles() {
    Logger.info("Loading profiles from ${rootDir.absolutePath}")
    val files = rootDir.listFiles { _, name -> name.endsWith(".properties") }
    if (files.isNullOrEmpty()) {
        val default = Profile(name = "Default")
        profiles.add(default)
        activeProfile = default
        saveProfile(default)
        Logger.info("No profiles found. Created default profile.")
    } else {
        files.forEach { file ->
            val props = Properties()
            FileInputStream(file).use { props.load(it) }
            val p = Profile(name = file.nameWithoutExtension)
            p.targetProcess = props.getProperty("TARGET_PROCESS", "")
            p.toggleButton1 = props.getProperty("TOGGLE_BTN_1", "None")
            p.toggleButton2 = props.getProperty("TOGGLE_BTN_2", "None")
            p.comboBufferMs = props.getProperty("COMBO_BUFFER_MS", "30").toIntOrNull() ?: 30

            fun loadB(prefix: String, b: PaddleBind, expectedDefault: String? = null) {
                b.enabled = props.getProperty("${prefix}_EN", b.enabled.toString()).toBoolean()
                b.isMacro = props.getProperty("${prefix}_MAC", "false").toBoolean()
                b.repeatMacro = props.getProperty("${prefix}_REP", "false").toBoolean()
                b.stepThrough = props.getProperty("${prefix}_STP", "false").toBoolean()
                b.macroText = props.getProperty("${prefix}_TXT", "")

                val loadedKey = props.getProperty("${prefix}_KEY", b.keyChar)
                if (expectedDefault != null && loadedKey == "A") {
                    b.keyChar = expectedDefault
                } else {
                    b.keyChar = loadedKey
                }

                b.shift = props.getProperty("${prefix}_SH", "false").toBoolean()
                b.ctrl = props.getProperty("${prefix}_CT", "false").toBoolean()
                b.alt = props.getProperty("${prefix}_AL", "false").toBoolean()
                b.win = props.getProperty("${prefix}_WI", "false").toBoolean()
            }

            for (i in 0 until 5) {
                val suffix = if (i == 0) "" else "_L${i+1}"
                p.layers[i].name = props.getProperty("LAYER${i+1}_NAME", "Layer ${i+1}")
                p.layers[i].enabled = props.getProperty("LAYER${i+1}_EN", if (i == 0) "true" else "false").toBoolean()

                loadB("M1$suffix", p.layers[i].m1); loadB("M2$suffix", p.layers[i].m2)
                loadB("M3$suffix", p.layers[i].m3); loadB("M4$suffix", p.layers[i].m4)
                loadB("CMD$suffix", p.layers[i].cmd); loadB("LIB$suffix", p.layers[i].lib)

                loadB("LB$suffix", p.layers[i].lb, "Xbox_LB"); loadB("RB$suffix", p.layers[i].rb, "Xbox_RB")
                loadB("LT$suffix", p.layers[i].lt, "Xbox_LT"); loadB("RT$suffix", p.layers[i].rt, "Xbox_RT")
                loadB("A$suffix", p.layers[i].a, "Xbox_A"); loadB("B$suffix", p.layers[i].b, "Xbox_B")
                loadB("X$suffix", p.layers[i].x, "Xbox_X"); loadB("Y$suffix", p.layers[i].y, "Xbox_Y")
                loadB("L3$suffix", p.layers[i].l3, "Xbox_L3"); loadB("R3$suffix", p.layers[i].r3, "Xbox_R3")
                loadB("DUP$suffix", p.layers[i].dUp, "Xbox_DUp"); loadB("DDOWN$suffix", p.layers[i].dDown, "Xbox_DDown")
                loadB("DLEFT$suffix", p.layers[i].dLeft, "Xbox_DLeft"); loadB("DRIGHT$suffix", p.layers[i].dRight, "Xbox_DRight")

                loadB("M1M2$suffix", p.layers[i].m1_m2); loadB("M1M3$suffix", p.layers[i].m1_m3)
                loadB("M1M4$suffix", p.layers[i].m1_m4); loadB("M2M3$suffix", p.layers[i].m2_m3)
                loadB("M2M4$suffix", p.layers[i].m2_m4); loadB("M3M4$suffix", p.layers[i].m3_m4)
                loadB("CMDLIB$suffix", p.layers[i].cmd_lib)
            }

            profiles.add(p)
        }

        if (globalConfigFile.exists()) {
            val global = Properties()
            FileInputStream(globalConfigFile).use { global.load(it) }
            val lastActive = global.getProperty("ACTIVE_PROFILE", "Default")
            autoSwitchEnabled = global.getProperty("AUTO_SWITCH", "true").toBoolean()
            startMinimized = global.getProperty("START_MINIMIZED", "false").toBoolean()
            loadOnStartup = global.getProperty("LOAD_ON_STARTUP", "false").toBoolean()
            isDarkMode = global.getProperty("DARK_MODE", "true").toBoolean()
            osdPosition = global.getProperty("OSD_POSITION", "Bottom Right")
            controllerScanInterval = global.getProperty("SCAN_INTERVAL", "5000").toIntOrNull() ?: 5000

            activeProfile = profiles.find { it.name == lastActive } ?: profiles[0]
        } else {
            activeProfile = profiles[0]
        }
    }
}

fun saveProfile(p: Profile) {
    val props = Properties()
    props.setProperty("TARGET_PROCESS", p.targetProcess)
    props.setProperty("TOGGLE_BTN_1", p.toggleButton1)
    props.setProperty("TOGGLE_BTN_2", p.toggleButton2)
    props.setProperty("COMBO_BUFFER_MS", p.comboBufferMs.toString())

    fun saveB(prefix: String, b: PaddleBind) {
        props.setProperty("${prefix}_EN", b.enabled.toString())
        props.setProperty("${prefix}_MAC", b.isMacro.toString())
        props.setProperty("${prefix}_REP", b.repeatMacro.toString())
        props.setProperty("${prefix}_STP", b.stepThrough.toString())
        props.setProperty("${prefix}_TXT", b.macroText)
        props.setProperty("${prefix}_KEY", b.keyChar)
        props.setProperty("${prefix}_SH", b.shift.toString())
        props.setProperty("${prefix}_CT", b.ctrl.toString())
        props.setProperty("${prefix}_AL", b.alt.toString())
        props.setProperty("${prefix}_WI", b.win.toString())
    }

    for (i in 0 until 5) {
        val suffix = if (i == 0) "" else "_L${i+1}"
        props.setProperty("LAYER${i+1}_NAME", p.layers[i].name)
        props.setProperty("LAYER${i+1}_EN", p.layers[i].enabled.toString())

        saveB("M1$suffix", p.layers[i].m1); saveB("M2$suffix", p.layers[i].m2)
        saveB("M3$suffix", p.layers[i].m3); saveB("M4$suffix", p.layers[i].m4)
        saveB("CMD$suffix", p.layers[i].cmd); saveB("LIB$suffix", p.layers[i].lib)

        saveB("LB$suffix", p.layers[i].lb); saveB("RB$suffix", p.layers[i].rb)
        saveB("LT$suffix", p.layers[i].lt); saveB("RT$suffix", p.layers[i].rt)
        saveB("A$suffix", p.layers[i].a); saveB("B$suffix", p.layers[i].b)
        saveB("X$suffix", p.layers[i].x); saveB("Y$suffix", p.layers[i].y)
        saveB("L3$suffix", p.layers[i].l3); saveB("R3$suffix", p.layers[i].r3)
        saveB("DUP$suffix", p.layers[i].dUp); saveB("DDOWN$suffix", p.layers[i].dDown)
        saveB("DLEFT$suffix", p.layers[i].dLeft); saveB("DRIGHT$suffix", p.layers[i].dRight)

        saveB("M1M2$suffix", p.layers[i].m1_m2); saveB("M1M3$suffix", p.layers[i].m1_m3)
        saveB("M1M4$suffix", p.layers[i].m1_m4); saveB("M2M3$suffix", p.layers[i].m2_m3)
        saveB("M2M4$suffix", p.layers[i].m2_m4); saveB("M3M4$suffix", p.layers[i].m3_m4)
        saveB("CMDLIB$suffix", p.layers[i].cmd_lib)
    }

    FileOutputStream(File(rootDir, "${p.name}.properties")).use { props.store(it, null) }
    Logger.info("Saved profile '${p.name}'")
}

fun saveGlobalConfig() {
    val props = Properties()
    props.setProperty("ACTIVE_PROFILE", activeProfile.name)
    props.setProperty("AUTO_SWITCH", autoSwitchEnabled.toString())
    props.setProperty("START_MINIMIZED", startMinimized.toString())
    props.setProperty("LOAD_ON_STARTUP", loadOnStartup.toString())
    props.setProperty("DARK_MODE", isDarkMode.toString())
    props.setProperty("OSD_POSITION", osdPosition)
    props.setProperty("SCAN_INTERVAL", controllerScanInterval.toString())

    FileOutputStream(globalConfigFile).use { props.store(it, null) }
    Logger.info("Saved global configuration")
}

fun updateStartupRegistry(enable: Boolean) {
    try {
        val appName = "ShadowLink"
        val path = File(PaddleBind::class.java.protectionDomain.codeSource.location.toURI()).absolutePath

        val domain = System.getenv("USERDOMAIN") ?: System.getenv("COMPUTERNAME") ?: ""
        val user = System.getenv("USERNAME") ?: System.getProperty("user.name") ?: ""
        val currentUser = if (domain.isNotEmpty()) "$domain\\$user" else user

        val psScriptText = if (enable) {
            val isJar = path.lowercase().endsWith(".jar")
            val isExe = path.lowercase().endsWith(".exe")

            // Allow testing the creation process even inside the IDE
            val targetExe = if (isJar || (!isJar && !isExe)) File(System.getProperty("java.home"), "bin\\javaw.exe").absolutePath else path
            val args = if (isJar) "-jar \"$path\"" else ""
            val workingDir = File(path).parentFile.absolutePath

            """
                try {
                    ${'$'}Action = New-ScheduledTaskAction -Execute '$targetExe' ${if (args.isNotEmpty()) "-Argument '$args'" else ""} -WorkingDirectory '$workingDir'
                    ${'$'}Trigger = New-ScheduledTaskTrigger -AtLogOn
                    ${'$'}Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
                    ${'$'}Principal = New-ScheduledTaskPrincipal -UserId '$currentUser' -LogonType Interactive -RunLevel Highest
                    Register-ScheduledTask -TaskName '$appName' -Action ${'$'}Action -Trigger ${'$'}Trigger -Settings ${'$'}Settings -Principal ${'$'}Principal -Force
                } catch {}
            """.trimIndent()
        } else {
            """
                try {
                    Unregister-ScheduledTask -TaskName '$appName' -Confirm:${'$'}false
                } catch {}
            """.trimIndent()
        }

        val tempScript = File.createTempFile("ShadowLink_Startup", ".ps1")
        tempScript.writeText(psScriptText)

        val uacCommand = "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"${tempScript.absolutePath}\"' -Verb RunAs -Wait"
        val outerBase64 = java.util.Base64.getEncoder().encodeToString(uacCommand.toByteArray(Charsets.UTF_16LE))

        Runtime.getRuntime().exec(arrayOf("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", outerBase64)).waitFor()
        tempScript.delete()

    } catch (e: Exception) {
        Logger.error("Failed to update startup registry task", e)
    }
}

// --- UPDATER ---
fun checkForUpdates(parent: JFrame, silent: Boolean = false) {
    Thread {
        try {
            Logger.info("Checking for application updates from GitHub...")
            val apiUrl = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
            val connection = URI(apiUrl).toURL().openConnection() as java.net.HttpURLConnection
            connection.setRequestProperty("Accept", "application/vnd.github.v3+json")

            if (connection.responseCode != 200) {
                Logger.warn("GitHub API check returned status ${connection.responseCode}")
                if (!silent) SwingUtilities.invokeLater { JOptionPane.showMessageDialog(parent, "Could not check for updates. GitHub API returned: ${connection.responseCode}") }
                return@Thread
            }

            val response = connection.inputStream.bufferedReader().use { it.readText() }
            val tagMatch = "\"tag_name\":\\s*\"v?([^\"]+)\"".toRegex().find(response)
            val latestVersion = tagMatch?.groups?.get(1)?.value

            if (latestVersion == null) {
                if (!silent) SwingUtilities.invokeLater { JOptionPane.showMessageDialog(parent, "Failed to parse version from GitHub.") }
                return@Thread
            }

            if (latestVersion <= APP_VERSION) {
                if (!silent) SwingUtilities.invokeLater { JOptionPane.showMessageDialog(parent, "You are up to date! (Version $APP_VERSION)") }
                return@Thread
            }

            // Always show popup if there IS a new update available
            val currentFile = File(PaddleBind::class.java.protectionDomain.codeSource.location.toURI())
            val extension = if (currentFile.name.endsWith(".jar", true)) ".jar" else ".exe"

            val urlMatch = "\"browser_download_url\":\\s*\"([^\"]+\\$extension)\"".toRegex().find(response)
            val downloadUrl = urlMatch?.groups?.get(1)?.value

            if (downloadUrl == null) {
                if (!silent) SwingUtilities.invokeLater { JOptionPane.showMessageDialog(parent, "Update found (v$latestVersion), but no $extension asset was found.") }
                return@Thread
            }

            val choice = JOptionPane.showConfirmDialog(parent, "Version $latestVersion is available!\n\nWould you like to download and install it now?", "Update Available", JOptionPane.YES_NO_OPTION)
            if (choice != JOptionPane.YES_OPTION) return@Thread

            val updateFile = File(currentFile.parentFile, "ShadowLink_Update$extension")
            URI(downloadUrl).toURL().openStream().use { input ->
                FileOutputStream(updateFile).use { output ->
                    input.copyTo(output)
                }
            }

            val batFile = File(currentFile.parentFile, "updater.bat")
            val batContent = """
                @echo off
                cd /d "%~dp0"
                timeout /t 2 /nobreak > nul
                del "${currentFile.name}"
                ren "${updateFile.name}" "${currentFile.name}"
                start "" "${currentFile.name}"
                del "%~f0" & exit
            """.trimIndent()
            batFile.writeText(batContent)

            val pb = ProcessBuilder("cmd", "/c", "start", "", batFile.absolutePath)
            pb.directory(currentFile.parentFile)
            pb.start()
            System.exit(0)

        } catch (e: Exception) {
            Logger.error("Error checking for updates", e)
            if (!silent) SwingUtilities.invokeLater { JOptionPane.showMessageDialog(parent, "Error checking for updates: ${e.message}") }
        }
    }.start()
}