"""CustomTkinter GUI for Multi Video Downloader."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    DND_FILES = None
    HAS_DND = False

from .browser.login_capture import capture_login_storage_state
from .core.errors import PlatformNotSupportedError
from .core.models import Backend, DownloadContext
from .core.pipeline import Pipeline
from .core.utils import check_ffmpeg, check_ytdlp, get_bilibili_quality_warning
from .extractors import get_extractor_for_url
from .tools.bilibili_id_resolver import resolve_bilibili_input_to_url
from .tools.bilibili_playlist_tools import download_bilibili_playlist_direct, is_bilibili_playlist_url
from .tools.bilibili_playlist_utils import expand_bilibili_playlist_urls

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MVDGui(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Multi Video Downloader")
        self.geometry("960x700")
        self.minsize(900, 640)

        self.url_var = ctk.StringVar()
        self.quality_var = ctk.StringVar(value="highest（默认最高）")
        self.cookies_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar(value=os.getcwd())
        self.playlist_mode_var = ctk.StringVar(value="全部")
        self.playlist_custom_var = ctk.StringVar(value="")
        self.template_var = ctk.StringVar(value="{author} - {title} ({id})")
        self.meta_var = ctk.StringVar(value="json")
        self.backend_var = ctk.StringVar(value="auto")
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.verbose_var = ctk.BooleanVar(value=False)

        self.platform_info_var = ctk.StringVar(value="平台：-")
        self.title_info_var = ctk.StringVar(value="视频标题：-")
        self.storage_state_var = ctk.StringVar(value="Storage State：未加载")
        self.vip_warning_var = ctk.StringVar(value="")
        self.progress_text_var = ctk.StringVar(value="进度：0%")

        self._cancel_event = threading.Event()
        self._download_running = False
        self._info_running = False

        self._build_ui()
        self._bind_events()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(top, text="Multi Video Downloader", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text="深色模式   v0.3.0").pack(side="right")

        url_frame = ctk.CTkFrame(self)
        url_frame.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(url_frame, text="URL 输入（支持粘贴，若环境支持则可拖拽）").pack(anchor="w", padx=12, pady=(10, 4))
        self.url_entry = ctk.CTkEntry(url_frame, textvariable=self.url_var, height=40, placeholder_text="https://www.bilibili.com/video/...")
        self.url_entry.pack(fill="x", padx=12, pady=(0, 10))
        if HAS_DND and DND_FILES:
            try:
                self.url_entry.drop_target_register(DND_FILES)
                self.url_entry.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                pass

        info_row = ctk.CTkFrame(self, fg_color="transparent")
        info_row.pack(fill="x", padx=16, pady=(2, 6))
        ctk.CTkLabel(info_row, textvariable=self.platform_info_var).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(info_row, textvariable=self.title_info_var).pack(side="left")
        self.refresh_btn = ctk.CTkButton(info_row, text="刷新信息", width=100, command=self.fetch_video_info)
        self.refresh_btn.pack(side="right")

        opt = ctk.CTkFrame(self)
        opt.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(opt, text="清晰度").grid(row=0, column=0, sticky="w", padx=12, pady=10)
        ctk.CTkComboBox(opt, values=["highest（默认最高）", "1080p", "720p", "480p", "360p"], variable=self.quality_var, command=self.on_quality_changed, width=200).grid(row=0, column=1, sticky="w", padx=8, pady=10)
        ctk.CTkLabel(opt, textvariable=self.vip_warning_var, text_color="#FFB800", font=ctk.CTkFont(size=13, weight="bold")).grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(opt, text="Cookies 文件").grid(row=2, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkButton(opt, text="选择文件", width=120, command=self.select_cookies).grid(row=2, column=1, sticky="w", padx=8, pady=8)
        ctk.CTkButton(opt, text="一键登录 B站", width=120, fg_color="#FF6B00", hover_color="#d95b00", command=lambda: self.start_login("bilibili")).grid(row=2, column=2, sticky="w", padx=8, pady=8)
        ctk.CTkButton(opt, text="一键登录抖音", width=120, fg_color="#FF6B00", hover_color="#d95b00", command=lambda: self.start_login("douyin")).grid(row=2, column=3, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(opt, textvariable=self.storage_state_var).grid(row=3, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(opt, text="分P / 合集").grid(row=4, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkComboBox(opt, values=["全部", "仅当前P", "自定义序号"], variable=self.playlist_mode_var, width=160).grid(row=4, column=1, sticky="w", padx=8, pady=8)
        self.playlist_custom_entry = ctk.CTkEntry(opt, textvariable=self.playlist_custom_var, width=220, placeholder_text="如 1,3-5")
        self.playlist_custom_entry.grid(row=4, column=2, columnspan=2, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(opt, text="输出文件夹").grid(row=5, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkEntry(opt, textvariable=self.output_dir_var).grid(row=5, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(opt, text="选择", width=100, command=self.choose_output_dir).grid(row=5, column=3, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(opt, text="文件名模板").grid(row=6, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkEntry(opt, textvariable=self.template_var).grid(row=6, column=1, columnspan=3, sticky="ew", padx=8, pady=8)

        ctk.CTkLabel(opt, text="后端").grid(row=7, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkComboBox(opt, values=["auto", "httpx", "ffmpeg", "ytdlp"], variable=self.backend_var, width=120).grid(row=7, column=1, sticky="w", padx=8, pady=8)
        ctk.CTkComboBox(opt, values=["json", "filename", "both"], variable=self.meta_var, width=120).grid(row=7, column=2, sticky="w", padx=8, pady=8)
        ctk.CTkCheckBox(opt, text="仅预览", variable=self.dry_run_var).grid(row=7, column=3, sticky="w", padx=8, pady=8)
        ctk.CTkCheckBox(opt, text="详细日志", variable=self.verbose_var).grid(row=8, column=3, sticky="w", padx=8, pady=(0, 8))
        opt.grid_columnconfigure(2, weight=1)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(6, 8))
        self.download_btn = ctk.CTkButton(btns, text="开始下载", height=44, font=ctk.CTkFont(size=16, weight="bold"), command=self.start_download)
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btns, text="取消", height=44, fg_color="gray45", command=self.cancel_download).pack(side="left", padx=(8, 0))

        progress_row = ctk.CTkFrame(self, fg_color="transparent")
        progress_row.pack(fill="x", padx=16, pady=(2, 4))
        self.progress = ctk.CTkProgressBar(progress_row, height=18)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress.set(0.0)
        ctk.CTkLabel(progress_row, textvariable=self.progress_text_var).pack(side="right")

        self.log_text = ctk.CTkTextbox(self, height=180)
        self.log_text.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _bind_events(self) -> None:
        self.url_var.trace_add("write", self.on_quality_changed)
        self.cookies_var.trace_add("write", self.on_quality_changed)
        self.playlist_mode_var.trace_add("write", self.on_playlist_mode_changed)
        self.on_playlist_mode_changed()
        self.on_quality_changed()

    def _ui(self, fn, *args) -> None:
        self.after(0, lambda: fn(*args))

    def _get_quality_value(self) -> str:
        raw = (self.quality_var.get() or "").strip()
        quality = raw.split("（", 1)[0].strip().lower()
        return quality if quality in {"highest", "1080p", "720p", "480p", "360p", "low"} else "highest"

    def _resolve_playlist_args(self) -> tuple[str | None, bool]:
        mode = (self.playlist_mode_var.get() or "全部").strip()
        if mode == "仅当前P":
            return None, True
        if mode == "自定义序号":
            custom = (self.playlist_custom_var.get() or "").strip()
            return (custom or None), False
        return None, False

    def on_playlist_mode_changed(self, *_args) -> None:
        mode = (self.playlist_mode_var.get() or "全部").strip()
        self.playlist_custom_entry.configure(state="normal" if mode == "自定义序号" else "disabled")

    def on_quality_changed(self, *_args) -> None:
        quality = self._get_quality_value()
        url = (self.url_var.get() or "").strip().lower()
        is_bili = "bilibili.com" in url or url.startswith("bv") or url.startswith("av")
        has_cookies = bool((self.cookies_var.get() or "").strip())
        warning = get_bilibili_quality_warning(quality, has_cookies) if is_bili else None
        self.vip_warning_var.set(warning or "")

    def on_drop(self, event) -> None:
        value = (event.data or "").strip().strip("{}")
        if value:
            self.url_var.set(value)

    def select_cookies(self) -> None:
        path = filedialog.askopenfilename(title="选择 cookies/storageState 文件", filetypes=[("Cookie/JSON 文件", "*.txt *.json"), ("所有文件", "*.*")])
        if path:
            self.cookies_var.set(path)
            self.storage_state_var.set(f"Storage State：已加载 {Path(path).name}")
            self.log(f"已加载登录态文件：{path}")

    def choose_output_dir(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir_var.set(folder)

    def start_login(self, platform: str) -> None:
        self.log(f"正在打开浏览器登录 {platform} ...")
        threading.Thread(target=self._login_thread, args=(platform,), daemon=True).start()

    def _login_thread(self, platform: str) -> None:
        output_file = Path("./auth") / f"{platform}_state.json"
        try:
            saved = asyncio.run(capture_login_storage_state(platform=platform, output_file=str(output_file), confirm_mode="button", browser_type="auto"))
            self._ui(self.cookies_var.set, str(saved))
            self._ui(self.storage_state_var.set, f"Storage State：已加载 {Path(saved).name}")
            self._ui(self.log, f"✓ {platform} 登录状态已保存：{saved}")
        except Exception as e:  # noqa: BLE001
            self._ui(self.log, f"登录失败：{e}")

    def fetch_video_info(self) -> None:
        if self._info_running:
            return
        self._info_running = True
        self.refresh_btn.configure(state="disabled")
        threading.Thread(target=self._fetch_info_thread, daemon=True).start()

    def _fetch_info_thread(self) -> None:
        try:
            asyncio.run(self._fetch_info_async())
        except Exception as e:  # noqa: BLE001
            self._ui(self.log, f"获取信息失败：{e}")
        finally:
            self._info_running = False
            self._ui(self.refresh_btn.configure, state="normal")

    async def _fetch_info_async(self) -> None:
        raw = (self.url_var.get() or "").strip()
        if not raw:
            self._ui(self.log, "请先输入 URL/BV/av")
            return
        url = raw
        if not raw.lower().startswith(("http://", "https://")):
            resolved = await resolve_bilibili_input_to_url(raw)
            if resolved:
                url = resolved.video_url
        extractor = get_extractor_for_url(url)
        if not extractor:
            self._ui(self.platform_info_var.set, "平台：不支持")
            self._ui(self.title_info_var.set, "视频标题：-")
            self._ui(self.log, "当前 URL 暂不支持")
            return
        backend_name = (self.backend_var.get() or "auto").lower()
        backend = Backend(backend_name) if backend_name in {"auto", "httpx", "ffmpeg", "ytdlp"} else Backend.AUTO
        ctx = DownloadContext(output_dir=self.output_dir_var.get() or "./downloads", template=self.template_var.get() or "{author} - {title} ({id})", meta_mode=self.meta_var.get() or "json", cookies=(self.cookies_var.get() or None), quality=self._get_quality_value(), backend=backend, dry_run=True, verbose=self.verbose_var.get(), prefer_no_watermark=True)
        media = await extractor.parse(url, ctx)
        self._ui(self.platform_info_var.set, f"平台：{extractor.get_platform_name()}")
        self._ui(self.title_info_var.set, f"视频标题：{media.title}")
        self._ui(self.log, f"已刷新：{media.title}")

    def start_download(self) -> None:
        if self._download_running:
            return
        self._cancel_event.clear()
        self._download_running = True
        self.download_btn.configure(state="disabled")
        self.progress.set(0.0)
        self.progress_text_var.set("进度：0%")
        self.log("开始下载...")
        threading.Thread(target=self._download_thread, daemon=True).start()

    def cancel_download(self) -> None:
        self._cancel_event.set()
        self.log("已请求取消：将在当前步骤完成后停止。")

    def _on_progress(self, percent: float, status: str) -> None:
        if self._cancel_event.is_set():
            return

        def update() -> None:
            p = max(0.0, min(100.0, float(percent)))
            self.progress.set(p / 100.0)
            state = (status or "").strip()
            self.progress_text_var.set(f"进度：{p:.0f}% ({state})" if state else f"进度：{p:.0f}%")

        self._ui(update)

    def _download_thread(self) -> None:
        try:
            asyncio.run(self._download_async())
            self._ui(self.log, "下载已取消。" if self._cancel_event.is_set() else "✅ 下载完成！")
        except Exception as e:  # noqa: BLE001
            self._ui(self.log, f"❌ 下载失败：{e}")
        finally:
            self._download_running = False
            self._ui(self.download_btn.configure, state="normal")

    async def _download_async(self) -> None:
        raw = (self.url_var.get() or "").strip()
        if not raw:
            raise ValueError("请先输入 URL")
        out_dir = (self.output_dir_var.get() or "").strip()
        if not out_dir:
            raise ValueError("请先选择输出目录")

        url = raw
        if not raw.lower().startswith(("http://", "https://")):
            resolved = await resolve_bilibili_input_to_url(raw)
            if resolved:
                url = resolved.video_url
                self._ui(self.platform_info_var.set, "平台：Bilibili")
                self._ui(self.title_info_var.set, f"视频标题：{resolved.title or '-'}")

        backend_name = (self.backend_var.get() or "auto").lower()
        backend = Backend(backend_name) if backend_name in {"auto", "httpx", "ffmpeg", "ytdlp"} else Backend.AUTO
        if backend == Backend.FFMPEG and not check_ffmpeg():
            raise ValueError("ffmpeg 未找到，请先安装 ffmpeg")
        if backend == Backend.YTDLP and not check_ytdlp():
            raise ValueError("yt-dlp 未安装，请先安装 yt-dlp")

        playlist_items, only_current = self._resolve_playlist_args()
        cookies_raw = (self.cookies_var.get() or "").strip()
        cookies = cookies_raw if cookies_raw and Path(cookies_raw).exists() else None
        ctx = DownloadContext(output_dir=out_dir, template=(self.template_var.get() or "{author} - {title} ({id})"), meta_mode=(self.meta_var.get() or "json"), cookies=cookies, quality=self._get_quality_value(), backend=backend, dry_run=self.dry_run_var.get(), verbose=self.verbose_var.get(), prefer_no_watermark=True, progress_callback=self._on_progress)

        if is_bilibili_playlist_url(url) and ("?p=" not in url):
            if self._cancel_event.is_set():
                return
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: download_bilibili_playlist_direct(url=url, output_dir=ctx.output_dir, filename_template=ctx.template, cookies=ctx.cookies, playlist_items=playlist_items, noplaylist=only_current, dry_run=ctx.dry_run, progress_callback=self._on_progress))
            return

        targets = expand_bilibili_playlist_urls(url, playlist_items, only_current) or [url]
        for idx, page_url in enumerate(targets, start=1):
            if self._cancel_event.is_set():
                return
            extractor = get_extractor_for_url(page_url)
            if not extractor:
                raise PlatformNotSupportedError(f"当前 URL 不支持：{page_url}")
            self._ui(self.platform_info_var.set, f"平台：{extractor.get_platform_name()}")
            self._ui(self.log, f"[{idx}/{len(targets)}] 解析视频信息...")
            media_info = await extractor.parse(page_url, ctx)
            self._ui(self.title_info_var.set, f"视频标题：{media_info.title}")
            pipeline = Pipeline(ctx)
            await pipeline.process(media_info)

    def log(self, message: str) -> None:
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def on_closing(self) -> None:
        self._cancel_event.set()
        self.destroy()


def main() -> None:
    app = MVDGui()
    app.mainloop()


if __name__ == "__main__":
    main()
