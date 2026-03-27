"""数据模型定义"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field, field_validator


class MediaType(str, Enum):
    """媒体类型"""
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"


class Backend(str, Enum):
    """下载后端"""
    AUTO = "auto"
    HTTPX = "httpx"
    FFMPEG = "ffmpeg"
    YTDLP = "ytdlp"


class MediaItem(BaseModel):
    """媒体项（单个视频/音频/图片）"""
    direct_url: Optional[str] = Field(None, description="直接下载链接")
    manifest_url: Optional[str] = Field(None, description="清单文件链接（如 m3u8）")
    ext: str = Field(..., description="文件扩展名（如 mp4, m3u8）")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    quality: Optional[str] = Field(None, description="质量标识（如 1080p, 720p）")
    height: Optional[int] = Field(None, description="视频高度（像素）")
    width: Optional[int] = Field(None, description="视频宽度（像素）")
    filesize: Optional[int] = Field(None, description="文件大小（字节）")
    type: MediaType = Field(MediaType.VIDEO, description="媒体类型")
    backend: Optional[Backend] = Field(None, description="推荐使用的后端")
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外信息")

    @field_validator("direct_url", "manifest_url", mode="before")
    @classmethod
    def validate_url(cls, v):
        if v is None:
            return None
        if not isinstance(v, str) or not v.strip():
            return None
        return v.strip()

    def has_url(self) -> bool:
        """检查是否有可用的 URL"""
        return bool(self.direct_url or self.manifest_url)


class MediaInfo(BaseModel):
    """媒体信息（统一 schema）"""
    platform: str = Field(..., description="平台名称")
    id: str = Field(..., description="视频ID")
    title: str = Field(..., description="标题")
    author: str = Field(..., description="作者/UP主")
    publish_time: Optional[datetime] = Field(None, description="发布时间")
    tags: List[str] = Field(default_factory=list, description="标签")
    source_url: str = Field(..., description="源URL")
    items: List[MediaItem] = Field(default_factory=list, description="媒体项列表")
    description: Optional[str] = Field(None, description="描述")
    duration: Optional[float] = Field(None, description="时长（秒）")
    thumbnail: Optional[str] = Field(None, description="缩略图URL")
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外信息")

    def get_best_item(self, prefer_no_watermark: bool = True) -> Optional[MediaItem]:
        """获取最佳质量的媒体项"""
        if not self.items:
            return None
        
        # 优先选择视频
        video_items = [item for item in self.items if item.type == MediaType.VIDEO]
        if not video_items:
            video_items = self.items
        
        # 按质量排序（优先按 height，其次按 quality 字符串）
        def sort_key(item: MediaItem) -> tuple:
            height = item.height or 0
            quality_str = item.quality or ""
            # 简单的质量字符串排序（1080p > 720p > 480p）
            quality_order = {"1080p": 3, "720p": 2, "480p": 1, "360p": 0}.get(quality_str.lower(), -1)
            return (height, quality_order)
        
        sorted_items = sorted(video_items, key=sort_key, reverse=True)
        return sorted_items[0] if sorted_items else None


class DownloadContext(BaseModel):
    """下载上下文"""
    output_dir: str = Field(..., description="输出目录")
    template: str = Field("{title}", description="文件名模板")
    meta_mode: str = Field("json", description="元数据模式：json|filename|both")
    cookies: Optional[str] = Field(None, description="Cookies 文件路径")
    quality: str = Field("highest", description="目标清晰度：highest|1080p|720p|480p|360p|low")
    backend: Backend = Field(Backend.AUTO, description="下载后端")
    dry_run: bool = Field(False, description="仅预览，不下载")
    verbose: bool = Field(False, description="详细日志")
    prefer_no_watermark: bool = Field(True, description="优先无水印")
    # GUI/前端用：在下载线程里回传进度，交由 UI 线程展示。
    # 该字段不参与序列化/落盘。
    progress_callback: Optional[Callable[[float, str], None]] = Field(
        None, description="进度回调(0-100, status)", exclude=True
    )