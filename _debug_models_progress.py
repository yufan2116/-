from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
s=p.read_text(encoding="utf-8", errors="replace")
lines=s.splitlines(keepends=True)
for i,line in enumerate(lines):
    if "progress_callback" in line:
        print("progress_callback at index", i)
        print(line.rstrip())
