"""Progress and AI Status Bottom Bar."""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QProgressBar,
    QLabel, QPushButton
)
from PySide6.QtCore import Qt, Signal

class ProgressPanel(QWidget):
    """Bottom status bar with real-time pipeline progress and AI connection pills."""

    cancel_requested = Signal()
    review_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # Status message & Progress bar
        v_layout = QVBoxLayout()
        v_layout.setSpacing(2)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #94a3b8;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        v_layout.addWidget(self.lbl_status)
        v_layout.addWidget(self.progress_bar)
        layout.addLayout(v_layout, stretch=1)

        # AI Status Badges
        self.lbl_online_ai = QLabel("🔴 Online AI")
        self.lbl_online_ai.setStyleSheet("color: #ef4444; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")

        self.lbl_lmstudio = QLabel("🔴 LM Studio")
        self.lbl_lmstudio.setStyleSheet("color: #ef4444; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")

        layout.addWidget(self.lbl_online_ai)
        layout.addWidget(self.lbl_lmstudio)

        # Review button (triggers Review Mode)
        self.btn_review = QPushButton("🔍 Review (0)")
        self.btn_review.setObjectName("secondaryBtn")
        self.btn_review.setEnabled(False)
        self.btn_review.clicked.connect(self.review_requested.emit)
        layout.addWidget(self.btn_review)

        # Cancel button
        self.btn_cancel = QPushButton("✖ Cancel")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self.btn_cancel)

    def set_progress(self, current: int, total: int, message: str):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(message)

    def set_ai_status(self, online_ok: bool, lmstudio_ok: bool):
        if online_ok:
            self.lbl_online_ai.setText("🟢 Online AI")
            self.lbl_online_ai.setStyleSheet("color: #10b981; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")
        else:
            self.lbl_online_ai.setText("🔴 Online AI")
            self.lbl_online_ai.setStyleSheet("color: #ef4444; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")

        if lmstudio_ok:
            self.lbl_lmstudio.setText("🟢 LM Studio")
            self.lbl_lmstudio.setStyleSheet("color: #10b981; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")
        else:
            self.lbl_lmstudio.setText("🔴 LM Studio")
            self.lbl_lmstudio.setStyleSheet("color: #ef4444; font-weight: bold; padding: 2px 6px; background: #1e293b; border-radius: 4px;")

    def set_review_count(self, count: int):
        self.btn_review.setText(f"🔍 Review ({count})")
        self.btn_review.setEnabled(count > 0)
