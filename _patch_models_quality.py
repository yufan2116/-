from pathlib import Path
p=Path(r"D:\Download-tool\multi_video_dl\src\multi_video_dl\core\models.py")
s=p.read_text(encoding="utf-8")
if any("quality:" in line and "Field" in line for line in s.splitlines()):
    print("quality already exists")
    raise SystemExit(0)
lines=s.splitlines(keepends=True)
start=None
for i,line in enumerate(lines):
    if "progress_callback:" in line:
        start=i
        break
if start is None:
    raise SystemExit("progress_callback not found")
end=start
while end < len(lines) and lines[end].strip()!=")":
    end+=1
if end>=len(lines):
    raise SystemExit("could not find end of progress_callback field")
insert="\n    quality: str = Field(\"highest\", description=\"娓呮櫚搴﹂€夋嫨\")\n"
lines.insert(end+1, insert)
p.write_text("".join(lines), encoding="utf-8")
print("patched models.py")
