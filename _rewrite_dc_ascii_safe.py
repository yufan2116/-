from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
text=p.read_text(encoding="utf-8", errors="replace")
start=text.find("class DownloadContext(BaseModel):")
if start==-1:
    raise SystemExit("DownloadContext not found")
prefix=text[:start]

new_class='''class DownloadContext(BaseModel):
    """DownloadContext"""

    output_dir: str = Field(..., description="output_dir")
    template: str = Field("{title}", description="template")
    meta_mode: str = Field("json", description="meta_mode")
    cookies: Optional[str] = Field(None, description="cookies")
    backend: Backend = Field(Backend.AUTO, description="backend")
    dry_run: bool = Field(False, description="dry_run")
    verbose: bool = Field(False, description="verbose")
    prefer_no_watermark: bool = Field(True, description="prefer_no_watermark")

    # progress callback is used by GUI to update a progress bar.
    progress_callback: Optional[Callable[[float, str], None]] = Field(
        None, description="progress_callback", exclude=True
    )

    # quality selection: highest(default), 1080p/720p/480p/360p/low.
    quality: str = Field("highest", description="quality")
'''

# Ensure Callable is imported
if "from typing import Optional, List, Dict, Any, Callable" not in text:
    text=text.replace("from typing import Optional, List, Dict, Any", "from typing import Optional, List, Dict, Any, Callable")

# Keep file prefix up to class definition
text = text[:start] + new_class

p.write_text(text, encoding="utf-8")
print("rewrote DownloadContext (ASCII safe)")
