"""Modern Master-Detail Settings Dialog with Settings Cards, Categorized Navigation, and Scrollable Model Explorer."""

from typing import Optional, Dict, List
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QMessageBox, QFrame, QScrollArea, QStackedWidget, QListWidget,
    QListWidgetItem, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QFont

from app.storage.settings import AppSettings, SettingsManager
from app.ai.model_fetcher import fetch_available_models, DEFAULT_URLS, FALLBACK_MODELS
from app.ai.online import OnlineProvider
from app.network.lmstudio_checker import LMStudioChecker
from app.services.mineru_service import MinerUService

PROVIDER_MAP = {
    "Google Gemini": "google",
    "OpenAI": "openai",
    "Anthropic Claude": "anthropic",
    "OpenCode / OpenRouter": "opencode",
    "Custom (OpenAI-compatible)": "custom"
}

PROVIDER_REVERSE_MAP = {v: k for k, v in PROVIDER_MAP.items()}

SUPPORTED_LANGUAGES = [
    ("en", "Tiếng Anh (English)"),
    ("vi", "Tiếng Việt (Vietnamese)"),
    ("fr", "Tiếng Pháp (French - Français)"),
    ("de", "Tiếng Đức (German - Deutsch)"),
    ("zh", "Tiếng Trung (Chinese - 中文)"),
    ("ja", "Tiếng Nhật (Japanese - 日本語)"),
    ("ko", "Tiếng Hàn (Korean - 한국어)"),
    ("es", "Tiếng Tây Ban Nha (Spanish - Español)"),
    ("ru", "Tiếng Nga (Russian - Русский)"),
    ("it", "Tiếng Ý (Italian - Italiano)"),
    ("pt", "Tiếng Bồ Đào Nha (Portuguese - Português)"),
    ("ar", "Tiếng Ả Rập (Arabic - العربية)")
]


class SettingsCard(QFrame):
    """Modern Dark Card container with title, subtitle, and grouped form elements."""

    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self.setStyleSheet("""
            QFrame#settingsCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 14px;
                margin-bottom: 10px;
            }
        """)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(10)

        # Card Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #f8fafc; font-size: 13pt; font-weight: 700;")
        header_layout.addWidget(lbl_title)

        if subtitle:
            lbl_sub = QLabel(subtitle)
            lbl_sub.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
            lbl_sub.setWordWrap(True)
            header_layout.addWidget(lbl_sub)

        self.main_layout.addLayout(header_layout)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet("background-color: #334155; max-height: 1px; margin: 4px 0px 8px 0px;")
        self.main_layout.addWidget(div)

    def add_widget(self, widget: QWidget):
        self.main_layout.addWidget(widget)

    def add_layout(self, layout):
        self.main_layout.addLayout(layout)


class SettingsDialog(QDialog):
    """
    Master-Detail Settings Dialog with Left Navigation Sidebar,
    Right Scrollable Content Cards, and Scrollable Model Explorer.
    """

    def __init__(self, settings_manager: SettingsManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("SciDoc OCR Studio - Settings & Engine Configuration")
        self.resize(880, 680)
        self.setMinimumSize(800, 580)
        self.manager = settings_manager
        self.settings = self.manager.settings

        self.provider_keys: Dict[str, str] = dict(self.settings.provider_keys)
        self.provider_urls: Dict[str, str] = dict(self.settings.provider_urls)
        self.provider_models: Dict[str, str] = dict(self.settings.provider_models)
        self.current_provider: str = self.settings.online_provider or "google"
        self._is_loading: bool = True
        self._all_current_models: List[str] = []

        self._init_ui()
        self._load_values()

    def _init_ui(self):
        self.key_debounce_timer = QTimer(self)
        self.key_debounce_timer.setSingleShot(True)
        self.key_debounce_timer.setInterval(400)
        self.key_debounce_timer.timeout.connect(self._refresh_models)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # -------------------------------------------------------------
        # Master-Detail Split Area
        # -------------------------------------------------------------
        split_layout = QHBoxLayout()
        split_layout.setSpacing(12)

        # 1. Left Navigation Sidebar (Master)
        nav_container = QFrame()
        nav_container.setFixedWidth(230)
        nav_container.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        nav_layout.setSpacing(6)

        nav_header = QLabel("⚙️ Cấu Hình")
        nav_header.setStyleSheet("color: #38bdf8; font-size: 11pt; font-weight: 700; padding: 4px 8px;")
        nav_layout.addWidget(nav_header)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                color: #cbd5e1;
                font-size: 10.5pt;
                font-weight: 500;
                padding: 10px 12px;
                border-radius: 8px;
                margin-bottom: 3px;
            }
            QListWidget::item:hover {
                background-color: #1e293b;
                color: #f8fafc;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
            }
        """)

        nav_items = [
            ("🤖 Online Cloud AI", "OpenAI, Google Gemini, Anthropic, OpenRouter"),
            ("🏠 Local AI & MinerU", "LM Studio, MinerU Server, YOLOv10 ONNX"),
            ("⚡ Chế Độ & Pipeline", "Auto Fallback, Local Only, Online Only"),
            ("🌐 Dịch Thuật & Ngôn Ngữ", "Google Translate, AI LLM Translation"),
            ("📄 OCR & Độ Phân Giải", "DPI Render, Độ tin cậy (Confidence)"),
            ("📐 LaTeX & Trình Biên Dịch", "XeLaTeX, PDFLaTeX, Tectonic, LuaLaTeX")
        ]

        for text, tooltip in nav_items:
            item = QListWidgetItem(text)
            item.setToolTip(tooltip)
            self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        nav_layout.addWidget(self.nav_list)
        split_layout.addWidget(nav_container)

        # 2. Right Content Pane (Detail Stacked Widget)
        self.content_stack = QStackedWidget()

        # Build each Detail Page inside Scroll Area
        self.content_stack.addWidget(self._build_online_ai_page())
        self.content_stack.addWidget(self._build_local_ai_page())
        self.content_stack.addWidget(self._build_pipeline_mode_page())
        self.content_stack.addWidget(self._build_translation_page())
        self.content_stack.addWidget(self._build_ocr_page())
        self.content_stack.addWidget(self._build_latex_page())

        split_layout.addWidget(self.content_stack, stretch=1)
        root_layout.addLayout(split_layout, stretch=1)

        # -------------------------------------------------------------
        # Bottom Dialog Action Bar
        # -------------------------------------------------------------
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 4, 4, 4)

        lbl_hint = QLabel("💡 Cài đặt được tự động đồng bộ tức thì với .env và settings.json")
        lbl_hint.setStyleSheet("color: #64748b; font-size: 9pt;")
        bottom_bar.addWidget(lbl_hint)
        bottom_bar.addStretch()

        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Lưu Cài Đặt")
        self.btn_save.setObjectName("accentBtn")
        self.btn_save.setFixedWidth(120)
        self.btn_save.clicked.connect(self._save_values)
        bottom_bar.addWidget(self.btn_save)

        root_layout.addLayout(bottom_bar)

    def _wrap_in_scroll_area(self, content_widget: QWidget) -> QScrollArea:
        """Wraps any page widget in a smooth dark-themed scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #0f172a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 5px;
                min-height: 25px;
            }
            QScrollBar::handle:vertical:hover {
                background: #475569;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        scroll.setWidget(content_widget)
        return scroll

    # =================================================================
    # PAGE 1: ONLINE CLOUD AI PROVIDERS & MODEL EXPLORER
    # =================================================================
    def _build_online_ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        # Card 1: Provider Selection & API Keys
        card_prov = SettingsCard(
            title="🌐 Nhà Cung Cấp Cloud AI (Online API)",
            subtitle="Kết nối trực tiếp tới Google Gemini, OpenAI, Claude hoặc OpenRouter để bóc tách OCR & dịch thuật."
        )

        prov_row = QHBoxLayout()
        prov_row.addWidget(QLabel("Nhà cung cấp (Provider):"))
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(list(PROVIDER_MAP.keys()))
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        prov_row.addWidget(self.combo_provider, stretch=1)
        card_prov.add_layout(prov_row)

        card_prov.add_widget(QLabel("API Key:"))
        key_box = QHBoxLayout()
        self.txt_online_key = QLineEdit()
        self.txt_online_key.setEchoMode(QLineEdit.Password)
        self.txt_online_key.setPlaceholderText("Nhập API Key (sk-... / AIzaSy...)...")
        self.txt_online_key.textChanged.connect(self._on_key_changed)
        self.txt_online_key.editingFinished.connect(self._refresh_models)
        key_box.addWidget(self.txt_online_key, stretch=1)

        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedWidth(38)
        self.btn_toggle_key.setObjectName("secondaryBtn")
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_box.addWidget(self.btn_toggle_key)
        card_prov.add_layout(key_box)

        card_prov.add_widget(QLabel("Base URL (Điểm cuối API):"))
        self.txt_online_url = QLineEdit()
        self.txt_online_url.textChanged.connect(self._on_url_changed)
        card_prov.add_widget(self.txt_online_url)

        layout.addWidget(card_prov)

        # Card 2: Interactive Model Selector with Search & Scroll List
        card_models = SettingsCard(
            title="🎯 Danh Sách & Chọn Mô Hình AI (Model Explorer)",
            subtitle="Duyệt qua danh sách thanh trượt hoặc tìm kiếm nhanh model tối ưu cho OCR và LaTeX."
        )

        # Model Search & Action bar
        model_tool_row = QHBoxLayout()
        self.txt_model_search = QLineEdit()
        self.txt_model_search.setPlaceholderText("🔍 Tìm kiếm model (vd: flash, gpt-4o, claude, deepseek)...")
        self.txt_model_search.textChanged.connect(self._filter_model_list)
        model_tool_row.addWidget(self.txt_model_search, stretch=1)

        self.btn_refresh_models = QPushButton("🔄 Tải Danh Sách Live")
        self.btn_refresh_models.setObjectName("secondaryBtn")
        self.btn_refresh_models.clicked.connect(self._refresh_models)
        model_tool_row.addWidget(self.btn_refresh_models)
        card_models.add_layout(model_tool_row)

        # Scrollable Model List
        self.list_online_models = QListWidget()
        self.list_online_models.setFixedHeight(170)
        self.list_online_models.setStyleSheet("""
            QListWidget {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                color: #e2e8f0;
                padding: 7px 10px;
                border-radius: 6px;
                font-family: 'Consolas', 'Fira Code', monospace;
                font-size: 10pt;
            }
            QListWidget::item:hover {
                background-color: #1e293b;
                color: #38bdf8;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        self.list_online_models.itemClicked.connect(self._on_model_list_clicked)
        card_models.add_widget(self.list_online_models)

        # Selected Model Name Input Field (supports manual typing)
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Model được chọn:"))
        self.txt_selected_model = QLineEdit()
        self.txt_selected_model.setPlaceholderText("Chọn từ danh sách trên hoặc gõ tên model tùy chỉnh...")
        self.txt_selected_model.textChanged.connect(self._on_selected_model_text_changed)
        sel_row.addWidget(self.txt_selected_model, stretch=1)
        card_models.add_layout(sel_row)

        # Test API Status & Button
        test_row = QHBoxLayout()
        self.lbl_models_status = QLabel("Nhập API Key để tự động tải đầy đủ model.")
        self.lbl_models_status.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        test_row.addWidget(self.lbl_models_status, stretch=1)

        self.btn_test_online = QPushButton("⚡ Kiểm Tra Kết Nối (Test API)")
        self.btn_test_online.setObjectName("secondaryBtn")
        self.btn_test_online.clicked.connect(self._test_online_api)
        test_row.addWidget(self.btn_test_online)
        card_models.add_layout(test_row)

        layout.addWidget(card_models)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # PAGE 2: LOCAL ENGINES (LM STUDIO, MINERU, YOLO ONNX)
    # =================================================================
    def _build_local_ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        # Card 1: LM Studio
        card_lm = SettingsCard(
            title="🏠 LM Studio (Offline LLM / Vision)",
            subtitle="Chạy mô hình AI trực tiếp trên card đồ họa máy tính không cần kết nối mạng."
        )

        lm_row = QHBoxLayout()
        lm_row.addWidget(QLabel("LM Studio URL:"))
        self.txt_lm_url = QLineEdit()
        self.txt_lm_url.setPlaceholderText("http://127.0.0.1:1234/v1")
        lm_row.addWidget(self.txt_lm_url, stretch=1)

        self.btn_test_lm = QPushButton("🔌 Test LM Studio")
        self.btn_test_lm.setObjectName("secondaryBtn")
        self.btn_test_lm.clicked.connect(self._test_lmstudio)
        lm_row.addWidget(self.btn_test_lm)
        card_lm.add_layout(lm_row)

        lm_model_row = QHBoxLayout()
        lm_model_row.addWidget(QLabel("Model Tên:"))
        self.combo_lm_model = QComboBox()
        self.combo_lm_model.setEditable(True)
        self.combo_lm_model.lineEdit().setPlaceholderText("qwen/qwen3.5-9b (hoặc tự động phát hiện)...")
        lm_model_row.addWidget(self.combo_lm_model, stretch=1)
        card_lm.add_layout(lm_model_row)

        self.lbl_lm_status = QLabel("Kết nối LM Studio (cổng 1234) cho dịch thuật và trợ lý AI cục bộ.")
        self.lbl_lm_status.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        card_lm.add_widget(self.lbl_lm_status)
        layout.addWidget(card_lm)

        # Card 2: MinerU Engine
        card_mineru = SettingsCard(
            title="📄 MinerU Pipeline Engine",
            subtitle="Công cụ bóc tách PDF học thuật chuyên sâu (công thức toán, bảng biểu đa cột)."
        )

        m_port_row = QHBoxLayout()
        m_port_row.addWidget(QLabel("MinerU Server URL:"))
        self.txt_mineru_url = QLineEdit("http://127.0.0.1:8000")
        m_port_row.addWidget(self.txt_mineru_url, stretch=1)

        self.btn_test_mineru_port = QPushButton("🔌 Test Port")
        self.btn_test_mineru_port.setObjectName("secondaryBtn")
        self.btn_test_mineru_port.clicked.connect(self._test_mineru_port)
        m_port_row.addWidget(self.btn_test_mineru_port)
        card_mineru.add_layout(m_port_row)

        m_cli_row = QHBoxLayout()
        m_cli_row.addWidget(QLabel("MinerU CLI Path:"))
        self.txt_mineru_cli = QLineEdit("magic-pdf")
        m_cli_row.addWidget(self.txt_mineru_cli, stretch=1)

        self.btn_browse_mineru = QPushButton("📁 Browse...")
        self.btn_browse_mineru.setObjectName("secondaryBtn")
        self.btn_browse_mineru.clicked.connect(self._browse_mineru_cli)
        m_cli_row.addWidget(self.btn_browse_mineru)

        self.btn_auto_mineru = QPushButton("🔍 Auto-Detect")
        self.btn_auto_mineru.setObjectName("secondaryBtn")
        self.btn_auto_mineru.clicked.connect(self._auto_detect_mineru)
        m_cli_row.addWidget(self.btn_auto_mineru)
        card_mineru.add_layout(m_cli_row)

        m_opt_row = QHBoxLayout()
        m_opt_row.addWidget(QLabel("Chế độ trích xuất MinerU:"))
        self.combo_mineru_method = QComboBox()
        self.combo_mineru_method.addItems(["auto", "ocr", "txt"])
        m_opt_row.addWidget(self.combo_mineru_method)
        m_opt_row.addStretch()
        card_mineru.add_layout(m_opt_row)

        self.lbl_mineru_status = QLabel("MinerU bóc tách định dạng tài liệu học thuật với độ chính xác cao.")
        self.lbl_mineru_status.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        card_mineru.add_widget(self.lbl_mineru_status)
        layout.addWidget(card_mineru)

        # Card 3: YOLOv8 Layout Model
        card_yolo = SettingsCard(
            title="⚡ YOLOv8 Layout ONNX (Phân Tích Bố Cục)",
            subtitle="Phát hiện và cắt trực tiếp vùng biểu đồ, sơ đồ và kiến trúc mô hình."
        )

        yolo_box = QHBoxLayout()
        self.lbl_yolo_status = QLabel("⚡ YOLOv8 DocLayout: Đang kiểm tra...")
        self.lbl_yolo_status.setStyleSheet("color: #38bdf8; font-size: 9.5pt; font-weight: 500;")
        yolo_box.addWidget(self.lbl_yolo_status, stretch=1)

        self.btn_download_yolo = QPushButton("📥 Tải Model YOLOv8 (~45MB)")
        self.btn_download_yolo.setObjectName("secondaryBtn")
        self.btn_download_yolo.clicked.connect(self._download_yolo_model)
        yolo_box.addWidget(self.btn_download_yolo)
        card_yolo.add_layout(yolo_box)
        layout.addWidget(card_yolo)

        # Card 4: UniMERNet Formula Model
        card_unimer = SettingsCard(
            title="🧮 UniMERNet Formula OCR (Nhận Diện Công Thức Toán)",
            subtitle="Giải mã công thức toán học chuyên sâu sang mã nguồn LaTeX chuẩn mực."
        )

        unimer_box = QHBoxLayout()
        self.lbl_unimer_status = QLabel("🧮 UniMERNet: Đang kiểm tra...")
        self.lbl_unimer_status.setStyleSheet("color: #14b8a6; font-size: 9.5pt; font-weight: 500;")
        unimer_box.addWidget(self.lbl_unimer_status, stretch=1)

        self.btn_download_unimer = QPushButton("📥 Tải UniMERNet Base (~260MB)")
        self.btn_download_unimer.setObjectName("secondaryBtn")
        self.btn_download_unimer.clicked.connect(self._download_unimer_model)
        unimer_box.addWidget(self.btn_download_unimer)
        card_unimer.add_layout(unimer_box)
        layout.addWidget(card_unimer)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # PAGE 3: PIPELINE MODE & WORKFLOW STRATEGY
    # =================================================================
    def _build_pipeline_mode_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        card_mode = SettingsCard(
            title="⚡ Chế Độ Xử Lý Toàn Cục (Engine Strategy)",
            subtitle="Quy định chiến lược định tuyến giữa Online Vision AI và mô hình Cục bộ Offline."
        )

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Chế độ vận hành (AI Mode):"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Auto (Ưu tiên Online AI, tự động fallback Offline)",
            "Local Only (LM Studio + MinerU Offline)",
            "Local Only (Chỉ dùng MinerU Engine)",
            "Online Only (Chỉ dùng API Cloud)"
        ])
        mode_row.addWidget(self.combo_mode, stretch=1)
        card_mode.add_layout(mode_row)

        desc_lbl = QLabel(
            "• Auto: Gửi yêu cầu lên Gemini / GPT-4o / Claude. Nếu mất mạng hoặc hết quota (429), tự động chuyển sang LM Studio.\n"
            "• Local Only: Chạy hoàn toàn 100% offline bảo mật dữ liệu.\n"
            "• Online Only: Luôn sử dụng mô hình đám mây chất lượng cao nhất."
        )
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 9.5pt; line-height: 1.4;")
        card_mode.add_widget(desc_lbl)

        layout.addWidget(card_mode)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # PAGE 4: TRANSLATION & LANGUAGES
    # =================================================================
    def _build_translation_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        card_trans = SettingsCard(
            title="🌐 Dịch Thuật Học Thuật (Formula-Safe Translation)",
            subtitle="Cấu hình động cơ dịch và các cặp ngôn ngữ dịch thuật, bảo tồn 100% công thức toán học và mã code."
        )

        card_trans.add_widget(QLabel("Động cơ dịch thuật (Translation Engine):"))
        self.combo_trans_engine = QComboBox()
        self.combo_trans_engine.addItem("🚀 Google Translate (Miễn phí, Tốc độ cao, Không tốn Token)", "google_translate")
        self.combo_trans_engine.addItem("🧠 AI LLM Translation (Gemini / OpenAI / Claude / LM Studio)", "ai_llm")
        card_trans.add_widget(self.combo_trans_engine)

        engine_desc = QLabel(
            "• Google Translate: Dịch siêu tốc, miễn phí 100%, không cần API Key, thích hợp cho tài liệu dài.\n"
            "• AI LLM: Dịch chuẩn xác văn phong học thuật chuyên sâu theo mô hình AI bạn chọn ở mục Cloud / Local."
        )
        engine_desc.setStyleSheet("color: #94a3b8; font-size: 9pt; line-height: 1.4; margin-bottom: 6px;")
        card_trans.add_widget(engine_desc)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Ngôn ngữ nguồn (Gốc):"))
        self.combo_src_lang = QComboBox()
        for code, name in SUPPORTED_LANGUAGES:
            self.combo_src_lang.addItem(f"{name} [{code}]", code)
        lang_row.addWidget(self.combo_src_lang, stretch=1)

        lang_row.addWidget(QLabel("Ngôn ngữ đích (Dịch):"))
        self.combo_tgt_lang = QComboBox()
        for code, name in SUPPORTED_LANGUAGES:
            self.combo_tgt_lang.addItem(f"{name} [{code}]", code)
        lang_row.addWidget(self.combo_tgt_lang, stretch=1)
        card_trans.add_layout(lang_row)

        layout.addWidget(card_trans)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # PAGE 5: OCR RESOLUTION & QUALITY
    # =================================================================
    def _build_ocr_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        card_ocr = SettingsCard(
            title="📄 Độ Phân Giải & Đánh Giá Chất Lượng (OCR Settings)",
            subtitle="Cấu hình độ phân giải trích xuất ảnh và ngưỡng tự động đánh dấu kiểm duyệt."
        )

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("Độ phân giải render trang (OCR DPI):"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(72, 600)
        self.spin_dpi.setValue(400)
        self.spin_dpi.setSuffix(" DPI")
        dpi_row.addWidget(self.spin_dpi, stretch=1)
        card_ocr.add_layout(dpi_row)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Ngưỡng tự động Review (Confidence Threshold):"))
        self.spin_conf = QDoubleSpinBox()
        self.spin_conf.setRange(0.50, 0.99)
        self.spin_conf.setSingleStep(0.05)
        self.spin_conf.setValue(0.85)
        conf_row.addWidget(self.spin_conf, stretch=1)
        card_ocr.add_layout(conf_row)

        hint = QLabel("Khuyến nghị: 400 DPI cho bài báo khoa học chứa nhiều chỉ số trên/dưới nhỏ.")
        hint.setStyleSheet("color: #64748b; font-size: 9pt;")
        card_ocr.add_widget(hint)

        layout.addWidget(card_ocr)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # PAGE 6: LATEX COMPILER & EXPORT
    # =================================================================
    def _build_latex_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        card_latex = SettingsCard(
            title="📐 Trình Biên Dịch LaTeX (LaTeX Compiler)",
            subtitle="Chọn công cụ biên dịch tài liệu LaTeX thành PDF học thuật."
        )

        comp_row = QHBoxLayout()
        comp_row.addWidget(QLabel("Trình biên dịch mặc định:"))
        self.combo_compiler = QComboBox()
        self.combo_compiler.addItems(["xelatex", "pdflatex", "lualatex", "tectonic"])
        comp_row.addWidget(self.combo_compiler, stretch=1)
        card_latex.add_layout(comp_row)

        desc_comp = QLabel(
            "• XeLaTeX (Khuyến nghị): Hỗ trợ đầy đủ Unicode tiếng Việt và font chữ đa ngôn ngữ.\n"
            "• PDFLaTeX: Trình biên dịch truyền thống tốc độ cao.\n"
            "• Tectonic: Trình biên dịch standalone tự động tải các gói LaTeX cần thiết."
        )
        desc_comp.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
        card_latex.add_widget(desc_comp)

        layout.addWidget(card_latex)
        layout.addStretch()

        return self._wrap_in_scroll_area(page)

    # =================================================================
    # SLOTS & EVENT HANDLERS
    # =================================================================

    def _on_nav_changed(self, row: int):
        if 0 <= row < self.content_stack.count():
            self.content_stack.setCurrentIndex(row)

    def _load_values(self):
        self._is_loading = True
        s = self.settings

        # 1. Mode
        mode_idx = 0
        if s.ai_mode == "local_only":
            mode_idx = 1
        elif s.ai_mode == "mineru":
            mode_idx = 2
        elif s.ai_mode == "online_only":
            mode_idx = 3
        self.combo_mode.setCurrentIndex(mode_idx)

        # 2. MinerU
        self.txt_mineru_url.setText(getattr(s, "mineru_server_url", "http://127.0.0.1:8000"))
        self.combo_mineru_method.setCurrentText(getattr(s, "mineru_method", "auto"))
        self.txt_mineru_cli.setText(getattr(s, "mineru_cli_path", "magic-pdf"))

        # 3. LM Studio
        self.txt_lm_url.setText(s.lmstudio_url)
        self.combo_lm_model.setEditText(s.lmstudio_model or "qwen/qwen3.5-9b")

        # 4. Active Cloud Provider
        prov = s.online_provider or "google"
        display_name = PROVIDER_REVERSE_MAP.get(prov, "Google Gemini")
        self.combo_provider.setCurrentText(display_name)
        self._switch_to_provider(prov)

        # 5. Translation & OCR
        t_eng = getattr(s, "translation_engine", "google_translate")
        for idx in range(self.combo_trans_engine.count()):
            if self.combo_trans_engine.itemData(idx) == t_eng:
                self.combo_trans_engine.setCurrentIndex(idx)
                break

        for idx in range(self.combo_src_lang.count()):
            if self.combo_src_lang.itemData(idx) == s.source_language:
                self.combo_src_lang.setCurrentIndex(idx)
                break

        for idx in range(self.combo_tgt_lang.count()):
            if self.combo_tgt_lang.itemData(idx) == s.target_language:
                self.combo_tgt_lang.setCurrentIndex(idx)
                break

        self.spin_dpi.setValue(s.ocr_dpi or 400)
        self.spin_conf.setValue(s.confidence_threshold)
        self.combo_compiler.setCurrentText(s.latex_compiler)

        # Select first nav tab by default
        self.nav_list.setCurrentRow(0)

        self._is_loading = False
        self._refresh_yolo_status()
        self._refresh_unimer_status()

    def _switch_to_provider(self, prov: str):
        self.current_provider = prov

        key = self.provider_keys.get(prov, "")
        url = self.provider_urls.get(prov, "") or DEFAULT_URLS.get(prov, "https://api.openai.com/v1")
        saved_model = self.provider_models.get(prov, "")

        self.txt_online_key.setText(key)
        self.txt_online_url.setText(url)

        # Populate the scrollable model explorer
        self._populate_models(prov, key, url, saved_model)

    def _populate_models(self, prov: str, key: str, url: str, target_model: str = ""):
        models = fetch_available_models(prov, key, url)
        self._all_current_models = list(models)
        self.txt_model_search.clear()
        self._render_model_list(models, target_model)

        if target_model:
            self.txt_selected_model.setText(target_model)
        elif models:
            self.txt_selected_model.setText(models[0])

        if key:
            self.lbl_models_status.setText(f"✓ Đã nạp {len(models)} model khả dụng cho {prov.capitalize()}.")
        else:
            self.lbl_models_status.setText(f"Hiển thị danh sách model có sẵn. Nhập API Key để nạp live.")

    def _render_model_list(self, models: List[str], selected_model: str = ""):
        self.list_online_models.clear()
        selected_row = -1

        for idx, m in enumerate(models):
            item = QListWidgetItem(m)
            # Add recommended tag for top models
            if any(rec in m.lower() for rec in ("gemini-3.5-flash", "gpt-4o-mini", "claude-3-7", "deepseek-chat")):
                item.setText(f"⭐ {m}  [Khuyên dùng]")
                item.setData(Qt.UserRole, m)
            else:
                item.setText(f"   {m}")
                item.setData(Qt.UserRole, m)

            self.list_online_models.addItem(item)
            if selected_model and (m == selected_model or m in selected_model):
                selected_row = idx

        if selected_row >= 0:
            self.list_online_models.setCurrentRow(selected_row)
        elif models:
            self.list_online_models.setCurrentRow(0)

    def _filter_model_list(self, query: str):
        q = query.strip().lower()
        if not q:
            filtered = self._all_current_models
        else:
            filtered = [m for m in self._all_current_models if q in m.lower()]
        current_sel = self.txt_selected_model.text().strip()
        self._render_model_list(filtered, current_sel)

    def _on_model_list_clicked(self, item: QListWidgetItem):
        real_model = item.data(Qt.UserRole) or item.text().replace("⭐ ", "").replace("   ", "").split(" ")[0].strip()
        self.txt_selected_model.setText(real_model)
        self.provider_models[self.current_provider] = real_model

    def _on_selected_model_text_changed(self, text: str):
        if not getattr(self, "_is_loading", False):
            self.provider_models[self.current_provider] = text.strip()

    def _refresh_models(self):
        prov = self.current_provider
        key = self.txt_online_key.text().strip()
        url = self.txt_online_url.text().strip()
        current_model = self.txt_selected_model.text().strip()

        self.lbl_models_status.setText("⏳ Đang kết nối máy chủ nạp danh sách model...")
        self._populate_models(prov, key, url, current_model)

    def _on_provider_changed(self, idx: int):
        if getattr(self, "_is_loading", False):
            return
        self._save_current_provider_state()
        display_name = self.combo_provider.currentText()
        new_prov = PROVIDER_MAP.get(display_name, "google")
        self._switch_to_provider(new_prov)

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

    def _toggle_key_visibility(self):
        if self.txt_online_key.echoMode() == QLineEdit.Password:
            self.txt_online_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.txt_online_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("👁")

    def _test_online_api(self):
        prov = self.current_provider
        key = self.txt_online_key.text().strip()
        url = self.txt_online_url.text().strip()
        model = self.txt_selected_model.text().strip()

        if not key:
            QMessageBox.warning(self, "Online API Test", f"Vui lòng nhập API Key cho {prov.capitalize()}.")
            return

        provider_obj = OnlineProvider(
            provider=prov,
            api_key=key,
            base_url=url,
            model_name=model,
            timeout=12.0
        )

        try:
            res = provider_obj.complete("Say 'SciDoc OK' in 2 words.", max_tokens=10)
            QMessageBox.information(
                self,
                "Kết Nối Thành Công",
                f"✓ Kết nối thành công tới {prov.capitalize()}!\nModel: {provider_obj.model_name}\nPhản hồi: {res}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Lỗi Kết Nối", f"✗ Kết nối thất bại:\n{e}")

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

            models_str = ", ".join(models) if models else "Sẵn sàng (auto-detect)"
            QMessageBox.information(self, "LM Studio Test", f"✓ Kết nối thành công tới LM Studio!\nDanh sách Model: {models_str}")
        else:
            self.lbl_lm_status.setText(f"✗ Không thể kết nối: {err}")
            QMessageBox.warning(self, "LM Studio Test", f"✗ Kết nối thất bại: {err}")

    def _test_mineru_port(self):
        url = self.txt_mineru_url.text().strip() or "http://127.0.0.1:8000"
        svc = MinerUService(server_url=url)
        ok, msg = svc.check_server_port()
        if ok:
            self.lbl_mineru_status.setText(f"✓ MinerU Server đang chạy tại: {url}")
            QMessageBox.information(self, "MinerU Server Test", f"✓ Kết nối thành công!\n{msg}")
        else:
            self.lbl_mineru_status.setText(f"✗ Không tìm thấy server MinerU tại: {url}")
            QMessageBox.warning(self, "MinerU Server Test", f"✗ Không thể kết nối cổng MinerU:\n{msg}\n\n(Bạn có thể dùng chế độ CLI bên dưới thay thế).")

    def _browse_mineru_cli(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file magic-pdf.exe hoặc mineru.exe",
            filter="Executables (*.exe *.bat *.cmd);;All Files (*)"
        )
        if file_path:
            self.txt_mineru_cli.setText(file_path)
            self._test_mineru()

    def _auto_detect_mineru(self):
        svc = MinerUService()
        exe = svc.get_executable()
        self.txt_mineru_cli.setText(exe)
        self._test_mineru()

    def _test_mineru(self):
        cli = self.txt_mineru_cli.text().strip() or "magic-pdf"
        svc = MinerUService(cli_path=cli)
        if svc.is_available():
            exe_path = svc.get_executable()
            self.lbl_mineru_status.setText(f"✓ MinerU CLI detected: {exe_path}")
            QMessageBox.information(self, "MinerU Test", f"✓ Tìm thấy MinerU CLI sẵn sàng!\nĐường dẫn: {exe_path}")
        else:
            self.lbl_mineru_status.setText("✗ magic-pdf command not found. Cài đặt mineru: `uv pip install mineru[all]`.")
            QMessageBox.warning(self, "MinerU Test", "✗ Không tìm thấy file thực thi magic-pdf trên PATH hoặc mineru_env.")

    def _refresh_yolo_status(self):
        from app.utils.downloader import is_model_installed
        if is_model_installed("yolov8_doclayout"):
            self.lbl_yolo_status.setText("🟢 Model YOLOv8 DocLayout ONNX: Đã sẵn sàng trên CPU.")
            self.lbl_yolo_status.setStyleSheet("color: #4ade80; font-size: 9.5pt; font-weight: 500;")
            self.btn_download_yolo.setText("🔄 Tải Lại YOLOv8")
        else:
            self.lbl_yolo_status.setText("⚪ Chưa tải model (Đang dùng bộ phân tích hình học CV Heuristics).")
            self.lbl_yolo_status.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
            self.btn_download_yolo.setText("📥 Tải Model YOLOv8 (~45MB)")

    def _download_yolo_model(self):
        import threading
        from app.utils.downloader import download_model_streaming

        self.btn_download_yolo.setEnabled(False)
        self.lbl_yolo_status.setText("⏳ Đang tải Model YOLOv8...")
        self.lbl_yolo_status.setStyleSheet("color: #38bdf8; font-size: 9.5pt;")

        def _bg_download():
            def _prog(downloaded, total, speed, status_str):
                self.lbl_yolo_status.setText(status_str)

            ok, res_msg = download_model_streaming(
                model_key="yolov8_doclayout",
                progress_callback=_prog
            )

            self.btn_download_yolo.setEnabled(True)
            if ok:
                self._refresh_yolo_status()
                QMessageBox.information(self, "Tải Model Thành Công", "✓ Đã tải xong Model YOLOv8 DocLayout ONNX vào thư mục assets/models!\nModel đã sẵn sàng hoạt động trên CPU.")
            else:
                self._refresh_yolo_status()
                QMessageBox.warning(self, "Lỗi Tải Model", f"✗ Không thể tải model:\n{res_msg}")

        thread = threading.Thread(target=_bg_download, daemon=True)
        thread.start()

    def _refresh_unimer_status(self):
        from app.utils.downloader import is_model_installed
        if is_model_installed("unimernet"):
            self.lbl_unimer_status.setText("🟢 Model UniMERNet Math OCR: Đã sẵn sàng.")
            self.lbl_unimer_status.setStyleSheet("color: #4ade80; font-size: 9.5pt; font-weight: 500;")
            self.btn_download_unimer.setText("🔄 Tải Lại UniMERNet")
        else:
            self.lbl_unimer_status.setText("⚪ Chưa tải UniMERNet (Có thể tải để nhận diện công thức toán).")
            self.lbl_unimer_status.setStyleSheet("color: #94a3b8; font-size: 9.5pt;")
            self.btn_download_unimer.setText("📥 Tải Model UniMERNet (~115MB)")

    def _download_unimer_model(self):
        import threading
        from app.utils.downloader import download_model_streaming

        self.btn_download_unimer.setEnabled(False)
        self.lbl_unimer_status.setText("⏳ Đang tải Model UniMERNet...")
        self.lbl_unimer_status.setStyleSheet("color: #14b8a6; font-size: 9.5pt;")

        def _bg_download():
            def _prog(downloaded, total, speed, status_str):
                self.lbl_unimer_status.setText(status_str)

            ok, res_msg = download_model_streaming(
                model_key="unimernet",
                progress_callback=_prog
            )

            self.btn_download_unimer.setEnabled(True)
            if ok:
                self._refresh_unimer_status()
                QMessageBox.information(self, "Tải Model Thành Công", "✓ Đã tải xong Model UniMERNet Formula OCR!\nModel đã sẵn sàng hoạt động.")
            else:
                self._refresh_unimer_status()
                QMessageBox.warning(self, "Lỗi Tải Model", f"✗ Không thể tải UniMERNet:\n{res_msg}")

        thread = threading.Thread(target=_bg_download, daemon=True)
        thread.start()

    def _save_current_provider_state(self):
        self.provider_keys[self.current_provider] = self.txt_online_key.text().strip()
        self.provider_urls[self.current_provider] = self.txt_online_url.text().strip()
        self.provider_models[self.current_provider] = self.txt_selected_model.text().strip()

    def _save_values(self):
        self._save_current_provider_state()

        modes = ["auto", "local_only", "mineru", "online_only"]
        self.settings.ai_mode = modes[self.combo_mode.currentIndex()]

        # MinerU
        self.settings.mineru_server_url = self.txt_mineru_url.text().strip() or "http://127.0.0.1:8000"
        self.settings.mineru_method = self.combo_mineru_method.currentText()
        self.settings.mineru_cli_path = self.txt_mineru_cli.text().strip() or "magic-pdf"

        # LM Studio
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

        # Translation & OCR & LaTeX
        self.settings.translation_engine = self.combo_trans_engine.currentData() or "google_translate"
        self.settings.source_language = self.combo_src_lang.currentData() or "en"
        self.settings.target_language = self.combo_tgt_lang.currentData() or "vi"
        self.settings.ocr_dpi = self.spin_dpi.value()
        self.settings.confidence_threshold = self.spin_conf.value()
        self.settings.latex_compiler = self.combo_compiler.currentText()

        self.manager.save_settings(self.settings)
        self.accept()
