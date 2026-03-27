from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from datetime import datetime

import httpx

from yt_dlp import YoutubeDL

from ..core.utils import check_ffmpeg, get_ffmpeg_path, normalize_cookies_for_yt_dlp


_BILIBILI_VIDEO_RE = re.compile(r"^https?://(www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)", re.I)


def is_bilibili_video_url(url: str) -> bool:
    return bool(_BILIBILI_VIDEO_RE.match(url or ""))


def is_bilibili_playlist_url(url: str) -> bool:
    """
    判断是否为 Bilibili 的“合集/playlist”页面（不依赖 /video/BV...）。
    主要覆盖：
    - 收藏夹：/space.bilibili.com/{uid}/favlist?...（需要 cookies）
    - 其他常见 playlist 入口：/video/BV.../?...（yt-dlp 通常也能当 playlist）
    """
    u = url or ""
    lower = u.lower()
    if "bilibili.com" not in lower:
        return False

    # 收藏夹（favlist）/ 剧集等通常会被 yt-dlp 当成 playlist
    if "favlist" in lower:
        return True

    # 兜底：视频页（BV/av）也可能存在“自动带合集”的情况
    if is_bilibili_video_url(u):
        return True

    # 可扩展：未来再加 series/bangumi/番剧等
    return False


def _template_to_yt_dlp_outtmpl(template: str) -> str:
    # 把 {author}/{title}/{id} 近似映射到 yt-dlp 的 %(uploader)s/%(title)s/%(id)s
    # 不做严格完整模板映射，保持尽量可用。
    out = template
    out = out.replace("{author}", "%(uploader)s")
    out = out.replace("{title}", "%(title)s")
    out = out.replace("{id}", "%(id)s")
    out = out.replace("{platform}", "bilibili")
    out = out.replace("{date}", "%(upload_date>%Y%m%d)s")
    # ext 由 yt-dlp 自动追加，不建议放到 outtmpl 里
    out = out.replace("{ext}", "%(ext)s")
    # 避免用户模板里包含路径分隔导致输出目录被破坏
    out = out.replace("/", "_").replace("\\", "_")
    return out


def _build_format_selector() -> str:
    # 兼顾清晰度与兼容性；playlist 场景下我们尽量别触发大会员/4K 专享。
    return "bestvideo[height<=1080]+bestaudio/best[height<=1080]"


def _resolve_cookies_for_yt_dlp(cookies: Optional[str]) -> Optional[str]:
    if not cookies:
        return None
    return normalize_cookies_for_yt_dlp(cookies)


@dataclass(frozen=True)
class PlaylistEntry:
    index: int
    title: str


def list_playlist_entries(
    url: str,
    cookies: Optional[str] = None,
) -> List[PlaylistEntry]:
    """
    使用 yt-dlp 列出 playlist 条目（用于 GUI 勾选）。
    """
    cookies_file = _resolve_cookies_for_yt_dlp(cookies)

    yt_dlp_path = Path(sys.executable).resolve().parent / "yt-dlp.exe"
    if not yt_dlp_path.exists():
        yt_dlp_path = Path(sys.executable).resolve().parent / "yt-dlp"
    if not yt_dlp_path.exists():
        raise RuntimeError("无法找到 venv 内的 yt-dlp 可执行文件")

    cmd = [
        str(yt_dlp_path),
        "--flat-playlist",
        "--skip-download",
        "--yes-playlist",
        "--no-warnings",
        "--print",
        # title 字段在部分收藏夹场景会返回 NA 或包含编码问题，
        # 用 url 保证字段稳定（保证 \t 分隔可解析）。
        "%(playlist_index)s\t%(url)s",
        url,
    ]
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])

    # 即便某些条目解析失败，也尽量不要中断整个“列表枚举”
    cmd.extend(["--ignore-errors"])

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        raise RuntimeError(err or "Failed to list playlist entries")

    results: List[PlaylistEntry] = []
    next_index = 1
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        idx_str = parts[0].strip()
        # parts[1] 是 %(url)s
        title = parts[1].strip()
        try:
            idx = int(idx_str)
        except Exception:
            idx = next_index
        results.append(PlaylistEntry(index=idx, title=title))
        next_index += 1

    return results


def download_bilibili_playlist_direct(
    *,
    url: str,
    output_dir: str,
    filename_template: str,
    cookies: Optional[str] = None,
    playlist_items: Optional[str] = None,
    noplaylist: bool = False,
    playlist_start: Optional[int] = None,
    playlist_end: Optional[int] = None,
    match_filter: Optional[str] = None,
    dateafter: Optional[str] = None,
    playlist_reverse: bool = False,
    dry_run: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> None:
    """
    直接用 yt-dlp 下载 playlist（跳过本项目 extractor/pipeline）。
    """
    # favlist 场景：yt-dlp 直接下载整个 playlist 可能触发 KeyError('bvid')，
    # 这里走稳定兜底：flat-playlist 枚举后逐条下载。
    if "favlist" in (url or "").lower():
        download_bilibili_favlist_stable_by_flat_entries(
            url=url,
            output_dir=output_dir,
            filename_template=filename_template,
            cookies=cookies,
            playlist_items=playlist_items,
            noplaylist=noplaylist,
            playlist_start=playlist_start,
            playlist_end=playlist_end,
            match_filter=match_filter,
            dateafter=dateafter,
            playlist_reverse=playlist_reverse,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )
        return

    cookies_file = _resolve_cookies_for_yt_dlp(cookies)

    outtmpl_base = str(Path(output_dir) / _template_to_yt_dlp_outtmpl(filename_template))
    outtmpl = outtmpl_base + ".%(ext)s"

    ffmpeg_ok = check_ffmpeg()
    format_selector = _build_format_selector()

    def _make_progress_hook(cb: Callable[[float, str], None]):
        def _hook(d: dict) -> None:
            try:
                downloaded = d.get("downloaded_bytes") or d.get("downloaded_bytes_estimate")
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total:
                    percent = float(downloaded) * 100.0 / float(total)
                    percent = max(0.0, min(100.0, percent))
                    cb(percent, str(d.get("status") or ""))
            except Exception:
                return

        return _hook

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": format_selector,
        # 有些平台会产出不带声音的文件；无 ffmpeg 时 yt-dlp 直接拆分即可继续。
        "no_merge": not ffmpeg_ok,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": bool(dry_run),
        "progress_hooks": [],
    }

    # yt-dlp 合并时需要从 PATH 找 ffmpeg；这里显式指定本地 ffmpeg 目录，避免“ffmpeg not installed”。
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        ffmpeg_dir = str(Path(ffmpeg_path).parent)
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    # playlist 控制：透传给 yt-dlp
    if playlist_items:
        ydl_opts["playlist_items"] = playlist_items
    if noplaylist:
        ydl_opts["noplaylist"] = True
    if playlist_start is not None:
        ydl_opts["playlist_start"] = int(playlist_start)
    if playlist_end is not None:
        ydl_opts["playlist_end"] = int(playlist_end)
    if match_filter:
        # yt-dlp 参数名是 match_filter，对应 --match-filter
        ydl_opts["match_filter"] = match_filter
    if dateafter:
        ydl_opts["dateafter"] = dateafter
    if playlist_reverse:
        ydl_opts["playlist_reverse"] = True

    if progress_callback:
        ydl_opts["progress_hooks"] = [_make_progress_hook(progress_callback)]

    # 直接下载
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def _parse_yyyymmdd(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), "%Y%m%d")
    except Exception:
        return None


def _extract_bv_or_av_id(video_url: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.search(r"/video/(BV[0-9a-zA-Z]+|av\d+)", video_url or "", re.I)
    if not m:
        return None, None
    vid = m.group(1)
    if vid.lower().startswith("bv"):
        return vid, None
    if vid.lower().startswith("av"):
        return None, vid[2:]
    return None, None


def _resolve_bilibili_title_pubdate_by_bvid(
    bvid: str, cookies: Optional[str]
) -> Tuple[Optional[str], Optional[int]]:
    # 使用同步 http 请求：避免让 playlist 工具变成 async
    url = "https://api.bilibili.com/x/web-interface/view"
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {"bvid": bvid}
    # cookiefile 用于 yt-dlp；这里用 httpx 不方便直接复用同格式 cookies，
    # 因此主要用于 match-filter/dateafter 的“尽力而为”过滤。
    with httpx.Client(timeout=30, headers=headers) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        title = data.get("title")
        pubdate = data.get("pubdate")
        pubdate_i = int(pubdate) if pubdate is not None else None
        return (str(title) if title else None, pubdate_i)


def download_bilibili_favlist_stable_by_flat_entries(
    *,
    url: str,
    output_dir: str,
    filename_template: str,
    cookies: Optional[str] = None,
    playlist_items: Optional[str] = None,
    noplaylist: bool = False,
    playlist_start: Optional[int] = None,
    playlist_end: Optional[int] = None,
    match_filter: Optional[str] = None,
    dateafter: Optional[str] = None,
    playlist_reverse: bool = False,
    dry_run: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> None:
    """
    favlist 兜底：先 flat-playlist 枚举条目，再逐个下载，绕开 yt-dlp playlist KeyError('bvid')。
    """
    cookies_file = _resolve_cookies_for_yt_dlp(cookies)

    yt_dlp_path = Path(sys.executable).resolve().parent / "yt-dlp.exe"
    if not yt_dlp_path.exists():
        yt_dlp_path = Path(sys.executable).resolve().parent / "yt-dlp"
    if not yt_dlp_path.exists():
        raise RuntimeError("无法找到 venv 内的 yt-dlp 可执行文件")

    cmd = [
        str(yt_dlp_path),
        "--yes-playlist",
        "--flat-playlist",
        "--skip-download",
        "--no-warnings",
        "--print",
        "%(playlist_index)s\t%(url)s",
        url,
    ]
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip() or "Failed to enumerate favlist entries")

    # 解析条目
    entries: List[Tuple[int, str]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            idx = int(parts[0].strip())
        except Exception:
            continue
        page_url = parts[1].strip()
        if page_url:
            entries.append((idx, page_url))

    if not entries:
        return

    # 筛选 indices
    indices = [i for i, _ in entries]
    selected = set(indices)

    if playlist_items and str(playlist_items).strip().upper() != "ALL":
        from .bilibili_playlist_utils import parse_playlist_items

        selected = set(parse_playlist_items(str(playlist_items)))

    if playlist_start is not None:
        selected = {i for i in selected if i >= int(playlist_start)}
    if playlist_end is not None:
        selected = {i for i in selected if i <= int(playlist_end)}

    selected_list = [i for i in indices if i in selected]
    if not selected_list:
        return

    if playlist_reverse:
        selected_list = list(reversed(selected_list))

    if noplaylist:
        # 在收藏夹场景，“只下载当前”无法明确对应哪一项，这里取筛选后的第一项
        selected_list = [selected_list[0]]

    # title/date 过滤：尽力而为（需要调用 view API）
    title_kw: Optional[str] = None
    if match_filter:
        # 只支持 title*=关键词
        m = re.search(r"title\*=(.+)$", match_filter.strip(), re.I)
        if m:
            title_kw = m.group(1).strip()

    date_after_dt = _parse_yyyymmdd(dateafter) if dateafter else None

    if title_kw or date_after_dt:
        filtered_list: List[int] = []
        for idx in selected_list:
            video_url = next(u for i, u in entries if i == idx)
            bvid, _aid = _extract_bv_or_av_id(video_url)
            if not bvid:
                filtered_list.append(idx)
                continue
            title, pubdate_i = _resolve_bilibili_title_pubdate_by_bvid(bvid, cookies_file)
            ok = True
            if title_kw and title:
                if title_kw not in title:
                    ok = False
            if date_after_dt and pubdate_i is not None:
                pub_dt = datetime.fromtimestamp(pubdate_i)
                if pub_dt < date_after_dt:
                    ok = False
            if ok:
                filtered_list.append(idx)
        selected_list = filtered_list
        if not selected_list:
            return

    # 下载每个条目
    outtmpl = str(Path(output_dir) / _template_to_yt_dlp_outtmpl(filename_template)) + ".%(ext)s"
    ffmpeg_ok = check_ffmpeg()
    format_selector = _build_format_selector()

    def _make_progress_hook(cb: Callable[[float, str], None]):
        def _hook(d: dict) -> None:
            try:
                downloaded = d.get("downloaded_bytes") or d.get("downloaded_bytes_estimate")
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total:
                    percent = float(downloaded) * 100.0 / float(total)
                    percent = max(0.0, min(100.0, percent))
                    cb(percent, str(d.get("status") or ""))
            except Exception:
                return

        return _hook

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": format_selector,
        "no_merge": not ffmpeg_ok,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": bool(dry_run),
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    if progress_callback:
        ydl_opts["progress_hooks"] = [_make_progress_hook(progress_callback)]
    
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

    with YoutubeDL(ydl_opts) as ydl:
        for idx in selected_list:
            video_url = next(u for i, u in entries if i == idx)
            try:
                ydl.download([video_url])
            except Exception:
                # 单条失败跳过，保证整个合集尽量不中断
                continue

