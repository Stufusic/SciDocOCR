"""AI Chat Assistant Panel with Dynamic Multi-Provider Live Model Discovery and Document Q&A."""

import re
import os
from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPlainTextEdit, QTextBrowser, QPushButton, QCheckBox,
    QProgressBar, QFrame, QLineEdit, QGroupBox
)
from PySide6.QtGui import QFont, QTextCursor, QKeyEvent
from PySide6.QtCore import Qt, Signal, QThread, QObject
from app.ai.router import AIRouter
from app.ai.online import OnlineProvider
from app.ai.lmstudio import LMStudioProvider
from app.ai.model_fetcher import fetch_available_models, DEFAULT_URLS
from app.network.lmstudio_checker import LMStudioChecker
from app.storage.settings import SettingsManager
from app.core.document import Document
from app.utils.logging import get_logger

logger = get_logger("AIChatPanel")

CHAT_PROVIDERS = {
    "Google Gemini": "google",
    "LM Studio (Local)": "lmstudio",
    "OpenAI": "openai",
    "Anthropic Claude": "anthropic",
    "OpenCode / OpenRouter": "opencode",
    "Custom (OpenAI-compatible)": "custom"
}

class ChatWorker(QThread):
    """Background worker for executing LLM chat completion without freezing UI."""
    response_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, provider_obj, prompt: str, system_prompt: str = "", parent: Optional[QObject] = None):
        super().__init__(parent)
        self.provider_obj = provider_obj
        self.prompt = prompt
        self.system_prompt = system_prompt
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return
            res = self.provider_obj.complete(
                prompt=self.prompt,
                system_prompt=self.system_prompt,
                temperature=0.3,
                max_tokens=4096
            )
            if not self._is_cancelled:
                self.response_ready.emit(res)
        except Exception as e:
            if not self._is_cancelled:
                self.error_occurred.emit(str(e))

class ChatInputEdit(QPlainTextEdit):
    """Custom input edit that sends on Enter (Shift+Enter for new line)."""
    return_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.return_pressed.emit()
        else:
            super().keyPressEvent(event)

class AIChatPanel(QWidget):
    """Interactive multi-model AI Chat Assistant for SciDoc OCR with dynamic model querying."""

    def __init__(self, ai_router: AIRouter, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ai_router = ai_router
        self.settings_manager = SettingsManager()
        self.current_document: Optional[Document] = None
        self.chat_history: List[Dict[str, str]] = []
        self.current_worker: Optional[ChatWorker] = None

        self._init_ui()
        self._sync_with_settings()

    def set_document(self, doc: Optional[Document]):
        """Sets the active document context for Q&A."""
        self.current_document = doc
        if doc and doc.metadata.title:
            self.lbl_doc_badge.setText(f"📄 Ngữ cảnh: {doc.metadata.title[:35]}")
            self.lbl_doc_badge.setVisible(True)
        else:
            self.lbl_doc_badge.setVisible(False)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Top Controls Bar: Row 1 (Provider & Model Selection)
        row1_bar = QHBoxLayout()
        row1_bar.setSpacing(6)

        lbl_prov = QLabel("Nhà cung cấp:")
        lbl_prov.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")
        row1_bar.addWidget(lbl_prov)

        self.combo_provider = QComboBox()
        self.combo_provider.addItems(list(CHAT_PROVIDERS.keys()))
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        row1_bar.addWidget(self.combo_provider)

        lbl_model = QLabel("Mô hình:")
        lbl_model.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")
        row1_bar.addWidget(lbl_model)

        self.combo_model = QComboBox()
        self.combo_model.setEditable(True)
        self.combo_model.lineEdit().setPlaceholderText("Đang tải danh sách mô hình...")
        row1_bar.addWidget(self.combo_model, stretch=1)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Quét lại danh sách mô hình trực tiếp từ API")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.setFixedWidth(32)
        self.btn_refresh.clicked.connect(self._fetch_live_models)
        row1_bar.addWidget(self.btn_refresh)

        layout.addLayout(row1_bar)

        # Row 2 (Quick Actions & Status)
        row2_bar = QHBoxLayout()
        row2_bar.setSpacing(6)

        self.btn_toggle_config = QPushButton("⚙ API/URL")
        self.btn_toggle_config.setToolTip("Xem và chỉnh sửa API Key / Base URL nhanh")
        self.btn_toggle_config.setObjectName("secondaryBtn")
        self.btn_toggle_config.clicked.connect(self._toggle_config_box)
        row2_bar.addWidget(self.btn_toggle_config)

        self.btn_clear = QPushButton("🧹 Xóa")
        self.btn_clear.setToolTip("Làm sạch lịch sử đoạn chat")
        self.btn_clear.setObjectName("secondaryBtn")
        self.btn_clear.clicked.connect(self._clear_chat)
        row2_bar.addWidget(self.btn_clear)

        self.lbl_models_status = QLabel("Đang khởi tạo kết nối mô hình...")
        self.lbl_models_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        row2_bar.addWidget(self.lbl_models_status, stretch=1)

        self.chk_attach_doc = QCheckBox("Gửi kèm ngữ cảnh PDF")
        self.chk_attach_doc.setChecked(True)
        self.chk_attach_doc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        row2_bar.addWidget(self.chk_attach_doc)

        layout.addLayout(row2_bar)

        # 2. Quick API / URL Inline Box (Collapsible)
        self.config_box = QGroupBox("Cấu hình Kết nối API Nhanh")
        self.config_box.setVisible(False)
        cfg_layout = QVBoxLayout(self.config_box)
        cfg_layout.setContentsMargins(8, 6, 8, 6)
        cfg_layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("API Key:"))
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.Password)
        self.txt_api_key.setPlaceholderText("Nhập API Key (AIzaSy... / sk-...)...")
        row1.addWidget(self.txt_api_key, stretch=1)

        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedWidth(30)
        self.btn_toggle_key.clicked.connect(self._toggle_key_vis)
        row1.addWidget(self.btn_toggle_key)
        cfg_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Base URL:"))
        self.txt_base_url = QLineEdit()
        self.txt_base_url.setPlaceholderText("Endpoint URL (để trống nếu dùng mặc định)...")
        row2.addWidget(self.txt_base_url, stretch=1)

        self.btn_save_config = QPushButton("💾 Lưu & Kết nối")
        self.btn_save_config.setObjectName("accentBtn")
        self.btn_save_config.clicked.connect(self._save_quick_config)
        row2.addWidget(self.btn_save_config)
        cfg_layout.addLayout(row2)

        layout.addWidget(self.config_box)

        # Status & Context Info Bar
        info_bar = QHBoxLayout()
        self.lbl_models_status = QLabel("Đang khởi tạo kết nối mô hình...")
        self.lbl_models_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        info_bar.addWidget(self.lbl_models_status)

        info_bar.addStretch()

        self.chk_attach_doc = QCheckBox("Gửi kèm ngữ cảnh PDF hiện tại")
        self.chk_attach_doc.setChecked(True)
        self.chk_attach_doc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        info_bar.addWidget(self.chk_attach_doc)

        layout.addLayout(info_bar)

        self.lbl_doc_badge = QLabel("")
        self.lbl_doc_badge.setStyleSheet("color: #38bdf8; font-size: 11px; font-style: italic;")
        self.lbl_doc_badge.setVisible(False)
        layout.addWidget(self.lbl_doc_badge)

        # 3. Chat History Display Area
        self.chat_display = QTextBrowser()
        self.chat_display.setFont(QFont("Segoe UI", 10))
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        layout.addWidget(self.chat_display, stretch=1)

        # 4. Input & Send Area
        bottom_bar = QVBoxLayout()
        bottom_bar.setSpacing(4)

        input_box = QHBoxLayout()
        input_box.setSpacing(6)

        self.txt_input = ChatInputEdit()
        self.txt_input.setFont(QFont("Segoe UI", 10))
        self.txt_input.setFixedHeight(64)
        self.txt_input.setPlaceholderText("Nhập câu hỏi về tài liệu, công thức toán, hoặc yêu cầu dịch... (Enter để gửi, Shift+Enter xuống dòng)")
        self.txt_input.return_pressed.connect(self._send_message)
        input_box.addWidget(self.txt_input, stretch=1)

        self.btn_send = QPushButton("Gửi 🚀")
        self.btn_send.setObjectName("accentBtn")
        self.btn_send.setFixedSize(76, 64)
        self.btn_send.clicked.connect(self._send_message)
        input_box.addWidget(self.btn_send)

        bottom_bar.addLayout(input_box)

        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Sẵn sàng.")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 11px;")
        status_row.addWidget(self.lbl_status)

        status_row.addStretch()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        status_row.addWidget(self.progress_bar)

        bottom_bar.addLayout(status_row)
        layout.addLayout(bottom_bar)

        # Add initial welcome message
        self._append_ai_message(
            "SciDoc AI Assistant",
            "Xin chào! Tôi là trợ lý AI phân tích tài liệu khoa học. "
            "Toàn bộ mô hình trực tiếp từ Google Gemini, OpenAI, Claude hoặc LM Studio đã được quét và tải vào danh sách trên."
        )

    def _sync_with_settings(self):
        """Loads configured keys from SettingsManager and refreshes models."""
        self.settings_manager = SettingsManager()
        s = self.settings_manager.settings

        # Match active provider in settings
        active_prov = s.online_provider or "google"
        for name, key in CHAT_PROVIDERS.items():
            if key == active_prov:
                self.combo_provider.setCurrentText(name)
                break

        self._on_provider_changed()

    def _toggle_config_box(self):
        self.config_box.setVisible(not self.config_box.isVisible())

    def _toggle_key_vis(self):
        if self.txt_api_key.echoMode() == QLineEdit.Password:
            self.txt_api_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.txt_api_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("👁")

    def _get_current_provider_code(self) -> str:
        return CHAT_PROVIDERS.get(self.combo_provider.currentText(), "google")

    def _on_provider_changed(self):
        prov = self._get_current_provider_code()
        s = self.settings_manager.settings

        if prov == "lmstudio":
            self.txt_api_key.setText("")
            self.txt_base_url.setText(s.lmstudio_url)
        else:
            k = s.provider_keys.get(prov, "")
            u = s.provider_urls.get(prov, "") or DEFAULT_URLS.get(prov, "")
            self.txt_api_key.setText(k)
            self.txt_base_url.setText(u)

        self._fetch_live_models()

    def _save_quick_config(self):
        prov = self._get_current_provider_code()
        s = self.settings_manager.settings

        key = self.txt_api_key.text().strip()
        url = self.txt_base_url.text().strip()

        if prov == "lmstudio":
            s.lmstudio_url = url or "http://127.0.0.1:1234/v1"
        else:
            s.provider_keys[prov] = key
            s.provider_urls[prov] = url or DEFAULT_URLS.get(prov, "")
            if s.online_provider == prov:
                s.online_api_key = key
                s.online_api_url = url

        self.settings_manager.save_settings(s)
        self.lbl_models_status.setText("✓ Đã lưu cấu hình. Đang đồng bộ mô hình...")
        self._fetch_live_models()

    def _fetch_live_models(self):
        """Fetches models from the provider dynamically."""
        prov = self._get_current_provider_code()
        s = self.settings_manager.settings

        self.lbl_models_status.setText(f"Đang kết nối {self.combo_provider.currentText()} để lấy danh sách model...")
        self.combo_model.clear()

        if prov == "lmstudio":
            url = self.txt_base_url.text().strip() or s.lmstudio_url
            checker = LMStudioChecker(url)
            ok, models, err = checker.check_availability()
            if ok and models:
                self.combo_model.addItems(models)
                self.lbl_models_status.setText(f"✓ Tìm thấy {len(models)} model cục bộ trong LM Studio.")
            else:
                self.combo_model.addItems(["qwen/qwen3.5-9b", "local-model"])
                self.lbl_models_status.setText("Chế độ LM Studio Offline (Chưa phát hiện model chạy sẵn).")
        else:
            key = self.txt_api_key.text().strip() or s.provider_keys.get(prov, "")
            url = self.txt_base_url.text().strip() or s.provider_urls.get(prov, "")
            target_saved_model = s.provider_models.get(prov, "") or s.online_model

            models = fetch_available_models(prov, key, url)
            self.combo_model.addItems(models)

            if target_saved_model and target_saved_model in models:
                self.combo_model.setCurrentText(target_saved_model)
            elif models:
                self.combo_model.setCurrentIndex(0)

            if key:
                self.lbl_models_status.setText(f"✓ Đã kết nối và nạp {len(models)} model khả dụng từ {self.combo_provider.currentText()}.")
            else:
                self.lbl_models_status.setText("Chưa có API Key. Bấm [⚙ API/URL] để nhập key.")

    def _get_provider_for_chat(self) -> Any:
        prov = self._get_current_provider_code()
        model = self.combo_model.currentText().strip()
        key = self.txt_api_key.text().strip()
        url = self.txt_base_url.text().strip()

        if prov == "lmstudio":
            return LMStudioProvider(base_url=url or "http://127.0.0.1:1234/v1", model_name=model)
        else:
            return OnlineProvider(
                provider=prov,
                api_key=key,
                base_url=url,
                model_name=model
            )

    def _send_message(self):
        prompt = self.txt_input.toPlainText().strip()
        if not prompt:
            return

        if self.current_worker and self.current_worker.isRunning():
            return

        # Display user message
        self._append_user_message(prompt)
        self.txt_input.clear()

        # Build context if enabled
        system_prompt = (
            "Bạn là trợ lý AI chuyên gia về tài liệu khoa học, toán học, vật lý và công nghệ. "
            "Trả lời câu hỏi rõ ràng, chi tiết, chính xác, sử dụng định dạng Markdown và công thức LaTeX ($ ... $ hoặc $$ ... $$) khi cần thiết."
        )

        if self.chk_attach_doc.isChecked() and self.current_document:
            doc_context = ""
            for p in self.current_document.pages[:5]:  # include first few pages
                p_text = "\n".join([getattr(b, "text", "") for b in p.blocks if getattr(b, "text", "")])
                if p_text:
                    doc_context += f"\n--- Trang {p.page_number} ---\n" + p_text[:1500]
            if doc_context:
                system_prompt += f"\n\nNgữ cảnh tài liệu hiện tại:\n{doc_context[:6000]}"

        # Provider instance
        provider = self._get_provider_for_chat()
        model_display = f"{self.combo_provider.currentText()} ({self.combo_model.currentText()})"

        # Update UI state
        self.btn_send.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText(f"Đang gửi yêu cầu tới {model_display}...")

        # Start worker
        self.current_worker = ChatWorker(provider, prompt, system_prompt, self)
        self.current_worker.response_ready.connect(lambda res, m=model_display: self._on_ai_response(res, m))
        self.current_worker.error_occurred.connect(self._on_ai_error)
        self.current_worker.start()

    def _on_ai_response(self, response: str, model_name: str):
        from app.utils.thought_cleaner import strip_thought_content
        cleaned_response = strip_thought_content(response)
        self.btn_send.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Sẵn sàng.")
        self._append_ai_message(model_name, cleaned_response)
        self.current_worker = None

    def _on_ai_error(self, err: str):
        self.btn_send.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Lỗi: {err[:50]}")
        self._append_ai_message("Lỗi kết nối", f"⚠️ Không thể nhận phản hồi từ AI:\n`{err}`\n\nVui lòng kiểm tra lại API Key hoặc endpoint.")
        self.current_worker = None

    def _format_markdown_html(self, text: str) -> str:
        """Converts Markdown text into clean HTML without thinking artifacts."""
        from app.utils.thought_cleaner import strip_thought_content
        formatted = strip_thought_content(text)
        formatted = formatted.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Code blocks ```...```
        formatted = re.sub(
            r"```([a-zA-Z0-9_-]*)\n([\s\S]*?)```",
            r'<pre style="background: #1e293b; padding: 8px; border-radius: 4px; border: 1px solid #475569; overflow-x: auto;"><code>\2</code></pre>',
            formatted
        )
        # Inline code `...`
        formatted = re.sub(r"`([^`]+)`", r'<code style="background: #334155; padding: 2px 4px; border-radius: 3px;">\1</code>', formatted)
        # Bold
        formatted = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", formatted)
        # Italic
        formatted = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", formatted)
        # Linebreaks
        formatted = formatted.replace("\n", "<br>")
        return formatted

    def _append_user_message(self, text: str):
        html_content = self._format_markdown_html(text)
        msg_html = f"""
        <div style="margin-bottom: 12px; text-align: right;">
            <div style="display: inline-block; background-color: #2563eb; color: #ffffff; padding: 8px 14px; border-radius: 12px 12px 2px 12px; max-width: 80%; text-align: left; font-size: 13px;">
                <b style="color: #bfdbfe;">Bạn:</b><br>{html_content}
            </div>
        </div>
        """
        self.chat_display.append(msg_html)
        self.chat_display.moveCursor(QTextCursor.End)

    def _append_ai_message(self, model_name: str, text: str):
        html_content = self._format_markdown_html(text)
        msg_html = f"""
        <div style="margin-bottom: 14px; text-align: left;">
            <div style="display: inline-block; background-color: #1e293b; color: #f8fafc; padding: 10px 14px; border-radius: 12px 12px 12px 2px; border: 1px solid #334155; max-width: 90%; font-size: 13px;">
                <b style="color: #38bdf8;">🤖 {model_name}:</b><br><br>{html_content}
            </div>
        </div>
        """
        self.chat_display.append(msg_html)
        self.chat_display.moveCursor(QTextCursor.End)

    def _clear_chat(self):
        self.chat_display.clear()
        self._append_ai_message(
            "SciDoc AI Assistant",
            "Đã làm sạch lịch sử trò chuyện. Bạn có thể bắt đầu phiên hỏi đáp mới!"
        )
