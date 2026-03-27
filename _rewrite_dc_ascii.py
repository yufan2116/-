from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
text=p.read_text(encoding="utf-8", errors="replace")
start=text.find("class DownloadContext(BaseModel):")
if start==-1:
    raise SystemExit("DownloadContext not found")
prefix=text[:start]
# ASCII-only class definition to avoid encoding-related quote corruption
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

# Ensure Callable import exists
if "Callable" not in text.split("\n",5)[0:20].__str__():
    # best-effort: update the typing import line
    text2=prefix+new_class

# Also ensure Callable is imported near top
# Replace typing import line if it exists
if "from typing import" in text:
    # Try a simple replace of the exact current pattern
    text=text.replace("from typing import Optional, List, Dict, Any", "from typing import Optional, List, Dict, Any, Callable")

# Rebuild file
text=prefix+new_class
p.write_text(text, encoding="utf-8')
print('rewrote DownloadContext (ASCII)')
