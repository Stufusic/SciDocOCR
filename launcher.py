"""SciDoc OCR Smart Launcher & Auto-Installer.
Checks environment, auto-installs dependencies via uv/pip, verifies models, and launches the app with 1 click.
"""

import sys
import os
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

APP_TITLE = "SciDoc OCR - Smart Launcher & Installer"

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = Path.cwd()
else:
    BUNDLE_DIR = Path(__file__).resolve().parent
    APP_DIR = BUNDLE_DIR

REQUIRED_PACKAGES = [
    "PySide6>=6.6.0",
    "PyMuPDF>=1.23.0",
    "httpx>=0.25.0",
    "sympy>=1.12",
    "reportlab>=4.0.0",
    "markdown-it-py>=3.0.0",
    "python-dotenv>=1.0.0"
]

class SciDocLauncherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("640x480")
        self.root.minsize(560, 400)
        self.root.configure(bg="#0f172a")

        ico_path = BUNDLE_DIR / "assets" / "app_icon.ico"
        if not ico_path.exists():
            ico_path = APP_DIR / "assets" / "app_icon.ico"

        png_path = BUNDLE_DIR / "assets" / "app_icon.png"
        if not png_path.exists():
            png_path = APP_DIR / "assets" / "app_icon.png"

        if ico_path.exists():
            try:
                self.root.iconbitmap(str(ico_path))
            except Exception:
                pass
        elif png_path.exists():
            try:
                icon_img = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, icon_img)
            except Exception:
                pass

        self._init_ui()
        self._check_initial_status()

    def _init_ui(self):
        # Header Frame
        header = tk.Frame(self.root, bg="#1e293b", padx=16, pady=12)
        header.pack(fill="x")

        title_lbl = tk.Label(
            header,
            text="⚡ SciDoc OCR Studio - Launcher",
            font=("Segoe UI", 15, "bold"),
            fg="#38bdf8",
            bg="#1e293b"
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            header,
            text="Tự động kiểm tra môi trường, tải thư viện phụ thuộc và khởi động hệ thống.",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b"
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Main Content Frame
        main_frame = tk.Frame(self.root, bg="#0f172a", padx=16, pady=12)
        main_frame.pack(fill="both", expand=True)

        # Status Label
        self.lbl_status = tk.Label(
            main_frame,
            text="Đang kiểm tra môi trường hệ thống...",
            font=("Segoe UI", 10, "bold"),
            fg="#f8fafc",
            bg="#0f172a"
        )
        self.lbl_status.pack(anchor="w", pady=(0, 6))

        # Progress Bar
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

        # Log Console
        log_lbl = tk.Label(
            main_frame,
            text="Nhật ký tiến trình (Log Console):",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a"
        )
        log_lbl.pack(anchor="w")

        self.txt_log = tk.Text(
            main_frame,
            bg="#020617",
            fg="#cbd5e1",
            font=("Consolas", 9),
            relief="solid",
            bd=1,
            wrap="word"
        )
        self.txt_log.pack(fill="both", expand=True, pady=(4, 10))

        # Bottom Buttons Bar
        btn_bar = tk.Frame(self.root, bg="#1e293b", padx=16, pady=10)
        btn_bar.pack(fill="x", side="bottom")

        self.btn_install_cpu = tk.Button(
            btn_bar,
            text="📦 Cài đặt CPU (Không cần GPU)",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=6,
            command=lambda: self._start_install_thread(mode="cpu")
        )
        self.btn_install_cpu.pack(side="left", padx=(0, 6))

        self.btn_install_gpu = tk.Button(
            btn_bar,
            text="⚡ Cài đặt GPU (MinerU CUDA)",
            font=("Segoe UI", 9, "bold"),
            bg="#0f766e",
            fg="#f0fdfa",
            activebackground="#115e59",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=6,
            command=lambda: self._start_install_thread(mode="gpu")
        )
        self.btn_install_gpu.pack(side="left")

        self.btn_launch = tk.Button(
            btn_bar,
            text="🚀 Khởi chạy SciDoc OCR",
            font=("Segoe UI", 10, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=6,
            command=self._launch_app
        )
        self.btn_launch.pack(side="right")

    def _log(self, message: str):
        self.txt_log.insert("end", message + "\n")
        self.txt_log.see("end")

    def _check_initial_status(self):
        self._log("✓ Kiểm tra Python executable: " + sys.executable)
        self._log("✓ Thư mục ứng dụng: " + str(APP_DIR))

        # Check PySide6
        try:
            import PySide6
            self._log(f"✓ Đã phát hiện PySide6 v{PySide6.__version__}")
            has_pyside6 = True
        except ImportError:
            self._log("✗ Chưa cài đặt PySide6")
            has_pyside6 = False

        # Check PyMuPDF
        try:
            import fitz
            self._log(f"✓ Đã phát hiện PyMuPDF (fitz) v{fitz.__version__}")
            has_fitz = True
        except ImportError:
            self._log("✗ Chưa cài đặt PyMuPDF")
            has_fitz = False

        # Check Torch & CUDA
        try:
            import torch
            cuda_ok = torch.cuda.is_available()
            device_name = torch.cuda.get_device_name(0) if cuda_ok else "CPU Only"
            self._log(f"✓ Đã phát hiện PyTorch v{torch.__version__} (CUDA: {cuda_ok} - {device_name})")
        except ImportError:
            self._log("ℹ PyTorch chưa được nạp trong môi trường này (Chế độ nhẹ).")

        if has_pyside6 and has_fitz:
            self.lbl_status.config(text="✓ Môi trường sẵn sàng! Bạn có thể bấm Khởi chạy ngay.", fg="#4ade80")
        else:
            self.lbl_status.config(text="⚠️ Phát hiện thiếu thư viện. Vui lòng bấm Cài đặt bên dưới.", fg="#facc15")

    def _start_install_thread(self, mode: str = "cpu"):
        self.btn_install_cpu.config(state="disabled")
        self.btn_install_gpu.config(state="disabled")
        self.btn_launch.config(state="disabled")
        self.progress.start(10)
        
        mode_label = "Bản Nhẹ / CPU (Không cần GPU)" if mode == "cpu" else "Bản Đầy Đủ / GPU (MinerU CUDA)"
        self.lbl_status.config(text=f"Đang tự động cài đặt {mode_label}...", fg="#38bdf8")

        thread = threading.Thread(target=self._run_installer, args=(mode,), daemon=True)
        thread.start()

    def _run_installer(self, mode: str = "cpu"):
        self._log("\n" + "=" * 50)
        if mode == "cpu":
            self._log("BẮT ĐẦU CÀI ĐẶT BẢN NHẸ / CPU (KHÔNG CẦN GPU)...")
        else:
            self._log("BẮT ĐẦU CÀI ĐẶT BẢN GPU FULL (MINERU + CUDA)...")
        self._log("=" * 50)

        # 1. Try uv first, fallback to pip
        use_uv = False
        try:
            subprocess.run(["uv", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            use_uv = True
            self._log("✓ Đã tìm thấy công cụ uv (Tốc độ cao)")
        except Exception:
            self._log("ℹ uv chưa có sẵn, sẽ sử dụng pip để cài đặt.")

        cmd = ["uv", "pip", "install"] if use_uv else [sys.executable, "-m", "pip", "install"]
        
        req_file = APP_DIR / "requirements.txt"
        if req_file.exists():
            cmd.extend(["-r", str(req_file)])
        else:
            cmd.extend(REQUIRED_PACKAGES)

        if mode == "gpu":
            cmd.append("mineru[all]")

        self._log("Đang thực thi: " + " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(APP_DIR)
            )

            for line in proc.stdout:
                clean_line = line.strip()
                if clean_line:
                    self._log(clean_line)

            proc.wait()

            if proc.returncode == 0:
                self._log("\n✓ CÀI ĐẶT HOÀN TẤT THÀNH CÔNG!")
                self.root.after(0, self._on_install_success)
            else:
                self._log(f"\n✗ Cài đặt gặp lỗi (Mã lỗi {proc.returncode}).")
                self.root.after(0, self._on_install_failed)
        except Exception as e:
            self._log(f"\n✗ Lỗi tiến trình cài đặt: {e}")
            self.root.after(0, self._on_install_failed)

    def _on_install_success(self):
        self.progress.stop()
        self.btn_install_cpu.config(state="normal")
        self.btn_install_gpu.config(state="normal")
        self.btn_launch.config(state="normal")
        self.lbl_status.config(text="✓ Cài đặt thành công! Hệ thống sẵn sàng khởi chạy.", fg="#4ade80")
        messagebox.showinfo("Thành công", "Đã cài đặt hoàn tất các gói phụ thuộc!\nBấm 'Khởi chạy SciDoc OCR' để mở ứng dụng.")

    def _on_install_failed(self):
        self.progress.stop()
        self.btn_install_cpu.config(state="normal")
        self.btn_install_gpu.config(state="normal")
        self.btn_launch.config(state="normal")
        self.lbl_status.config(text="✗ Cài đặt chưa hoàn tất. Vui lòng kiểm tra log bên dưới.", fg="#ef4444")

    def _launch_app(self):
        self._log("\n🚀 Đang khởi động SciDoc OCR Studio...")
        self.lbl_status.config(text="Đang mở SciDoc OCR Studio...", fg="#38bdf8")

        # Launch app.main via background subprocess and close launcher
        cmd = [sys.executable, "-m", "app.main"]
        try:
            subprocess.Popen(cmd, cwd=str(APP_DIR))
            # Close launcher after 1.2s
            self.root.after(1200, self.root.destroy)
        except Exception as e:
            self._log(f"✗ Không thể mở ứng dụng: {e}")
            messagebox.showerror("Lỗi Khởi Chạy", f"Không thể mở ứng dụng:\n{e}")

def main():
    root = tk.Tk()
    app = SciDocLauncherGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
