"""Settings Dialog for configuring AI providers (OpenAI, Google, Anthropic, OpenCode, LM Studio, MinerU), OCR, and LaTeX engines."""

from typing import Optional, Dict, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QLineEdit, QComboBox, QDoubleSpinBox,
    QSpinBox, QPushButton, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QTimer
from app.storage.settings import AppSettings, SettingsManager
from app.ai.model_fetcher import fetch_available_models, DEFAULT_URLS, FALLBACK_MODELS
from app.ai.online import OnlineProvider
from app.network.lmstudio_checker import LMStudioChecker
from app.services.mineru_service import MinerUService

PROVIDER_MAP = {
    "OpenAI": "openai",
    "Google Gemini": "google",
    "Anthropic Claude": "anthropic",
    "OpenCode / OpenRouter": "opencode",
    "Custom (OpenAI-compatible)": "custom"
}

PROVIDER_REVERSE_MAP = {v: k for k, v in PROVIDER_MAP.items()}

class SettingsDialog(QDialog):
    """Configuration dialog for AI endpoints, models, OCR, and LaTeX compilers."""

    def __init__(self, settings_manager: SettingsManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("SciDoc OCR - Settings")
        self.resize(650, 620)
        self.manager = settings_manager
        self.settings = self.manager.settings

        self.provider_keys: Dict[str, str] = dict(self.settings.provider_keys)
        self.provider_urls: Dict[str, str] = dict(self.settings.provider_urls)
        self.provider_models: Dict[str, str] = dict(self.settings.provider_models)
        self.current_provider: str = self.settings.online_provider or "openai"
        self._is_loading: bool = True

        self._init_ui()
        self._load_values()

    def _init_ui(self):
        self.key_debounce_timer = QTimer(self)
        self.key_debounce_timer.setSingleShot(True)
        self.key_debounce_timer.setInterval(400)
        self.key_debounce_timer.timeout.connect(self._refresh_models)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tabs = QTabWidget()

        # =============================================================
        # 1. AI Settings Tab
        # =============================================================
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.setSpacing(10)

        # Mode Selector
        mode_box = QHBoxLayout()
        mode_box.addWidget(QLabel("AI Engine Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Auto (Online with Offline Fallback)",
            "Local Only (LM Studio)",
            "Local Only (MinerU Engine)",
            "Online Only (API)"
        ])
        mode_box.addWidget(self.combo_mode)
        ai_layout.addLayout(mode_box)

        # MinerU Group
        mineru_group = QGroupBox("MinerU (Local CLI Engine - magic-pdf)")
        mineru_layout = QVBoxLayout(mineru_group)
        mineru_layout.setSpacing(6)

        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Method:"))
        self.combo_mineru_method = QComboBox()
        self.combo_mineru_method.addItems(["auto", "ocr", "txt"])
        m_row.addWidget(self.combo_mineru_method)

        m_row.addWidget(QLabel("CLI Executable:"))
        self.txt_mineru_cli = QLineEdit("magic-pdf")
        m_row.addWidget(self.txt_mineru_cli, stretch=1)

        self.btn_test_mineru = QPushButton("🔍 Check MinerU")
        self.btn_test_mineru.setObjectName("secondaryBtn")
        self.btn_test_mineru.clicked.connect(self._test_mineru)
        m_row.addWidget(self.btn_test_mineru)
        mineru_layout.addLayout(m_row)

        self.lbl_mineru_status = QLabel("MinerU runs in isolated subprocess to extract high-accuracy formulas and layout.")
        self.lbl_mineru_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        mineru_layout.addWidget(self.lbl_mineru_status)
        ai_layout.addWidget(mineru_group)

        # LM Studio Group
        lm_group = QGroupBox("LM Studio (Offline Engine)")
        lm_layout = QVBoxLayout(lm_group)
        lm_layout.setSpacing(6)

        lm_layout.addWidget(QLabel("Base URL:"))
        self.txt_lm_url = QLineEdit()
        lm_layout.addWidget(self.txt_lm_url)

        # Local Model Selector
        lm_layout.addWidget(QLabel("Model Name:"))
        lm_model_box = QHBoxLayout()
        self.combo_lm_model = QComboBox()
        self.combo_lm_model.setEditable(True)
        self.combo_lm_model.lineEdit().setPlaceholderText("local-model (or auto-detect)...")
        lm_model_box.addWidget(self.combo_lm_model, stretch=1)

        self.btn_test_lm = QPushButton("🔌 Test & Load Local Models")
        self.btn_test_lm.setObjectName("secondaryBtn")
        self.btn_test_lm.clicked.connect(self._test_lmstudio)
        lm_model_box.addWidget(self.btn_test_lm)
        lm_layout.addLayout(lm_model_box)

        self.lbl_lm_status = QLabel("Connect to LM Studio to auto-detect loaded models.")
        self.lbl_lm_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lm_layout.addWidget(self.lbl_lm_status)

        ai_layout.addWidget(lm_group)

        # Online API Group
        online_group = QGroupBox("Online API Engine (Multi-Provider)")
        online_layout = QVBoxLayout(online_group)
        online_layout.setSpacing(6)

        # Provider Selector
        prov_box = QHBoxLayout()
        prov_box.addWidget(QLabel("Provider:"))
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(list(PROVIDER_MAP.keys()))
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        prov_box.addWidget(self.combo_provider)
        online_layout.addLayout(prov_box)

        # API Key
        online_layout.addWidget(QLabel("API Key:"))
        key_box = QHBoxLayout()
        self.txt_online_key = QLineEdit()
        self.txt_online_key.setEchoMode(QLineEdit.Password)
        self.txt_online_key.setPlaceholderText("Enter API Key (sk-... / AIza...)...")
        self.txt_online_key.textChanged.connect(self._on_key_changed)
        self.txt_online_key.editingFinished.connect(self._refresh_models)
        key_box.addWidget(self.txt_online_key)

        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.setObjectName("secondaryBtn")
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_box.addWidget(self.btn_toggle_key)
        online_layout.addLayout(key_box)

        # Base URL
        online_layout.addWidget(QLabel("Base URL:"))
        self.txt_online_url = QLineEdit()
        self.txt_online_url.textChanged.connect(self._on_url_changed)
        online_layout.addWidget(self.txt_online_url)

        # Model Selector (Editable ComboBox with Refresh button)
        online_layout.addWidget(QLabel("Model:"))
        model_box = QHBoxLayout()
        self.combo_online_model = QComboBox()
        self.combo_online_model.setEditable(True)
        self.combo_online_model.lineEdit().setPlaceholderText("Select or type model name...")
        model_box.addWidget(self.combo_online_model, stretch=1)

        self.btn_refresh_models = QPushButton("🔄 Refresh Models")
        self.btn_refresh_models.setObjectName("secondaryBtn")
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        model_box.addWidget(self.btn_refresh_models)
        online_layout.addLayout(model_box)

        # Status & Test buttons
        status_box = QHBoxLayout()
        self.lbl_models_status = QLabel("Enter API Key to auto-load available models.")
        self.lbl_models_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        status_box.addWidget(self.lbl_models_status)
        status_box.addStretch()

        self.btn_test_online = QPushButton("⚡ Test Online API")
        self.btn_test_online.setObjectName("secondaryBtn")
        self.btn_test_online.clicked.connect(self._test_online_api)
        status_box.addWidget(self.btn_test_online)
        online_layout.addLayout(status_box)

        ai_layout.addWidget(online_group)
        tabs.addTab(ai_tab, "🤖 AI Engine")

        # =============================================================
        # 2. Document & OCR Tab
        # =============================================================
        ocr_tab = QWidget()
        ocr_layout = QVBoxLayout(ocr_tab)

        ocr_layout.addWidget(QLabel("Translation Engine:"))
        self.combo_trans_engine = QComboBox()
        self.combo_trans_engine.addItems([
            "Google Translate (Free & Fast - No API Key)",
            "AI LLM Translation (Gemini / OpenAI / Claude / LM Studio)"
        ])
        ocr_layout.addWidget(self.combo_trans_engine)

        ocr_layout.addWidget(QLabel("Source Language:"))
        self.combo_src_lang = QComboBox()
        self.combo_src_lang.addItems(["en", "vi", "fr", "de", "zh", "ja", "es", "ru"])
        ocr_layout.addWidget(self.combo_src_lang)

        ocr_layout.addWidget(QLabel("Target Translation Language:"))
        self.combo_tgt_lang = QComboBox()
        self.combo_tgt_lang.addItems(["vi", "en", "fr", "de", "zh", "ja", "es", "ru"])
        ocr_layout.addWidget(self.combo_tgt_lang)

        ocr_layout.addWidget(QLabel("OCR Resolution (DPI):"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 600)
        self.spin_dpi.setValue(400)
        ocr_layout.addWidget(self.spin_dpi)

        ocr_layout.addWidget(QLabel("Review Confidence Threshold:"))
        self.spin_conf = QDoubleSpinBox()
        self.spin_conf.setRange(0.50, 0.99)
        self.spin_conf.setSingleStep(0.05)
        self.spin_conf.setValue(0.85)
        ocr_layout.addWidget(self.spin_conf)

        ocr_layout.addStretch()
        tabs.addTab(ocr_tab, "📄 OCR & Translation")

        # =============================================================
        # 3. LaTeX Tab
        # =============================================================
        latex_tab = QWidget()
        latex_layout = QVBoxLayout(latex_tab)

        latex_layout.addWidget(QLabel("Preferred LaTeX Compiler:"))
        self.combo_compiler = QComboBox()
        self.combo_compiler.addItems(["xelatex", "pdflatex", "lualatex", "tectonic"])
        latex_layout.addWidget(self.combo_compiler)

        latex_layout.addStretch()
        tabs.addTab(latex_tab, "📐 LaTeX")

        layout.addWidget(tabs)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("accentBtn")
        self.btn_save.clicked.connect(self._save_values)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_save)
        layout.addLayout(btn_box)

    def _load_values(self):
        self._is_loading = True
        s = self.settings

        # Mode
        mode_idx = 0
        if s.ai_mode == "local_only":
            mode_idx = 1
        elif s.ai_mode == "mineru":
            mode_idx = 2
        elif s.ai_mode == "online_only":
            mode_idx = 3
        self.combo_mode.setCurrentIndex(mode_idx)

        # MinerU
        self.combo_mineru_method.setCurrentText(getattr(s, "mineru_method", "auto"))
        self.txt_mineru_cli.setText(getattr(s, "mineru_cli_path", "magic-pdf"))

        self.txt_lm_url.setText(s.lmstudio_url)
        self.combo_lm_model.setEditText(s.lmstudio_model or "qwen/qwen3.5-9b")

        # Active Provider
        prov = s.online_provider or "openai"
        display_name = PROVIDER_REVERSE_MAP.get(prov, "OpenAI")
        self.combo_provider.setCurrentText(display_name)
        self._switch_to_provider(prov)

        t_eng = getattr(s, "translation_engine", "google_translate")
        self.combo_trans_engine.setCurrentIndex(0 if t_eng == "google_translate" else 1)

        self.combo_src_lang.setCurrentText(s.source_language)
        self.combo_tgt_lang.setCurrentText(s.target_language)
        self.spin_dpi.setValue(s.ocr_dpi or 400)
        self.spin_conf.setValue(s.confidence_threshold)
        self.combo_compiler.setCurrentText(s.latex_compiler)
        self._is_loading = False

    def _test_mineru(self):
        cli = self.txt_mineru_cli.text().strip() or "magic-pdf"
        svc = MinerUService(cli_path=cli)
        if svc.is_available():
            exe_path = svc.get_executable()
            self.lbl_mineru_status.setText(f"✓ MinerU CLI detected: {exe_path}")
            QMessageBox.information(self, "MinerU Test", f"✓ MinerU CLI found and ready!\nPath: {exe_path}")
        else:
            self.lbl_mineru_status.setText("✗ magic-pdf command not found. Please install mineru (`uv pip install mineru[all]`).")
            QMessageBox.warning(self, "MinerU Test", "✗ magic-pdf executable not found on PATH or mineru_env.")

    def _toggle_key_visibility(self):
        if self.txt_online_key.echoMode() == QLineEdit.Password:
            self.txt_online_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.txt_online_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("👁")

    def _on_key_changed(self, text: str):
        if getattr(self, "_is_loading", False):
            return
        self.provider_keys[self.current_provider] = text.strip()
        if len(text.strip()) > 10:
            self.key_debounce_timer.start()

    def _on_url_changed(self, text: str):
        if getattr(self, "_is_loading", False):
            return
        self.provider_urls[self.current_provider] = text.strip()

    def _on_provider_changed(self, idx: int):
        if getattr(self, "_is_loading", False):
            return
        self._save_current_provider_state()
        display_name = self.combo_provider.currentText()
        new_prov = PROVIDER_MAP.get(display_name, "openai")
        self._switch_to_provider(new_prov)

    def _save_current_provider_state(self):
        self.provider_keys[self.current_provider] = self.txt_online_key.text().strip()
        self.provider_urls[self.current_provider] = self.txt_online_url.text().strip()
        self.provider_models[self.current_provider] = self.combo_online_model.currentText().strip()

    def _switch_to_provider(self, prov: str):
        self.current_provider = prov

        key = self.provider_keys.get(prov, "")
        url = self.provider_urls.get(prov, "") or DEFAULT_URLS.get(prov, "https://api.openai.com/v1")
        saved_model = self.provider_models.get(prov, "")

        self.txt_online_key.setText(key)
        self.txt_online_url.setText(url)

        # Refresh models for this provider
        self._populate_models(prov, key, url, saved_model)

    def _populate_models(self, prov: str, key: str, url: str, target_model: str = ""):
        models = fetch_available_models(prov, key, url)
        self.combo_online_model.clear()
        self.combo_online_model.addItems(models)

        if target_model and target_model in models:
            self.combo_online_model.setCurrentText(target_model)
        elif target_model:
            self.combo_online_model.setEditText(target_model)
        elif models:
            self.combo_online_model.setCurrentIndex(0)

        if key:
            self.lbl_models_status.setText(f"✓ Sẵn sàng {len(models)} model khả dụng cho {prov.capitalize()}.")
        else:
            self.lbl_models_status.setText(f"Hiển thị danh sách model có sẵn. Nhập API key để đồng bộ live.")

    def _refresh_models(self):
        prov = self.current_provider
        key = self.txt_online_key.text().strip()
        url = self.txt_online_url.text().strip()
        current_model = self.combo_online_model.currentText().strip()

        self.lbl_models_status.setText("Fetching available models...")
        self._populate_models(prov, key, url, current_model)

    def _test_lmstudio(self):
        url = self.txt_lm_url.text().strip()
        checker = LMStudioChecker(url)
        ok, models, err = checker.check_availability()
        if ok:
            if models:
                self.combo_lm_model.clear()
                self.combo_lm_model.addItems(models)
                self.combo_lm_model.setCurrentIndex(0)
                self.lbl_lm_status.setText(f"✓ Tìm thấy {len(models)} model cục bộ trong LM Studio.")
            else:
                self.lbl_lm_status.setText("✓ Đã kết nối LM Studio (chế độ auto-detect).")

            models_str = ", ".join(models) if models else "Ready (auto-detect)"
            QMessageBox.information(self, "LM Studio Test", f"✓ Successfully connected to LM Studio!\nModels: {models_str}")
        else:
            self.lbl_lm_status.setText(f"✗ Không thể kết nối: {err}")
            QMessageBox.warning(self, "LM Studio Test", f"✗ Connection failed: {err}")

    def _test_online_api(self):
        prov = self.current_provider
        key = self.txt_online_key.text().strip()
        url = self.txt_online_url.text().strip()
        model = self.combo_online_model.currentText().strip()

        if not key:
            QMessageBox.warning(self, "Online API Test", f"Please enter an API key for {prov.capitalize()}.")
            return

        provider_obj = OnlineProvider(
            provider=prov,
            api_key=key,
            base_url=url,
            model_name=model,
            timeout=10.0
        )

        try:
            res = provider_obj.complete("Say 'SciDoc OK' in 2 words.", max_tokens=10)
            QMessageBox.information(
                self,
                "Online API Test",
                f"✓ Successfully connected to {prov.capitalize()}!\nModel: {provider_obj.model_name}\nResponse: {res}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Online API Test", f"✗ Connection failed:\n{e}")

    def _save_values(self):
        self._save_current_provider_state()

        modes = ["auto", "local_only", "mineru", "online_only"]
        self.settings.ai_mode = modes[self.combo_mode.currentIndex()]

        # MinerU
        self.settings.mineru_method = self.combo_mineru_method.currentText()
        self.settings.mineru_cli_path = self.txt_mineru_cli.text().strip() or "magic-pdf"

        self.settings.lmstudio_url = self.txt_lm_url.text().strip()
        self.settings.lmstudio_model = self.combo_lm_model.currentText().strip() or "qwen/qwen3.5-9b"

        # Active provider settings
        self.settings.online_provider = self.current_provider
        self.settings.online_api_key = self.provider_keys.get(self.current_provider, "")
        self.settings.online_api_url = self.provider_urls.get(self.current_provider, "")
        self.settings.online_model = self.provider_models.get(self.current_provider, "")

        # Save all provider mappings
        self.settings.provider_keys = self.provider_keys
        self.settings.provider_urls = self.provider_urls
        self.settings.provider_models = self.provider_models

        self.settings.translation_engine = "google_translate" if self.combo_trans_engine.currentIndex() == 0 else "ai_llm"
        self.settings.source_language = self.combo_src_lang.currentText()
        self.settings.target_language = self.combo_tgt_lang.currentText()
        self.settings.ocr_dpi = self.spin_dpi.value()
        self.settings.confidence_threshold = self.spin_conf.value()
        self.settings.latex_compiler = self.combo_compiler.currentText()

        self.manager.save_settings(self.settings)
        self.accept()
