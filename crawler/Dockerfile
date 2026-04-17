FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（Playwright 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（仅 Chromium）
RUN playwright install chromium --with-deps || true

COPY . .

CMD ["python", "main.py"]