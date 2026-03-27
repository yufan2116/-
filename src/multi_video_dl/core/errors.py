"""自定义异常类和错误阶段标记.

目标：
- 为常见失败场景定义具名异常类型
- 在异常中携带「阶段」与「上下文」，方便 CLI 统一展示人类可读的报错信息
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ErrorStage(str, Enum):
    """错误发生阶段（用于分类展示）"""

    EXTRACT = "extract"      # 解析 / 抓取
    SELECT = "select"        # 媒体项选择
    PREPARE = "prepare"      # 下载前的准备工作（构建 URL、headers 等）
    DOWNLOAD = "download"    # 实际下载过程
    STORE = "store"          # 保存文件 / 元数据
    PIPELINE = "pipeline"    # 管道调度流程
    DEPENDENCY = "dependency"  # 依赖/环境检查
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """异常的结构化上下文信息"""

    url: Optional[str] = None
    platform: Optional[str] = None
    backend: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class MultiVideoDLError(Exception):
    """基础异常类，带错误阶段和上下文"""

    def __init__(
        self,
        message: str = "",
        *args: Any,
        stage: Optional[ErrorStage] = None,
        code: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, *args)
        self.message = message or self.__class__.__doc__ or ""
        self.stage: ErrorStage = stage or ErrorStage.UNKNOWN
        self.code: str = code or self.__class__.__name__.upper()
        self.context: ErrorContext = context or ErrorContext()

    def to_readable(self) -> str:
        """返回适合直接展示在终端的、人类可读的错误说明"""
        stage_cn = {
            ErrorStage.EXTRACT: "解析阶段",
            ErrorStage.SELECT: "选择阶段",
            ErrorStage.PREPARE: "准备阶段",
            ErrorStage.DOWNLOAD: "下载阶段",
            ErrorStage.STORE: "保存阶段",
            ErrorStage.PIPELINE: "处理管道",
            ErrorStage.DEPENDENCY: "依赖检查",
            ErrorStage.UNKNOWN: "未知阶段",
        }.get(self.stage, "未知阶段")

        base = f"[{stage_cn}] {self.message}"

        parts = []
        if self.context.url:
            parts.append(f"URL={self.context.url}")
        if self.context.platform:
            parts.append(f"平台={self.context.platform}")
        if self.context.backend:
            parts.append(f"后端={self.context.backend}")
        if self.context.extra:
            # 只展示轻量的 key=value，避免过长
            extras = ", ".join(f"{k}={v}" for k, v in self.context.extra.items())
            parts.append(extras)

        if parts:
            return f"{base}（{'; '.join(parts)}）"
        return base

    def __str__(self) -> str:  # noqa: D401 - 用于友好展示
        return self.to_readable()


class ExtractorError(MultiVideoDLError):
    """Extractor 相关错误"""


class DownloaderError(MultiVideoDLError):
    """下载器相关错误"""


class StoreError(MultiVideoDLError):
    """存储相关错误"""


class PlatformNotSupportedError(ExtractorError):
    """平台不支持"""


class FFmpegNotFoundError(DownloaderError):
    """FFmpeg 未找到"""


class YtDlpNotFoundError(DownloaderError):
    """yt-dlp 未安装"""


class ParseError(ExtractorError):
    """解析错误"""


class DownloadError(DownloaderError):
    """下载失败"""
