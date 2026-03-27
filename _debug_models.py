from pathlib import Path
p=Path(r"D:/Download-tool/multi_video_dl/src/multi_video_dl/core/models.py")
s=p.read_text(encoding="utf-8")
lines=s.splitlines(keepends=True)
cls_idx=None
for i,line in enumerate(lines):
    if "class DownloadContext" in line:
        cls_idx=i
        break
print("cls_idx",cls_idx)
if cls_idx is not None:
    for j in range(cls_idx, min(cls_idx+20, len(lines))):
        if "progress_callback" in lines[j]:
            print("found progress_callback line",j, lines[j])
            break
    else:
        print("not found within next 20 lines; first 5 lines in range:")
        for j in range(cls_idx, min(cls_idx+5,len(lines))):
            print(j, lines[j].rstrip())
