@echo off
chcp 65001 >nul

REM 激活虚拟环境（根据你的路径调整，如果改过位置）
cd /d D:\Download-tool
call .venv\Scripts\activate.bat

REM 切到项目目录（可选，仅用于确保当前工作目录在仓库内）
cd /d D:\Download-tool\multi_video_dl

REM 强制优先使用当前源码（避免加载到虚拟环境里的旧安装包）
set PYTHONPATH=D:\Download-tool\multi_video_dl\src;%PYTHONPATH%

REM 默认启动本地图形界面（Tkinter GUI）
REM 依赖于虚拟环境中已安装 multi_video_dl 包
python -m multi_video_dl.gui

