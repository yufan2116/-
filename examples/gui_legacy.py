"""早期实验版 Tkinter GUI（已归档）

注意：
- 此文件为历史版本，仅作为参考示例保留，不随包一起发布/安装。
- 正式使用请运行包内的 `multi_video_dl.gui`（参见 README / start_mvd.bat）。
"""

from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox, filedialog

from multi_video_dl.core.errors import (
    PlatformNotSupportedError,
    FFmpegNotFoundError,
    YtDlpNotFoundError,
    MultiVideoDLError,
)
from multi_video_dl.core.models import Backend, DownloadContext
from multi_video_dl.core.utils import check_ffmpeg, check_ytdlp
from multi_video_dl.core.pipeline import Pipeline
from multi_video_dl.extractors import get_extractor_for_url


@dataclass
class GuiConfig:
    """GUI 默认配置"""

    default_output: str = "./downloads"
    default_template: str = "{author} - {title} ({id})"
    default_meta: str = "json"


class MvdGui(tk.Tk):
    """主窗口（历史版本）"""

    def __init__(self) -> None:
        super().__init__()
        self.title("Multi Video DL - Legacy GUI")
        self.geometry("760x460")
        self.resizable(False, False)

        self.config_data = GuiConfig()
        self._create_widgets()

    # ---------- UI ----------
    def _create_widgets(self) -> None:
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # URL
        ttk.Label(main, text="视频 URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(main, textvariable=self.url_var, width=80)
        url_entry.grid(row=0, column=1, columnspan=3, sticky="we", pady=2)

        # 输出目录
        ttk.Label(main, text="输出目录:").grid(row=1, column=0, sticky="w")
        self.out_var = tk.StringVar(value=self.config_data.default_output)
        out_entry = ttk.Entry(main, textvariable=self.out_var, width=60)
        out_entry.grid(row=1, column=1, sticky="we", pady=2)

        def choose_out() -> None:
            path = filedialog.askdirectory(title="选择输出目录")
            if path:
                self.out_var.set(path)

        ttk.Button(main, text="浏览...", command=choose_out).grid(
            row=1, column=2, sticky="w", padx=4
        )

        # 模板
        ttk.Label(main, text="文件名模板:").grid(row=2, column=0, sticky="w")
        self.template_var = tk.StringVar(value=self.config_data.default_template)
        template_entry = ttk.Entry(main, textvariable=self.template_var, width=80)
        template_entry.grid(row=2, column=1, columnspan=3, sticky="we", pady=2)

        # backend 选择
        ttk.Label(main, text="后端:").grid(row=3, column=0, sticky="w")
        self.backend_var = tk.StringVar(value="auto")
        backend_combo = ttk.Combobox(
            main,
            textvariable=self.backend_var,
            values=["auto", "httpx", "ffmpeg", "ytdlp"],
            state="readonly",
            width=10,
        )
        backend_combo.grid(row=3, column=1, sticky="w", pady=2)

        # meta 选项
        ttk.Label(main, text="元数据:").grid(row=3, column=2, sticky="e")
        self.meta_var = tk.StringVar(value=self.config_data.default_meta)
        meta_combo = ttk.Combobox(
            main,
            textvariable=self.meta_var,
            values=["json", "filename", "both"],
            state="readonly",
            width=10,
        )
        meta_combo.grid(row=3, column=3, sticky="w", pady=2)

        # 选项
        self.dry_run_var = tk.BooleanVar(value=True)
        self.verbose_var = tk.BooleanVar(value=False)
        dry_chk = ttk.Checkbutton(main, text="仅预览 (dry-run)", variable=self.dry_run_var)
        dry_chk.grid(row=4, column=0, sticky="w", pady=4)
        verbose_chk = ttk.Checkbutton(main, text="详细日志", variable=self.verbose_var)
        verbose_chk.grid(row=4, column=1, sticky="w", pady=4)

        # 按钮
        self.start_btn = ttk.Button(main, text="开始下载", command=self.on_start)
        self.start_btn.grid(row=4, column=3, sticky="e")

        # 日志区域
        ttk.Label(main, text="日志:").grid(row=5, column=0, sticky="nw", pady=(8, 2))
        self.log_text = tk.Text(main, height=14, width=90, state=tk.DISABLED)
        self.log_text.grid(row=5, column=1, columnspan=3, sticky="nsew")

        scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=5, column=4, sticky="ns")
        self.log_text["yscrollcommand"] = scrollbar.set

        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)

    # ---------- 日志 & 状态 ----------
    def log(self, msg: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.update_idletasks()

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.start_btn.configure(state=tk.DISABLED)
            self.config(cursor="watch")
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.config(cursor="")
        self.update_idletasks()

    # ---------- 事件 ----------
    def on_start(self) -> None:
        url = (self.url_var.get() or "").strip()
        if not url:
            messagebox.showwarning("提示", "请先输入视频 URL")
            return

        out_dir = (self.out_var.get() or "").strip()
        if not out_dir:
            messagebox.showwarning("提示", "请先选择输出目录")
            return

        backend_name = self.backend_var.get() or "auto"
        meta_mode = self.meta_var.get() or "json"

        # 依赖检查
        if backend_name == "ffmpeg" and not check_ffmpeg():
            messagebox.showerror("错误", "ffmpeg 未找到，请先在系统中安装 ffmpeg")
            return
        if backend_name == "ytdlp" and not check_ytdlp():
            messagebox.showerror("错误", "yt-dlp 未安装，请先运行: pip install yt-dlp")
            return

        if meta_mode not in {"json", "filename", "both"}:
            messagebox.showerror("错误", f"元数据模式不合法: {meta_mode}")
            return

        try:
            backend_enum = Backend(backend_name.lower())
        except ValueError:
            messagebox.showerror("错误", f"后端参数不合法: {backend_name}")
            return

        self.set_busy(True)
        self.log("开始任务...")
        self.log(f"URL: {url}")
        self.log(f"输出目录: {out_dir}")
        self.log(f"后端: {backend_enum.value}, dry-run={self.dry_run_var.get()}")

        thread = threading.Thread(
            target=self._run_download_thread,
            args=(url, out_dir, self.template_var.get(), meta_mode, backend_enum),
            daemon=True,
        )
        thread.start()

    # ---------- 后台线程 ----------
    def _run_download_thread(
        self,
        url: str,
        out_dir: str,
        template: str,
        meta_mode: str,
        backend: Backend,
    ) -> None:
        try:
            asyncio.run(
                self._run_download_async(
                    url=url,
                    out_dir=out_dir,
                    template=template,
                    meta_mode=meta_mode,
                    backend=backend,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._on_download_error, exc)

    async def _run_download_async(
        self,
        url: str,
        out_dir: str,
        template: str,
        meta_mode: str,
        backend: Backend,
    ) -> None:
        ctx = DownloadContext(
            output_dir=out_dir,
            template=template,
            meta_mode=meta_mode,
            cookies=None,
            backend=backend,
            dry_run=self.dry_run_var.get(),
            verbose=self.verbose_var.get(),
            prefer_no_watermark=True,
        )

        try:
            extractor = get_extractor_for_url(url)
            if not extractor:
                raise PlatformNotSupportedError(
                    f"当前 URL 不支持: {url}\n目前仅支持 Bilibili，抖音/小红书待实现。"
                )

            self.after(0, self.log, f"检测到平台: {extractor.get_platform_name()}")
            self.after(0, self.log, "开始解析视频信息...")

            media_info = await extractor.parse(url, ctx)

            self.after(0, self.log, f"标题: {media_info.title}")
            self.after(0, self.log, f"作者: {media_info.author}")
            self.after(0, self.log, f"共 {len(media_info.items)} 个媒体项")

            pipeline = Pipeline(ctx)
            media_path, metadata_path = await pipeline.process(media_info)

            if ctx.dry_run:
                msg = f"[DRY-RUN] 目标文件: {media_path}"
                if metadata_path:
                    msg += f"\n元数据文件: {metadata_path}"
                self.after(0, self._on_download_success, msg)
            else:
                msg = f"下载完成: {media_path}"
                if metadata_path:
                    msg += f"\n元数据: {metadata_path}"
                self.after(0, self._on_download_success, msg)

        except (FFmpegNotFoundError, YtDlpNotFoundError, MultiVideoDLError) as exc:
            self.after(0, self._on_download_error, exc)
        except Exception as exc:  # noqa: BLE001
            self.after(0, self._on_download_error, exc)

    # ---------- 结果回调 ----------
    def _on_download_success(self, msg: str) -> None:
        self.set_busy(False)
        self.log(msg)
        messagebox.showinfo("完成", msg)

    def _on_download_error(self, error: Exception) -> None:
        self.set_busy(False)
        self.log(f"错误: {error}")
        messagebox.showerror("错误", str(error))


def main() -> None:
    """GUI 入口（历史版本）"""

    app = MvdGui()
    app.mainloop()


if __name__ == "__main__":
    main()

