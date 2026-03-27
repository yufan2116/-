"""Playwright 登录态捕获。

启动可见浏览器，让用户手动登录后确认，
将当前 context 的 storageState 保存为 JSON 文件，供后续复用。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal, Optional


HOME_URLS: dict[str, str] = {
    "bilibili": "https://www.bilibili.com/",
    "douyin": "https://www.douyin.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/",
}

ConfirmMode = Literal["enter", "button", "either"]
BrowserType = Literal["auto", "chromium", "firefox", "webkit"]

_BUTTON_INIT_SCRIPT = """
(() => {
  const KEY = "__mvd_login_done__";
  const BTN_ID = "__mvd_login_done_btn__";
  const createBtn = () => {
    if (document.getElementById(BTN_ID)) return;
    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.innerText = "已登录完成";
    btn.style.position = "fixed";
    btn.style.right = "20px";
    btn.style.bottom = "20px";
    btn.style.zIndex = "2147483647";
    btn.style.padding = "10px 14px";
    btn.style.background = "#1677ff";
    btn.style.color = "#fff";
    btn.style.border = "none";
    btn.style.borderRadius = "8px";
    btn.style.cursor = "pointer";
    btn.style.fontSize = "14px";
    btn.style.boxShadow = "0 2px 8px rgba(0,0,0,.25)";
    btn.onclick = () => {
      localStorage.setItem(KEY, "1");
      btn.innerText = "已确认，正在保存...";
    };
    document.body.appendChild(btn);
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createBtn);
  } else {
    createBtn();
  }
})();
"""


async def _ensure_playwright():
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "需要安装 playwright 才能捕获登录态，请运行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e
    return async_playwright


async def _wait_enter() -> str:
    await asyncio.to_thread(input, "登录完成后按回车确认保存 storageState...\n")
    return "enter"


async def _wait_button(context) -> str:
    key = "__mvd_login_done__"
    while True:
        for page in context.pages:
            try:
                done = await page.evaluate(
                    "(k) => window.localStorage && window.localStorage.getItem(k) === '1'",
                    key,
                )
                if done:
                    return "button"
            except Exception:
                # 页面跨域/跳转过程中的瞬态错误，忽略继续轮询。
                pass
        await asyncio.sleep(0.5)


async def capture_login_storage_state(
    platform: str,
    output_file: str,
    confirm_mode: ConfirmMode = "either",
    browser_type: BrowserType = "auto",
) -> Path:
    """捕获登录态并写入 storageState JSON。"""
    if platform not in HOME_URLS:
        raise ValueError(f"不支持的平台: {platform}")

    def _detect_default_browser() -> Optional[BrowserType]:
        """
        读取 Windows 默认浏览器（通过 http 的 ProgId）。

        返回：
        - 'firefox' / 'chromium'（即 Edge/Chrome） / None（兜底）
        """
        try:
            import winreg  # type: ignore

            key_path = (
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]  # type: ignore[index]
            lowered = str(prog_id).lower()
            if "firefox" in lowered:
                return "firefox"
            if "microsoftedge" in lowered or "edge" in lowered or "chrome" in lowered:
                # edge/chrome 都走 chromium 引擎 + 指定 channel
                return "chromium"
            return None
        except Exception:
            return None

    def _detect_chromium_channel() -> Optional[str]:
        """
        在默认浏览器是 Edge/Chrome 时，返回 playwright channel: 'msedge'|'chrome'
        """
        try:
            import winreg  # type: ignore

            key_path = (
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]  # type: ignore[index]
            lowered = str(prog_id).lower()
            if "microsoftedge" in lowered or "msedge" in lowered or "edge" in lowered:
                return "msedge"
            if "chrome" in lowered:
                return "chrome"
            return None
        except Exception:
            return None

    async_playwright = await _ensure_playwright()
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        resolved_browser_type = browser_type
        if browser_type == "auto":
            detected = _detect_default_browser()
            resolved_browser_type = detected or "chromium"

        if resolved_browser_type == "chromium":
            channel = _detect_chromium_channel()
            # 用 channel 打开“已安装的 Edge/Chrome”，实现更接近系统默认浏览器的体验。
            if channel:
                browser = await p.chromium.launch(headless=False, channel=channel)
            else:
                browser = await p.chromium.launch(headless=False)
        elif resolved_browser_type == "firefox":
            browser = await p.firefox.launch(headless=False)
        elif resolved_browser_type == "webkit":
            browser = await p.webkit.launch(headless=False)
        else:
            raise ValueError(f"不支持的浏览器类型: {browser_type}")

        try:
            context = await browser.new_context()
            await context.add_init_script(_BUTTON_INIT_SCRIPT)
            page = await context.new_page()
            await page.goto(HOME_URLS[platform], wait_until="domcontentloaded")

            tasks = []
            if confirm_mode in {"enter", "either"}:
                tasks.append(asyncio.create_task(_wait_enter()))
            if confirm_mode in {"button", "either"}:
                tasks.append(asyncio.create_task(_wait_button(context)))

            if not tasks:
                raise ValueError("confirm_mode 必须是 enter|button|either")

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

            trigger = list(done)[0].result()
            state = await context.storage_state()
            output_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"登录态已保存: {output_path} (确认方式: {trigger})")
            return output_path
        finally:
            await browser.close()
