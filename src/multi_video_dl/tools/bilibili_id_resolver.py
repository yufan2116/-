"""Bilibili 输入解析器（BV/av/纯数字 -> 统一 bvid 并拼下载链接）"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import httpx


BV_RE = re.compile(r"^BV[0-9A-Za-z]+$", re.IGNORECASE)
AV_RE = re.compile(r"^av(\d+)$", re.IGNORECASE)
NUM_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class BilibiliResolved:
    bvid: str
    aid: str
    video_url: str
    title: str
    uploader: str
    pages: List[str]


async def resolve_bilibili_input_to_url(user_input: str) -> Optional[BilibiliResolved]:
    """
    如果 user_input 是 BV/av/纯数字，则请求 bilibili view API 并返回解析结果。
    否则返回 None。
    """
    raw = (user_input or "").strip()
    if not raw:
        return None

    bvid: Optional[str] = None
    aid: Optional[str] = None

    if BV_RE.match(raw):
        # BV 大小写对编码是敏感的：不要把整串强制 upper
        # 仅标准化前缀 BV，其余字符保持原样，避免变成另一个 bvid。
        bvid = "BV" + raw[2:]
    else:
        m = AV_RE.match(raw)
        if m:
            aid = m.group(1)
        elif NUM_RE.match(raw):
            aid = raw
        else:
            return None

    url = None
    if bvid:
        url = "https://api.bilibili.com/x/web-interface/view"
        params = {"bvid": bvid}
    else:
        url = "https://api.bilibili.com/x/web-interface/view"
        params = {"aid": aid}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        payload = resp.json()

    if payload.get("code") not in (0, None):
        raise RuntimeError(f"Bilibili API error: {payload.get('message') or payload.get('code')}")

    data = payload.get("data") or {}
    # API 返回的 bvid 才是最终标准 bvid；如果缺失则回退到输入值（不强制 upper）。
    resolved_bvid = str(data.get("bvid") or bvid or "").strip()
    if not resolved_bvid:
        raise RuntimeError("Bilibili API: missing bvid in response data")
    resolved_aid = str(data.get("aid") or aid)
    title = str(data.get("title") or "")
    uploader = str((data.get("owner") or {}).get("name") or "")

    pages: List[str] = []
    for p in data.get("pages") or []:
        part = p.get("part")
        if part:
            pages.append(str(part))

    video_url = f"https://www.bilibili.com/video/{resolved_bvid}"
    return BilibiliResolved(
        bvid=resolved_bvid,
        aid=resolved_aid,
        video_url=video_url,
        title=title,
        uploader=uploader,
        pages=pages,
    )

