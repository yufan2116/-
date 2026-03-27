from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def parse_playlist_items(playlist_items: str) -> List[int]:
    """
    解析 yt-dlp -I/--playlist-items 类似的输入：
      - "1" -> [1]
      - "1,3-5" -> [1,3,4,5]
    返回 1-based 的页码列表，去重并排序。
    """
    s = (playlist_items or "").strip()
    if not s:
        raise ValueError("playlist_items 不能为空")

    if s.upper() == "ALL":
        raise ValueError("ALL 需要由调用方处理（通常表示下载全部P）")

    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        raise ValueError("playlist_items 格式不正确")

    result = set()
    for p in parts:
        m = _RANGE_RE.match(p)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            if start <= 0 or end <= 0:
                raise ValueError(f"无效的分P范围: {p}")
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                result.add(i)
        else:
            if not p.isdigit():
                raise ValueError(f"无效的分P项: {p}")
            v = int(p)
            if v <= 0:
                raise ValueError(f"无效的分P序号: {v}")
            result.add(v)

    return sorted(result)


def _set_bilibili_p_param(url: str, p_value: int) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["p"] = [str(p_value)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def _remove_bilibili_p_param(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("p", None)
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def expand_bilibili_playlist_urls(
    url: str,
    playlist_items: Optional[str],
    only_current_p: bool,
) -> List[str]:
    """
    把 bilibili 单一视频 URL 扩展为多个 `?p=` 页面 URL。

    规则：
    - 如果只有当前P：确保 url 有 p=1（或保留原有 p）
    - 如果 playlist_items 是 None/空/ALL：返回原 url（下载全部）
    - 否则将 url 去掉原 p 参数，然后按 items 生成 url?p=序号
    """
    u = (url or "").strip()
    if not u:
        return []

    # 只对 bilibili video 页面做 p 扩展（避免影响其它平台）
    if "bilibili.com/video/" not in u:
        return [u]

    if only_current_p:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "p" in qs and qs["p"]:
            return [u]
        return [_set_bilibili_p_param(u, 1)]

    if not playlist_items:
        return [u]
    if str(playlist_items).strip().upper() == "ALL":
        return [u]

    items = parse_playlist_items(str(playlist_items))
    base = _remove_bilibili_p_param(u)
    return [_set_bilibili_p_param(base, i) for i in items]

