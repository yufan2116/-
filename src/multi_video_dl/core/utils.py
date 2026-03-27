"""工具函数"""

import json
import re
import shutil
import subprocess
import sys
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Optional, Dict, Tuple, Any

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller 运行时：资源会被解压到 _MEIPASS 目录下
    _PROJECT_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOCAL_FFMPEG_BIN = _PROJECT_ROOT / "ffmpeg" / "bin"
_LOCAL_FFMPEG_EXE = _LOCAL_FFMPEG_BIN / "ffmpeg.exe"


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """清理文件名，移除非法字符并限制长度"""
    # Windows 非法字符
    illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
    filename = re.sub(illegal_chars, "_", filename)
    
    # 移除前后空格和点
    filename = filename.strip(" .")
    
    # 限制长度
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    # 确保不为空
    if not filename:
        filename = "untitled"
    
    return filename


def format_date(dt, fmt: str = "%Y%m%d") -> str:
    """格式化日期"""
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime(fmt)


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用"""
    return shutil.which("ffmpeg") is not None or _LOCAL_FFMPEG_EXE.exists()


def check_ytdlp() -> bool:
    """检查 yt-dlp 是否可用"""
    try:
        import yt_dlp
        return True
    except ImportError:
        return False


def get_ffmpeg_path() -> Optional[str]:
    """获取 ffmpeg 可执行文件路径"""
    return shutil.which("ffmpeg") or (str(_LOCAL_FFMPEG_EXE) if _LOCAL_FFMPEG_EXE.exists() else None)


def read_urls_file(filepath: str) -> list[str]:
    """从文件读取 URL 列表（忽略空行和注释）"""
    urls = []
    path = Path(filepath)
    if not path.exists():
        return urls
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 忽略空行和以 # 开头的注释
            if line and not line.startswith("#"):
                urls.append(line)
    
    return urls


def load_cookies_file(cookies_file: str) -> Dict[str, str]:
    """
    从 Netscape 格式的 cookies.txt 文件加载 cookies
    
    Args:
        cookies_file: cookies 文件路径
        
    Returns:
        cookies 字典，格式为 {name: value}
    """
    cookies_dict: Dict[str, str] = {}
    path = Path(cookies_file)
    
    if not path.exists():
        return cookies_dict
    
    try:
        # 使用 MozillaCookieJar 读取 Netscape 格式
        jar = MozillaCookieJar(cookies_file)
        jar.load(ignore_discard=True, ignore_expires=True)
        
        # 转换为字典
        for cookie in jar:
            cookies_dict[cookie.name] = cookie.value
            
    except Exception as e:
        # 如果 MozillaCookieJar 失败，尝试手动解析 Netscape 格式
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Netscape 格式：每行以制表符分隔
                    # 格式：domain\tflag\tpath\tsecure\texpiration\tname\tvalue
                    if line and not line.startswith("#"):
                        parts = line.split("\t")
                        if len(parts) >= 7:
                            name = parts[5]
                            value = parts[6]
                            cookies_dict[name] = value
        except Exception:
            # 如果都失败了，返回空字典
            pass
    
    return cookies_dict


def cookies_to_header(cookies_dict: Dict[str, str]) -> str:
    """
    将 cookies 字典转换为 HTTP Cookie 头字符串
    
    Args:
        cookies_dict: cookies 字典，格式为 {name: value}
        
    Returns:
        Cookie 头字符串，格式为 "name1=value1; name2=value2"
    """
    if not cookies_dict:
        return ""
    
    cookie_pairs = [f"{name}={value}" for name, value in cookies_dict.items()]
    return "; ".join(cookie_pairs)


_STORAGE_STATE_CONVERT_CACHE: Dict[str, Tuple[float, str]] = {}


def storage_state_to_netscape_cookies(
    storage_state_file: str,
    output_file: Optional[str] = None,
) -> str:
    """
    将 Playwright context.storage_state.json 转为 yt-dlp/HTTP 需要的 Netscape cookies.txt。
    """
    src_path = Path(storage_state_file)
    if not src_path.exists():
        raise FileNotFoundError(f"storageState 文件不存在: {src_path}")

    mtime = src_path.stat().st_mtime
    cache_key = str(src_path)
    cached = _STORAGE_STATE_CONVERT_CACHE.get(cache_key)
    if cached:
        cached_mtime, cached_path = cached
        if cached_mtime == mtime and Path(cached_path).exists():
            return cached_path

    if output_file is None:
        # storage_state.json -> storage_state.cookies.txt
        output_path = src_path.with_suffix(".cookies.txt")
    else:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    raw = src_path.read_text(encoding="utf-8")
    data: Dict[str, Any] = json.loads(raw)
    cookies = data.get("cookies") or []

    lines = [
        "# Netscape HTTP Cookie File",
        "# This file was generated by multi_video_dl from Playwright storageState",
        "# domain\tflag\tpath\tsecure\texpiration\tname\tvalue",
    ]

    def _yn(v: bool) -> str:
        return "TRUE" if v else "FALSE"

    for c in cookies:
        try:
            domain = (c.get("domain") or "").strip()
            name = (c.get("name") or "").strip()
            value = c.get("value", "")
            if not domain or not name:
                continue

            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = (c.get("path") or "/").strip() or "/"
            secure = bool(c.get("secure", False))
            expires = c.get("expires")
            if expires is None or expires == -1:
                expiration = "0"
            else:
                expiration = str(int(expires))

            value_str = str(value).replace("\t", " ").replace("\n", " ").replace("\r", " ")
            lines.append(
                "\t".join(
                    [
                        domain,
                        flag,
                        path,
                        _yn(secure),
                        expiration,
                        name,
                        value_str,
                    ]
                )
            )
        except Exception:
            continue

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _STORAGE_STATE_CONVERT_CACHE[cache_key] = (mtime, str(output_path))
    return str(output_path)


def normalize_cookies_for_yt_dlp(cookies_file: Optional[str]) -> Optional[str]:
    """
    将 ctx.cookies 统一归一为 yt-dlp 能用的 cookiefile（Netscape cookies.txt）。
    """
    if not cookies_file:
        return None
    p = Path(cookies_file)
    if p.suffix.lower() == ".json":
        return storage_state_to_netscape_cookies(str(p))
    return str(p)


def get_bilibili_quality_warning(quality: str, has_cookies: bool) -> str | None:
    """返回 Bilibili 清晰度相关警告；None 表示无警告。"""
    if quality in ("highest", "1080p", "4k"):
        if not has_cookies:
            return (
                "⚠️ 高清（1080p+）通常需要大会员 + cookies。\n"
                "建议使用 --cookies 或登录按钮获取。"
            )
    return None
