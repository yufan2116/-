# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 及 Chromium（用于浏览器嗅探器）
RUN pip install --no-cache-dir playwright && \
    python -m playwright install --with-deps chromium

# 复制项目文件
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# 安装 Python 依赖和项目
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# 创建下载目录
RUN mkdir -p /downloads

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV MVD_OUTPUT_DIR=/downloads

# 设置默认输出目录
VOLUME ["/downloads"]

# 入口点
ENTRYPOINT ["mvd"]

# 默认命令（显示帮助）
CMD ["--help"]
