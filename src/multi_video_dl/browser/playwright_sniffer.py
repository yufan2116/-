"""Playwright 网络嗅探器

使用 headless Chromium + Playwright 抓取抖音 / 小红书等需要浏览器环境的平台视频直链，
并转换为统一的 ``MediaInfo`` / ``MediaItem`` 模型，方便直接交给 Pipeline 处理。

特性：
    - 基于 ``playwright.async_api`` 的异步实现
    - 通过 ``page.on('response')`` 嗅探网络请求，匹配 ``.mp4`` / ``aweme`` 等关键 URL
    - 优先选择无水印链接（例如 ``aweme.snssdk.com`` 的直链播放地址）
    - 支持注入 Playwright 的 ``storage_state`` JSON（通过 ``DownloadContext.cookies`` 指定路径）

用法示例：
    from multi_video_dl.browser.playwright_sniffer import sniff_douyin_with_playwright

    media_info = await sniff_douyin_with_playwright(url, ctx)

注意：
    - 需要先安装 playwright 以及 Chromium：
        pip install playwright
        playwright install chromium
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from ..core.models import Backend, DownloadContext, MediaInfo, MediaItem, MediaType

logger = logging.getLogger(__name__)


@dataclass
class SniffedSource:
    """嗅探到的媒体源"""

    url: str
    content_type: Optional[str] = None


async def _ensure_playwright():
    """动态导入 playwright.async_api，未安装时给出明确错误。"""
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError as e:  # pragma: no cover - 仅在未安装 playwright 时触发
        raise RuntimeError(
            "需要安装 playwright 才能使用浏览器嗅探功能，请运行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from e
    return async_playwright


async def _sniff_with_chromium(
    url: str,
    ctx: DownloadContext,
    match_fn,
    prefer_no_watermark_fn,
    platform: str,
) -> MediaInfo:
    """通用的 Chromium 嗅探逻辑，返回统一的 MediaInfo。"""
    async_playwright = await _ensure_playwright()

    sniffed: List[SniffedSource] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 支持通过 DownloadContext.cookies 传入 Playwright storage_state.json
        storage_state = None
        if ctx.cookies and ctx.cookies.endswith(".json"):
            storage_state = ctx.cookies

        if storage_state:
            context = await browser.new_context(storage_state=storage_state)
        else:
            context = await browser.new_context()

        page = await context.new_page()

        def _on_response(response):
            try:
                r_url = response.url
                if not match_fn(r_url):
                    return
                ctype = None
                try:
                    ctype = response.headers.get("content-type")
                except Exception:  # pragma: no cover - headers 访问异常时忽略
                    pass
                sniffed.append(SniffedSource(url=r_url, content_type=ctype))
            except Exception as e:  # pragma: no cover - 回调内部出错不应中断主流程
                logger.debug("Error in response handler: %s", e)

        page.on("response", _on_response)

        await page.goto(url, wait_until="networkidle")
        # 再额外等待一小段时间，给懒加载/自动播放的请求一些时间
        await page.wait_for_timeout(3000)

        await context.close()
        await browser.close()

    if not sniffed:
        # 未嗅探到任何候选，返回一个占位 MediaInfo，让上层做 graceful 处理
        return MediaInfo(
            platform=platform,
            id=_extract_video_id(url, platform) or "unknown",
            title="未知标题",
            author="未知作者",
            publish_time=None,
            tags=[],
            source_url=url,
            items=[],
            description=None,
            duration=None,
            thumbnail=None,
            extra={"sniffer": "playwright", "message": "no candidates sniffed"},
        )

    # 选择最佳候选 URL（按“无水印优先”等规则）
    best = prefer_no_watermark_fn(sniffed)

    item = MediaItem(
        direct_url=best.url,
        manifest_url=None,
        ext="mp4",
        headers={},  # 如需带 Cookie，可在 Pipeline 中注入 headers
        quality=None,
        height=None,
        width=None,
        filesize=None,
        type=MediaType.VIDEO,
        backend=Backend.HTTPX,
        extra={
            "source_url": url,
            "sniffer": "playwright",
            "content_type": best.content_type,
        },
    )

    return MediaInfo(
        platform=platform,
        id=_extract_video_id(url, platform) or "unknown",
        title="未知标题",
        author="未知作者",
        publish_time=None,
        tags=[],
        source_url=url,
        items=[item],
        description=None,
        duration=None,
        thumbnail=None,
        extra={"sniffer": "playwright"},
    )


def _extract_video_id(url: str, platform: str) -> Optional[str]:
    """从 URL 中提取一个尽量稳定的 ID（简化实现）。"""
    if platform == "douyin":
        # 常见形式：.../video/<id>/
        m = re.search(r"/video/(\d+)", url)
        if m:
            return m.group(1)
    if platform in {"xiaohongshu", "xhs"}:
        # 常见形式：/explore/<id>
        m = re.search(r"/explore/([0-9A-Za-z]+)", url)
        if m:
            return m.group(1)
    return None


def _douyin_match(url: str) -> bool:
    """抖音: 关注 .mp4 以及 aweme/snssdk 相关的播放链接。"""
    lowered = url.lower()
    if ".mp4" in lowered:
        return True
    if "aweme" in lowered and "snssdk.com" in lowered:
        return True
    return False


def _douyin_prefer(sources: List[SniffedSource]) -> SniffedSource:
    """抖音: 优先无水印 aweme 播放地址，其次普通 mp4。"""
    # 1. aweme.snssdk.com/play 且不含 watermark=1
    for s in sources:
        u = s.url.lower()
        if "aweme.snssdk.com" in u and "/play" in u and "watermark=" not in u:
            return s
    # 2. 其他不带 watermark 的 mp4
    for s in sources:
        u = s.url.lower()
        if ".mp4" in u and "watermark=" not in u:
            return s
    # 3. 回退：第一个候选
    return sources[0]


def _xhs_match(url: str) -> bool:
    """小红书: 关注直链 mp4 / 常见视频 CDN 域名。"""
    lowered = url.lower()
    if ".mp4" in lowered:
        return True
    # 常见小红书视频 CDN 域名关键字（简化）
    if "xhscdn.com" in lowered or "xiaohongshu.com" in lowered:
        return True
    return False


def _xhs_prefer(sources: List[SniffedSource]) -> SniffedSource:
    """小红书: 优先明显的视频直链 mp4。"""
    for s in sources:
        u = s.url.lower()
        if ".mp4" in u:
            return s
    return sources[0]


async def sniff_douyin_with_playwright(url: str, ctx: DownloadContext) -> MediaInfo:
    """使用 Playwright + Chromium 嗅探抖音视频直链，并返回统一 MediaInfo。"""
    return await _sniff_with_chromium(
        url=url,
        ctx=ctx,
        match_fn=_douyin_match,
        prefer_no_watermark_fn=_douyin_prefer,
        platform="douyin",
    )


async def sniff_xhs_with_playwright(url: str, ctx: DownloadContext) -> MediaInfo:
    """使用 Playwright + Chromium 嗅探小红书视频直链，并返回统一 MediaInfo。"""
    return await _sniff_with_chromium(
        url=url,
        ctx=ctx,
        match_fn=_xhs_match,
        prefer_no_watermark_fn=_xhs_prefer,
        platform="xiaohongshu",
    )
