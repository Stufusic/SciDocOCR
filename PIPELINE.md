# 🔬 SciDoc OCR — Kiến trúc & Pipeline Xử lý Chi tiết

---

## Tổng quan hệ thống

```mermaid
flowchart LR
    PDF["📄 PDF Khoa học"] --> OCR["🔬 OCR Engine"]
    OCR --> AST["🌳 Document AST"]
    AST --> AI["🤖 AI Audit"]
    AI --> TRANS["🌐 Dịch thuật"]
    TRANS --> PUB["📐 Xuất bản"]
    PUB --> OUT1["📝 Markdown"]
    PUB --> OUT2["📑 LaTeX / PDF"]
```

---

## 1 · Nạp & Chia Chunk PDF

```mermaid
flowchart TD
    A(["📄 Input PDF"]) --> B{"SHA-256\nCache Check"}

    B -- "✅ Đã có cache" --> C(["⚡ Tải từ cache\n(~0.1s)"])
    B -- "❌ Chưa có" --> D["✂️ PDFSplitter\n4 trang / chunk"]

    D --> E1["chunk_1\nTrang 1–4"]
    D --> E2["chunk_2\nTrang 5–8"]
    D --> E3["chunk_3\nTrang 9–12"]
    D --> E4["chunk_n\nTrang ..."]

    style A fill:#1e3a5f,stroke:#38bdf8,color:#f0f9ff
    style B fill:#374151,stroke:#6b7280,color:#f9fafb
    style C fill:#14532d,stroke:#4ade80,color:#f0fdf4
    style D fill:#1e293b,stroke:#94a3b8,color:#f1f5f9
```

> **Tại sao chia 4 trang/chunk?**
> Giới hạn VRAM GPU — mô hình nhận diện công thức cần nhiều bộ nhớ. Chia chunk giúp tránh tràn RAM, cho phép phục hồi nếu một chunk gặp sự cố, và hiển thị tiến độ `25% → 50% → 75% → 100%` chính xác.

---

## 2 · OCR Layout & Công thức Toán học

```mermaid
flowchart LR
    subgraph MinerU["🔬 MinerU CLI (GPU-accelerated)"]
        direction TB
        M1["YOLOv8\nPhát hiện Layout"] --> M2["Phân vùng đa cột\n(2-column, header, footer)"]
        M2 --> M3["UniMERNet\nCông thức → LaTeX"]
        M2 --> M4["Trích xuất Bảng biểu\n→ Markdown Table"]
        M2 --> M5["Trích xuất Hình ảnh\n→ images/crop_*.png"]
    end

    subgraph LocalOCR["📄 Local Engine (Fallback)"]
        direction TB
        L1["PyMuPDF fitz\nText & BBox"] --> L2["Heuristic Analyzer\nClassify Block Type"]
    end

    Chunk["📋 Chunk PDF"] --> MinerU & LocalOCR
    MinerU --> Out["📝 chunk_N.md\n+ images/"]
    LocalOCR --> Out
```

---

## 3 · Cấu trúc Cây AST

```mermaid
graph TB
    DOC["📘 Document\n────────\nid · metadata\npages: List&lsqb;Page&rsqb;"]

    PAGE["📄 Page\n────────\npage_number\nwidth · height\npreview_image"]

    HEAD["📌 HeadingBlock\n────────\nlevel: 1–6\ntext: str"]
    PARA["📝 ParagraphBlock\n────────\ntext: str\ninline_math: List"]
    FORM["➕ FormulaBlock\n────────\nlatex: str\nis_display: bool\nis_valid: bool\nsyntax_errors"]
    TABLE["📊 TableBlock\n────────\nrows · cols\ncells · caption"]
    FIG["🖼️ FigureBlock\n────────\nimage_path\ncaption: str"]

    DOC -->|"1 → nhiều"| PAGE
    PAGE -->|blocks| HEAD & PARA & FORM & TABLE & FIG

    style DOC fill:#1e3a5f,stroke:#38bdf8,color:#f0f9ff
    style PAGE fill:#1e293b,stroke:#64748b,color:#f1f5f9
    style FORM fill:#3b0764,stroke:#a855f7,color:#faf5ff
```

---

## 4 · Bộ Điều phối AI (AIRouter)

```mermaid
flowchart TD
    Block["🔤 Đoạn Văn / Công thức"] --> Router{"🤖 AIRouter\n─────────\nauto · local · online"}

    Router --> LM["💻 LM Studio\n127.0.0.1:1234\nOffline · GPU Local"]
    Router --> GEM["✨ Google Gemini\ngemini-2.5-flash\ngemma-4-31b-it"]
    Router --> GPT["🔵 OpenAI\ngpt-4o · gpt-4o-mini"]
    Router --> CLD["🟠 Claude\nclaude-3-7-sonnet"]
    Router --> OR["🟣 OpenRouter\nDeepSeek-R1"]

    LM & GEM & GPT & CLD & OR --> Clean["🧹 strip_thought_content\nLọc &lt;think&gt; · &lt;thought&gt;\nThinking Process..."]
    Clean --> Annot["📐 LaTeX Annotator\nSửa lỗi · Thêm chú thích 💡"]

    style Router fill:#374151,stroke:#6b7280,color:#f9fafb
    style Clean fill:#1c1917,stroke:#78716c,color:#fafaf9
    style Annot fill:#1e3a5f,stroke:#38bdf8,color:#f0f9ff
```

---

## 5 · Dịch thuật Bảo toàn Công thức

```mermaid
sequenceDiagram
    participant D as DocumentTranslator
    participant P as ProtectedBlockParser
    participant T as Google Translate / LLM
    participant V as TranslationValidator

    D->>P: mask("$$E=mc^2$$, \cite{ref}")
    P-->>D: "__SCIDOC_MATH_000__" + placeholder_map

    D->>T: translate(masked_text, "en"→"vi")
    T-->>D: text tiếng Việt có token

    D->>V: validate(translated, placeholder_map)
    Note over V: Regex: case-insensitive + space-tolerant
    V-->>D: ✅ is_valid=True, missing=[]

    D->>P: unmask(translated, placeholder_map)
    P-->>D: ✅ Văn bản Việt + công thức nguyên vẹn
```

> Validator sử dụng Regex `IGNORECASE` để nhận diện token dù bị đổi hoa thường, tránh cảnh báo `[WARNING] Translation dropped tokens` sai.

---

## 6 · Hợp nhất & Xuất bản Đa định dạng

```mermaid
flowchart LR
    C1["Chunk 1\n.md"] & C2["Chunk 2\n.md"] & C3["Chunk 3\n.md"] --> M

    M["🔗 MarkdownChunkMerger\nGhép nội dung · Sắp xếp heading\nChuẩn hóa đường dẫn ảnh"]

    M --> MD["📝 output.md\n+ images/"]
    M --> TEX["📐 LaTeXGenerator\nSinh mã nguồn .tex"]

    TEX --> COMP{"Compiler"}
    COMP -- "XeLaTeX / pdflatex" --> PDF1["📑 output.pdf\n(Chất lượng in ấn)"]
    COMP -- "ReportLab Fallback" --> PDF2["📑 output.pdf\n(Không cần TeX Live)"]

    style M fill:#1e3a5f,stroke:#38bdf8,color:#f0f9ff
    style PDF1 fill:#14532d,stroke:#4ade80,color:#f0fdf4
    style PDF2 fill:#3b1a08,stroke:#f97316,color:#fff7ed
```

---

## 7 · Giao diện Studio & Tính năng Tương tác

```mermaid
flowchart TD
    subgraph GUI["🖥️ Triple-Pane Desktop Studio (PySide6 Qt6)"]
        direction LR
        TREE["🌲 Project Panel\n─────────\nDanh sách dự án\nThống kê block"]
        VIEW["📄 PDF Viewer\n─────────\nRender từng trang\nHighlight vùng crop"]
        EDIT["✏️ Markdown / LaTeX\n─────────\nSide-by-side editor\nPreview trực tiếp"]
    end

    subgraph CHAT["💬 AI Assistant"]
        direction TB
        P["Chọn Provider\nGemini · LM Studio · GPT · Claude"]
        P --> ML["🔄 Live Model Discovery\nQuét API → danh sách mô hình thực tế"]
        ML --> MSG["Gửi câu hỏi + ngữ cảnh PDF"]
        MSG --> RES["Nhận câu trả lời\n(Không có thought/think)"]
    end

    subgraph REVIEW["🔍 Review Mode"]
        direction TB
        LOW["Phát hiện Block\nconfidence < 0.85"]
        LOW --> CMP["So sánh ảnh crop gốc\nvs LaTeX nhận diện"]
        CMP --> ACT["✅ Accept · ✏️ Edit · ❌ Reject"]
    end

    GUI --> CHAT & REVIEW
```

---

## Bảng tổng hợp công nghệ

| Giai đoạn | Module | Thư viện | Vai trò |
|---|---|---|---|
| Nạp PDF | `PDFSplitter` | PyMuPDF | Chia trang, render ảnh preview |
| Cache | `CacheManager` | SHA-256 + JSON | Tránh OCR lại trang đã xử lý |
| OCR chính | `MinerUService` | MinerU CLI | YOLOv8 layout + UniMERNet math |
| OCR dự phòng | `LocalOCRPipeline` | PyMuPDF + Heuristic | Bóc text vector, phân loại block |
| Kiểm tra Toán | `FormulaValidator` | SymPy | Kiểm cú pháp LaTeX, ngoặc cân bằng |
| Điều phối AI | `AIRouter` | httpx | Kết nối Gemini / OpenAI / LM Studio |
| Dịch thuật | `DocumentTranslator` | Google Translate | Dịch không giới hạn, bảo vệ công thức |
| Xác thực dịch | `TranslationValidator` | regex | Kiểm token không phân biệt hoa thường |
| Lọc suy nghĩ | `strip_thought_content` | re | Loại bỏ `<think>`, `Thinking Process` |
| Tạo LaTeX | `LaTeXGenerator` | Jinja2 template | Sinh `.tex` chuẩn AMSMath |
| Biên dịch | `LaTeXCompiler` | XeLaTeX / ReportLab | Xuất PDF chất lượng in ấn |
| Giao diện | `MainWindow` | PySide6 Qt6 | Dark-mode, bất đồng bộ QThread |
