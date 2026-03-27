"""存储和元数据管理"""

import json
import logging
from pathlib import Path
from typing import Optional

from .models import MediaInfo, DownloadContext
from .utils import sanitize_filename, format_date

logger = logging.getLogger(__name__)


class Store:
    """文件存储和元数据管理"""
    
    def __init__(self, ctx: DownloadContext):
        self.ctx = ctx
        self.output_dir = Path(ctx.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_filename(
        self,
        media_info: MediaInfo,
        item_ext: str,
        item: Optional = None,
    ) -> Path:
        """根据模板生成文件名"""
        template = self.ctx.template
        
        # 准备变量
        vars_map = {
            "platform": media_info.platform,
            "author": sanitize_filename(media_info.author or "unknown"),
            "title": sanitize_filename(media_info.title or "untitled"),
            "id": media_info.id,
            "date": format_date(media_info.publish_time),
            "ext": item_ext.lstrip("."),
        }
        
        # 替换模板变量
        filename = template
        for key, value in vars_map.items():
            filename = filename.replace(f"{{{key}}}", str(value))
        
        # 清理文件名
        filename = sanitize_filename(filename)
        
        # 确保有扩展名
        if not Path(filename).suffix:
            filename = f"{filename}.{item_ext.lstrip('.')}"
        
        return self.output_dir / filename
    
    def save_metadata(self, media_info: MediaInfo, media_path: Path) -> Optional[Path]:
        """保存元数据"""
        if self.ctx.meta_mode in ["json", "both"]:
            metadata_path = media_path.with_suffix(".metadata.json")
            
            # 转换为可序列化的字典
            metadata_dict = media_info.model_dump(mode="json")
            # 处理 datetime
            publish_time = metadata_dict.get("publish_time")
            if publish_time:
                # model_dump(mode="json") 已把 datetime 转成字符串，这里兼容两种情况
                if hasattr(publish_time, "isoformat"):
                    metadata_dict["publish_time"] = publish_time.isoformat()
            
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved metadata to {metadata_path}")
            return metadata_path
        
        return None
    
    def get_output_path(self, media_info: MediaInfo, item) -> Path:
        """获取输出路径"""
        ext = item.ext.lstrip(".")
        if not ext:
            ext = "mp4"  # 默认扩展名
        
        return self.generate_filename(media_info, ext, item)
