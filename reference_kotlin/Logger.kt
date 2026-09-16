package com.retholtz.shadowlink

import java.awt.Component
import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.swing.JFileChooser
import javax.swing.JOptionPane
import javax.swing.filechooser.FileNameExtensionFilter

object Logger {
    private val logsDir = File(dataDir, "logs").apply { if (!exists()) mkdirs() }
    val logFile = File(logsDir, "shadowlink.log")
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    private const val MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024L // 2MB log limit

    @Synchronized
    fun log(level: String, message: String, throwable: Throwable? = null) {
        val timestamp = dateFormat.format(Date())
        val threadName = Thread.currentThread().name
        val formattedMsg = "[$timestamp] [$level] [$threadName] $message"

        println(formattedMsg)
        throwable?.printStackTrace()

        try {
            rotateLogIfNeeded()
            PrintWriter(FileWriter(logFile, true)).use { writer ->
                writer.println(formattedMsg)
                throwable?.printStackTrace(writer)
            }
        } catch (e: Exception) {
            System.err.println("Failed to write to log file: ${e.message}")
        }
    }

    fun info(message: String) = log("INFO", message)
    fun warn(message: String, throwable: Throwable? = null) = log("WARN", message, throwable)
    fun error(message: String, throwable: Throwable? = null) = log("ERROR", message, throwable)
    fun debug(message: String) = log("DEBUG", message)

    private fun rotateLogIfNeeded() {
        if (logFile.exists() && (logFile.length() > MAX_FILE_SIZE_BYTES)) {
            val oldFile = File(logsDir, "shadowlink_old.log")
            if (oldFile.exists()) oldFile.delete()
            logFile.renameTo(oldFile)
        }
    }

    fun exportLogs(parent: Component?) {
        val dateStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val defaultFileName = "ShadowLink_Log_$dateStamp.txt"

        val chooser = JFileChooser().apply {
            dialogTitle = "Export ShadowLink Diagnostic Log"
            selectedFile = File(defaultFileName)
            fileFilter = FileNameExtensionFilter("Log Files (*.txt, *.log)", "txt", "log")
        }

        if (chooser.showSaveDialog(parent) == JFileChooser.APPROVE_OPTION) {
            try {
                var targetFile = chooser.selectedFile
                if (!targetFile.name.endsWith(".txt") && !targetFile.name.endsWith(".log")) {
                    targetFile = File(targetFile.parentFile, "${targetFile.name}.txt")
                }

                PrintWriter(FileWriter(targetFile)).use { writer ->
                    writer.println("==================================================")
                    writer.println("ShadowLink Diagnostic Log Export")
                    writer.println("Export Date: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())}")
                    writer.println("App Version: $APP_VERSION")
                    writer.println("OS: ${System.getProperty("os.name")} ${System.getProperty("os.version")} (${System.getProperty("os.arch")})")
                    writer.println("Java Version: ${System.getProperty("java.version")} (${System.getProperty("java.vendor")})")
                    writer.println("Active Profile: ${activeProfile.name}")
                    writer.println("USB Dongle Status: ${usbDongleStatus.label} ($usbDongleDetails)")
                    writer.println("Controller Link Status: ${controllerLinkStatus.label} ($controllerLinkDetails)")
                    writer.println("==================================================")
                    writer.println()

                    if (logFile.exists()) {
                        logFile.useLines { lines ->
                            lines.forEach { writer.println(it) }
                        }
                    } else {
                        writer.println("No prior log file entries found.")
                    }
                }

                JOptionPane.showMessageDialog(
                    parent,
                    "Log file exported successfully to:\n${targetFile.absolutePath}",
                    "Log Exported",
                    JOptionPane.INFORMATION_MESSAGE,
                )
                info("Diagnostic log exported to ${targetFile.absolutePath}")
            } catch (e: Exception) {
                error("Failed to export log file", e)
                JOptionPane.showMessageDialog(
                    parent,
                    "Failed to export log file:\n${e.message}",
                    "Export Error",
                    JOptionPane.ERROR_MESSAGE,
                )
            }
        }
    }
}
