"""
GUI Dialogs for Update Notifications and Asset Downloading.
Provides modern Fluent-style dialogs for viewing release notes,
tracking live download progress, and confirming application self-updates.
"""

from __future__ import annotations
import logging
from pathlib import Path
import sys
import time
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import config
from updater import ReleaseInfo, UpdateDownloaderThread, install_update_and_restart

logger = logging.getLogger("ShadowLink.UpdateDialog")


class UpdateAvailableDialog(QDialog):
    """
    Informs the user that a new release is available on GitHub and displays release notes.
    """

    def __init__(self, release_info: ReleaseInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.release_info = release_info
        self.setWindowTitle(f"Update Available - ShadowLink v{release_info.version_str}")
        self.setMinimumSize(540, 420)
        self.setWindowIcon(config.get_app_icon())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header with Version Info
        header_lbl = QLabel(f"A new version of ShadowLink is available!")
        header_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(header_lbl)

        sub_text = (
            f"<b>Available Version:</b> {self.release_info.version_str} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Current Version:</b> {config.APP_VERSION}"
        )
        sub_lbl = QLabel(sub_text)
        sub_lbl.setFont(QFont("Segoe UI", 10))
        sub_lbl.setStyleSheet("color: #0078d4;")
        layout.addWidget(sub_lbl)

        if self.release_info.title and self.release_info.title != self.release_info.tag_name:
            title_lbl = QLabel(f"<b>Release:</b> {self.release_info.title}")
            layout.addWidget(title_lbl)

        # Release Notes Display
        notes_hdr = QLabel("Release Notes:")
        notes_hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        layout.addWidget(notes_hdr)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        raw_notes = self.release_info.notes.strip() or "No release notes provided."
        # Simple markdown to HTML line breaks
        html_notes = raw_notes.replace("\n", "<br>")
        self.notes_browser.setHtml(f"<div style='font-family: Segoe UI, sans-serif; font-size: 10pt; line-height: 1.4;'>{html_notes}</div>")
        layout.addWidget(self.notes_browser, 1)

        # Asset info
        if self.release_info.asset_size > 0:
            mb_size = self.release_info.asset_size / (1024 * 1024)
            asset_info = f"Package: {self.release_info.asset_name} ({mb_size:.1f} MB)"
        else:
            asset_info = f"Package: {self.release_info.asset_name}"
        asset_lbl = QLabel(asset_info)
        asset_lbl.setStyleSheet("color: #888888; font-size: 9pt;")
        layout.addWidget(asset_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        github_btn = QPushButton("View on GitHub")
        github_btn.clicked.connect(self._on_view_github)
        btn_layout.addWidget(github_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Later")
        cancel_btn.setMinimumWidth(90)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.download_btn = QPushButton("Download and Install")
        self.download_btn.setObjectName("accentButton")
        self.download_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.download_btn.setMinimumWidth(160)
        self.download_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.download_btn)

        layout.addLayout(btn_layout)

    def _on_view_github(self) -> None:
        url = self.release_info.html_url or f"https://github.com/{config.GITHUB_REPO}/releases"
        QDesktopServices.openUrl(QUrl(url))


class DownloadProgressDialog(QDialog):
    """
    Modal progress dialog for downloading release assets.
    Tracks speed and total transferred bytes.
    """

    def __init__(self, release_info: ReleaseInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.release_info = release_info
        self.setWindowTitle("Downloading Update - ShadowLink")
        self.setMinimumSize(460, 180)
        self.setWindowIcon(config.get_app_icon())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.title_lbl = QLabel(f"Downloading ShadowLink v{release_info.version_str}...")
        self.title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.title_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Connecting to GitHub...")
        self.status_lbl.setStyleSheet("color: #888888; font-size: 9pt;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Prepare download target in AppData/temp or directory next to executable
        self.start_time = time.time()
        self.last_bytes = 0

        target_dir = config.DEFAULT_DATA_DIR / "updates"
        target_dir.mkdir(parents=True, exist_ok=True)
        ext = ".zip" if release_info.is_zip else ".exe"
        self.target_file = target_dir / f"ShadowLink_{release_info.version_str}{ext}"

        # Initialize worker thread
        self.worker = UpdateDownloaderThread(release_info.download_url, self.target_file, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, bytes_read: int, total_bytes: int) -> None:
        if total_bytes > 0:
            pct = int((bytes_read / total_bytes) * 100)
            self.progress_bar.setValue(min(100, max(0, pct)))

            mb_read = bytes_read / (1024 * 1024)
            mb_total = total_bytes / (1024 * 1024)

            elapsed = max(0.1, time.time() - self.start_time)
            speed_kbps = (bytes_read / 1024) / elapsed
            if speed_kbps >= 1024:
                speed_str = f"{speed_kbps / 1024:.1f} MB/s"
            else:
                speed_str = f"{speed_kbps:.0f} KB/s"

            self.status_lbl.setText(f"{mb_read:.1f} MB of {mb_total:.1f} MB ({pct}%) • {speed_str}")
        else:
            mb_read = bytes_read / (1024 * 1024)
            self.progress_bar.setRange(0, 0)  # Indeterminate
            self.status_lbl.setText(f"Downloaded {mb_read:.1f} MB...")

    def _on_finished(self, success: bool, message: str, file_path_str: str) -> None:
        if not success:
            if message != "Download cancelled.":
                QMessageBox.critical(self, "Download Error", f"Failed to download update:\n\n{message}")
            self.reject()
            return

        self.status_lbl.setText("Download complete! Preparing to install...")
        self.progress_bar.setValue(100)

        # Trigger installation
        file_path = Path(file_path_str)
        is_frozen = getattr(sys, "frozen", False)

        success, install_msg = install_update_and_restart(file_path)
        if success:
            if is_frozen:
                QMessageBox.information(
                    self,
                    "Installing Update",
                    "Update downloaded successfully!\n\nShadowLink will now close and restart with the new version.",
                )
                self.accept()
                QApplication.quit()
                sys.exit(0)
            else:
                QMessageBox.information(
                    self,
                    "Update Ready",
                    f"Update downloaded successfully!\n\n{install_msg}",
                )
                self.accept()
        else:
            QMessageBox.critical(
                self,
                "Installation Error",
                f"Could not apply update automatically:\n\n{install_msg}\n\nYou can manually download the release from GitHub.",
            )
            self.reject()

    def _on_cancel(self) -> None:
        self.worker.cancel()
        self.status_lbl.setText("Cancelling download...")
        self.cancel_btn.setEnabled(False)
        self.worker.wait(2000)
        self.reject()

    def closeEvent(self, event) -> None:
        self.worker.cancel()
        self.worker.wait(1000)
        super().closeEvent(event)

