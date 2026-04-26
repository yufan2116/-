"""Browser-based web frontend for Bilibili downloads."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import warnings
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from requests.exceptions import RequestsDependencyWarning

from .browser.login_capture import capture_login_storage_state
from .core.errors import PlatformNotSupportedError
from .core.models import Backend, DownloadContext
from .core.pipeline import Pipeline
from .core.utils import check_ffmpeg, check_ytdlp, get_bilibili_quality_warning
from .extractors import get_extractor_for_url
from .tools.bilibili_id_resolver import resolve_bilibili_input_to_url
from .tools.bilibili_playlist_tools import (
    download_bilibili_playlist_direct,
    is_bilibili_playlist_url,
)
from .tools.bilibili_playlist_utils import expand_bilibili_playlist_urls

DEFAULT_OUTPUT_DIR = r"d:\Users\syf21\Downloads"


def _detect_default_cookies_path() -> str:
    """启动时自动复用已保存的 B 站登录态文件。"""
    candidates = [
        Path("./auth/bilibili_state.json"),
        Path("./auth/storage_state.json"),
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ""

# 部分环境会出现 requests 版本组合告警（不影响本工具主流程），这里避免刷屏。
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bilibili 下载器</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #151515; color: #f3f3f3; }
    .wrap { max-width: 1000px; margin: 0 auto; padding: 20px; }
    .card { background: #222; border-radius: 10px; padding: 14px; margin-bottom: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    .field { display: flex; flex-direction: column; flex: 1 1 260px; }
    label { margin-bottom: 6px; font-size: 13px; color: #cfcfcf; }
    input, select, textarea, button {
      background: #111; color: #fff; border: 1px solid #444; border-radius: 6px; padding: 8px;
    }
    textarea { min-height: 180px; width: 100%; box-sizing: border-box; }
    button { cursor: pointer; }
    .btn { background: #0d6efd; border: none; padding: 10px 12px; }
    .btn.warn { background: #dc3545; }
    .btn.login { background: #ff6b00; }
    .muted { color: #aaa; font-size: 13px; }
    progress { width: 100%; height: 18px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>Bilibili 下载 - Web 控制台</h2>

    <div class="card">
      <div class="field">
        <label>URL / BV / av</label>
        <input id="url" placeholder="https://www.bilibili.com/video/..." />
      </div>
      <div class="row" style="margin-top:10px;">
        <button class="btn" onclick="refreshInfo()">刷新信息</button>
      </div>
      <p id="platform" class="muted">平台：-</p>
      <p id="title" class="muted">视频标题：-</p>
      <p id="vipwarn" class="muted"></p>
    </div>

    <div class="card">
      <div class="row">
        <div class="field">
          <label>清晰度</label>
          <select id="quality">
            <option value="highest">highest（默认最高）</option>
            <option value="1080p">1080p</option>
            <option value="720p">720p</option>
            <option value="480p">480p</option>
            <option value="360p">360p</option>
            <option value="low">low</option>
          </select>
        </div>
        <div class="field">
          <label>Cookies / storageState 文件路径</label>
          <input id="cookies" placeholder="例如 D:\\auth\\bilibili_state.json" />
        </div>
      </div>
      <div class="row" style="margin-top:10px;">
        <button class="btn login" onclick="captureLogin()">一键登录 B站</button>
      </div>
      <p id="storage" class="muted">Storage State：未加载</p>
    </div>

    <div class="card">
      <div class="row">
        <div class="field">
          <label>分P / 合集</label>
          <select id="playlist_mode">
            <option value="all">全部</option>
            <option value="current">仅当前P</option>
            <option value="custom">自定义序号</option>
          </select>
        </div>
        <div class="field">
          <label>自定义序号（例如 1,3-5）</label>
          <input id="playlist_custom" />
        </div>
      </div>
      <div class="row" style="margin-top:10px;">
        <div class="field">
          <label>输出目录</label>
          <input id="output_dir" />
        </div>
        <div class="field">
          <label>文件名模板</label>
          <input id="template" value="{author} - {title} ({id})" />
        </div>
      </div>
      <div class="row" style="margin-top:10px;">
        <div class="field">
          <label>后端</label>
          <select id="backend">
            <option value="auto">auto</option>
            <option value="httpx">httpx</option>
            <option value="ffmpeg">ffmpeg</option>
            <option value="ytdlp">ytdlp</option>
          </select>
        </div>
        <div class="field">
          <label>元数据模式</label>
          <select id="meta">
            <option value="json">json</option>
            <option value="filename">filename</option>
            <option value="both">both</option>
          </select>
        </div>
        <div class="field">
          <label>选项</label>
          <div>
            <label><input type="checkbox" id="dry_run" /> 仅预览</label>
            <label style="margin-left:12px;"><input type="checkbox" id="verbose" /> 详细日志</label>
          </div>
        </div>
      </div>
      <div class="row" style="margin-top:10px;">
        <button class="btn" onclick="startDownload()">开始下载</button>
        <button class="btn warn" onclick="cancelDownload()">取消</button>
      </div>
    </div>

    <div class="card">
      <progress id="progress" value="0" max="100"></progress>
      <p id="progress_text" class="muted">进度：0%</p>
      <textarea id="logs" readonly></textarea>
    </div>
  </div>

  <script>
    function payload() {
      return {
        url: document.getElementById("url").value,
        quality: document.getElementById("quality").value,
        cookies: document.getElementById("cookies").value,
        output_dir: document.getElementById("output_dir").value,
        playlist_mode: document.getElementById("playlist_mode").value,
        playlist_custom: document.getElementById("playlist_custom").value,
        template: document.getElementById("template").value,
        meta: document.getElementById("meta").value,
        backend: document.getElementById("backend").value,
        dry_run: document.getElementById("dry_run").checked,
        verbose: document.getElementById("verbose").checked
      };
    }
    async function callApi(path, method, body) {
      const r = await fetch(path, {
        method: method,
        headers: {"Content-Type":"application/json"},
        body: body ? JSON.stringify(body) : null
      });
      return await r.json();
    }
    async function refreshInfo() { await callApi("/api/info", "POST", payload()); }
    async function startDownload() { await callApi("/api/download", "POST", payload()); }
    async function cancelDownload() { await callApi("/api/cancel", "POST", {}); }
    async function captureLogin() { await callApi("/api/login", "POST", {platform: "bilibili"}); }
    async function poll() {
      const s = await callApi("/api/state", "GET");
      document.getElementById("platform").innerText = "平台：" + (s.platform || "-");
      document.getElementById("title").innerText = "视频标题：" + (s.title || "-");
      document.getElementById("storage").innerText = "Storage State：" + (s.storage_state || "未加载");
      document.getElementById("vipwarn").innerText = s.vip_warning || "";
      document.getElementById("progress").value = s.progress || 0;
      document.getElementById("progress_text").innerText = s.progress_text || "进度：0%";
      if (!document.activeElement || document.activeElement.id !== "logs") {
        document.getElementById("logs").value = (s.logs || []).join("\\n");
      }
      const cookiesInput = document.getElementById("cookies");
      if ((!cookiesInput.value || cookiesInput.value.trim() === "") && s.cookies_path) {
        cookiesInput.value = s.cookies_path;
      }
      const outputInput = document.getElementById("output_dir");
      if (!outputInput.value && s.output_dir) { outputInput.value = s.output_dir; }
    }
    setInterval(poll, 1000);
    poll();
  </script>
</body>
</html>
"""


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.logs: list[str] = []
        self.platform = "-"
        self.title = "-"
        self.cookies_path = _detect_default_cookies_path()
        self.storage_state = f"已加载 {Path(self.cookies_path).name}" if self.cookies_path else "未加载"
        self.vip_warning = ""
        self.progress = 0.0
        self.progress_text = "进度：0%"
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.download_running = False
        self.info_running = False
        self.login_running = False
        self.cancel_event = threading.Event()

    def log(self, message: str) -> None:
        with self.lock:
            self.logs.append(message)
            self.logs = self.logs[-500:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "logs": list(self.logs),
                "platform": self.platform,
                "title": self.title,
                "storage_state": self.storage_state,
                "cookies_path": self.cookies_path,
                "vip_warning": self.vip_warning,
                "progress": self.progress,
                "progress_text": self.progress_text,
                "output_dir": self.output_dir,
                "download_running": self.download_running,
                "info_running": self.info_running,
                "login_running": self.login_running,
            }


STATE = AppState()


def _normalize_quality(raw: str) -> str:
    quality = (raw or "highest").strip().lower().split("（", 1)[0].strip()
    return quality if quality in {"highest", "1080p", "720p", "480p", "360p", "low"} else "highest"


def _parse_backend(raw: str) -> Backend:
    backend_name = (raw or "auto").strip().lower()
    return Backend(backend_name) if backend_name in {"auto", "httpx", "ffmpeg", "ytdlp"} else Backend.AUTO


def _resolve_playlist_args(payload: dict[str, Any]) -> tuple[str | None, bool]:
    mode = (payload.get("playlist_mode") or "all").strip()
    if mode == "current":
        return None, True
    if mode == "custom":
        custom = (payload.get("playlist_custom") or "").strip()
        return (custom or None), False
    return None, False


def _update_quality_warning(url: str, quality: str, cookies: str | None) -> None:
    lowered = (url or "").strip().lower()
    is_bili = "bilibili.com" in lowered or lowered.startswith("bv") or lowered.startswith("av")
    warning = get_bilibili_quality_warning(quality=quality, has_cookies=bool((cookies or "").strip())) if is_bili else None
    with STATE.lock:
        STATE.vip_warning = warning or ""


async def _fetch_info_async(payload: dict[str, Any]) -> None:
    raw = (payload.get("url") or "").strip()
    if not raw:
        STATE.log("请先输入 URL/BV/av")
        return
    quality = _normalize_quality(payload.get("quality") or "highest")
    cookies = (payload.get("cookies") or "").strip() or None
    _update_quality_warning(raw, quality, cookies)

    url = raw
    if not raw.lower().startswith(("http://", "https://")):
        resolved = await resolve_bilibili_input_to_url(raw)
        if resolved:
            url = resolved.video_url

    extractor = get_extractor_for_url(url)
    if not extractor:
        with STATE.lock:
            STATE.platform = "不支持"
            STATE.title = "-"
        STATE.log("当前 URL 暂不支持")
        return

    ctx = DownloadContext(
        output_dir=(payload.get("output_dir") or os.getcwd()),
        template=(payload.get("template") or "{author} - {title} ({id})"),
        meta_mode=(payload.get("meta") or "json"),
        cookies=cookies,
        quality=quality,
        backend=_parse_backend(payload.get("backend") or "auto"),
        dry_run=True,
        verbose=bool(payload.get("verbose")),
        prefer_no_watermark=True,
    )
    media = await extractor.parse(url, ctx)
    with STATE.lock:
        STATE.platform = extractor.get_platform_name()
        STATE.title = media.title
        STATE.output_dir = ctx.output_dir
    STATE.log(f"已刷新：{media.title}")


def _on_progress(percent: float, status: str) -> None:
    if STATE.cancel_event.is_set():
        return
    p = max(0.0, min(100.0, float(percent)))
    label = (status or "").strip()
    with STATE.lock:
        STATE.progress = p
        STATE.progress_text = f"进度：{p:.0f}% ({label})" if label else f"进度：{p:.0f}%"


async def _download_async(payload: dict[str, Any]) -> None:
    raw = (payload.get("url") or "").strip()
    if not raw:
        raise ValueError("请先输入 URL")
    out_dir = (payload.get("output_dir") or "").strip()
    if not out_dir:
        raise ValueError("请先输入输出目录")

    quality = _normalize_quality(payload.get("quality") or "highest")
    cookies_raw = (payload.get("cookies") or "").strip()
    cookies = cookies_raw if cookies_raw and Path(cookies_raw).exists() else None
    backend = _parse_backend(payload.get("backend") or "auto")
    _update_quality_warning(raw, quality, cookies)

    if backend == Backend.FFMPEG and not check_ffmpeg():
        raise ValueError("ffmpeg 未找到，请先安装 ffmpeg")
    if backend == Backend.YTDLP and not check_ytdlp():
        raise ValueError("yt-dlp 未安装，请先安装 yt-dlp")

    url = raw
    if not raw.lower().startswith(("http://", "https://")):
        resolved = await resolve_bilibili_input_to_url(raw)
        if resolved:
            url = resolved.video_url
            with STATE.lock:
                STATE.platform = "Bilibili"
                STATE.title = resolved.title or "-"

    playlist_items, only_current = _resolve_playlist_args(payload)
    ctx = DownloadContext(
        output_dir=out_dir,
        template=(payload.get("template") or "{author} - {title} ({id})"),
        meta_mode=(payload.get("meta") or "json"),
        cookies=cookies,
        quality=quality,
        backend=backend,
        dry_run=bool(payload.get("dry_run")),
        verbose=bool(payload.get("verbose")),
        prefer_no_watermark=True,
        progress_callback=_on_progress,
    )

    if is_bilibili_playlist_url(url) and ("?p=" not in url):
        if STATE.cancel_event.is_set():
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: download_bilibili_playlist_direct(
                url=url,
                output_dir=ctx.output_dir,
                filename_template=ctx.template,
                cookies=ctx.cookies,
                playlist_items=playlist_items,
                noplaylist=only_current,
                dry_run=ctx.dry_run,
                progress_callback=_on_progress,
            ),
        )
        return

    targets = expand_bilibili_playlist_urls(url, playlist_items, only_current) or [url]
    for idx, page_url in enumerate(targets, start=1):
        if STATE.cancel_event.is_set():
            return
        extractor = get_extractor_for_url(page_url)
        if not extractor:
            raise PlatformNotSupportedError(f"当前 URL 不支持：{page_url}")
        with STATE.lock:
            STATE.platform = extractor.get_platform_name()
        STATE.log(f"[{idx}/{len(targets)}] 解析视频信息...")
        media_info = await extractor.parse(page_url, ctx)
        with STATE.lock:
            STATE.title = media_info.title
        pipeline = Pipeline(ctx)
        await pipeline.process(media_info)


def _launch_info_worker(payload: dict[str, Any]) -> None:
    with STATE.lock:
        if STATE.info_running:
            return
        STATE.info_running = True
    try:
        asyncio.run(_fetch_info_async(payload))
    except Exception as e:  # noqa: BLE001
        err_text = str(e)
        if "412" in err_text and "BiliBili" in err_text:
            STATE.log("获取信息失败：B站返回 412（风控拦截）。请先点击“一键登录 B站”后重试。")
        else:
            STATE.log(f"获取信息失败：{e}")
    finally:
        with STATE.lock:
            STATE.info_running = False


def _launch_login_worker(platform: str) -> None:
    already_running = False
    with STATE.lock:
        if STATE.login_running:
            already_running = True
        else:
            STATE.login_running = True
    if already_running:
        STATE.log("已有登录窗口在进行中，请先完成当前登录。")
        return
    STATE.log(f"正在打开浏览器登录 {platform} ...")
    STATE.log("请在弹出的页面完成登录；检测到登录态后会自动保存。")
    output_file = Path("./auth") / f"{platform}_state.json"
    try:
        saved = asyncio.run(
            capture_login_storage_state(
                platform=platform,
                output_file=str(output_file),
                confirm_mode="button",
                browser_type="auto",
            )
        )
        with STATE.lock:
            STATE.storage_state = f"已加载 {Path(saved).name}"
            STATE.cookies_path = str(saved)
        STATE.log(f"✓ {platform} 登录状态已保存：{saved}")
    except Exception as e:  # noqa: BLE001
        STATE.log(f"登录失败：{e}")
    finally:
        with STATE.lock:
            STATE.login_running = False


def _launch_download_worker(payload: dict[str, Any]) -> None:
    with STATE.lock:
        if STATE.download_running:
            return
        STATE.download_running = True
        STATE.progress = 0.0
        STATE.progress_text = "进度：0%"
        STATE.output_dir = (payload.get("output_dir") or os.getcwd()).strip()
    STATE.cancel_event.clear()
    STATE.log("开始下载...")
    try:
        asyncio.run(_download_async(payload))
        STATE.log("下载已取消。" if STATE.cancel_event.is_set() else "下载完成！")
    except Exception as e:  # noqa: BLE001
        err_text = str(e)
        if "412" in err_text and "BiliBili" in err_text:
            STATE.log("下载失败：B站返回 412（风控拦截）。请先点击“一键登录 B站”，并重试下载。")
        else:
            STATE.log(f"下载失败：{e}")
    finally:
        with STATE.lock:
            STATE.download_running = False


class _Handler(BaseHTTPRequestHandler):
    server_version = "MVDWeb/0.1"

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            self._send_json(STATE.snapshot())
            return
        self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._read_json()

        if path == "/api/info":
            threading.Thread(target=_launch_info_worker, args=(payload,), daemon=True).start()
            self._send_json({"ok": True})
            return

        if path == "/api/login":
            platform = (payload.get("platform") or "").strip().lower()
            if platform != "bilibili":
                self._send_json({"ok": False, "error": "仅支持 bilibili"}, HTTPStatus.BAD_REQUEST)
                return
            threading.Thread(target=_launch_login_worker, args=("bilibili",), daemon=True).start()
            self._send_json({"ok": True})
            return

        if path == "/api/download":
            threading.Thread(target=_launch_download_worker, args=(payload,), daemon=True).start()
            self._send_json({"ok": True})
            return

        if path == "/api/cancel":
            STATE.cancel_event.set()
            STATE.log("已请求取消：将在当前步骤完成后停止。")
            self._send_json({"ok": True})
            return

        self._send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    STATE.log(f"Web 控制台已启动：{url}")
    print(f"Web 控制台已启动：{url}")
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
