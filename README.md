# 文档翻译器（本地模型版）

把 Word / Excel / PDF / 文本 丢进去，调用你机器上的 llama.cpp（默认 127.0.0.1:8080）翻译，下载译文。

## 能力

- 格式：.docx / .xlsx / .xlsm / .pdf（原生文字）/ .txt / .md
- 语言：源语言自动或指定，目标语言中/英/日/韩/法/德/西/俄
- 对话：流式输出、停止生成、附件（可一键转翻译）、历史会话
- 术语库：多库管理、术语增删、CSV 导入导出，按库应用到任务
- 任务：上传即返回任务号，后台排队执行，可看进度、取消、重试、下载
- 质量报告：单元数、缺失、数字/URL/占位符保留率，随结果下载
- 设置页：模型地址、采样、批预算、聊天上下文，保存即生效

## 前后端关系（开发与生产）

这是前后端分离的两个工程：

    frontend/   React + TypeScript + Vite，产物在 frontend/dist
    backend/    FastAPI，只提供 /api

开发模式（两个进程，改代码热更新）：

    # 终端 1：后端
    .venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env

    # 终端 2：前端（Vite 把 /api 代理到 127.0.0.1:8000）
    cd frontend
    npm install
    npm run dev -- --host 0.0.0.0

    浏览器打开 http://服务器IP:5173

生产模式，二选一：

    A. 前后端分离（推荐，和 Plan 一致）
       Caddy / Nginx 托管 frontend/dist，/api 反代到 127.0.0.1:8000
       参考 deploy/Caddyfile.example

    B. 单端口（省一个进程）
       只跑 FastAPI，由它托管 frontend/dist
       下面的部署步骤就是这种方式

Node.js 只在开发前端和构建 dist 时需要；生产用方式 A 或 B 都不需要 Node。

## 部署（Ubuntu 服务器）

1. 准备 Python 3.10+ 与项目目录：

        cd /opt
        git clone <this-repo> corefix
        cd corefix
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt

2. 配置：

        cp .env.example .env

3. 前端构建（仓库已带 frontend/dist，可跳过；改过前端才需要）：

   注意：这是单端口方式 B。若用 Caddy 托管静态文件（方式 A），
   第 4 步的 FastAPI 只需监听 127.0.0.1。

        cd frontend
        npm install
        npm run build
        cd ..

4. 启动：

        .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1 --env-file .env

   浏览器打开 http://服务器IP:8000

5. 开机自启：参考 deploy/corefix.service，放到 /etc/systemd/system/ 后

        systemctl daemon-reload
        systemctl enable --now corefix

6. 反代与 HTTPS（可选）：参考 deploy/Caddyfile.example

## 离线预览（不需要模型）

    MODEL_BACKEND=fake .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --env-file .env

假模型会回显你的消息，用于验证界面、流式输出、任务流程；翻译任务会输出带 [目标语言] 前缀的占位文本。

## 数据持久化

- 数据目录由 DATA_DIR 决定；相对路径按**代码目录**解析，不随启动位置变化
- 默认是代码目录下的 data/（含 app.db 与 storage/）
- 生产建议 DATA_DIR=/var/lib/corefix，并确保部署/升级时该目录不被覆盖
- 备份时连同 app.db 与 storage/ 一起备份
- 设置页底部会显示实际数据目录、数据库路径与记录数，可用来确认

## PDF 输出模式

默认 PDF_OUTPUT_MODE=overlay：在原 PDF 上擦除原文、原位写入译文。

- 保留图片、表格线、页眉页脚、分栏等版式
- 不依赖 LibreOffice
- 同一字号的文本会统一缩放，避免同一样式出现多种字号
- 译文过长时该字号组整体变小；极端情况仍可能溢出文本框
- 扫描件（图片型 PDF）没有可提取文字，不会被翻译

需要“重排成新 PDF”时改用 reflow：

    PDF_OUTPUT_MODE=reflow

reflow 会重建 DOCX 再调用 LibreOffice 转 PDF，需要：

    apt install libreoffice-writer fonts-noto-cjk
    # 可选
    SOFFICE_BIN=/usr/bin/soffice
    PDF_FONT_NAME=Noto Sans CJK SC

没装 LibreOffice 时，reflow 模式的 PDF 任务会以 pdf_converter_missing 失败，overlay 不受影响。

## 模型要求

注意：后台 Worker 跑在 API 进程内，必须使用 --workers 1（默认即是）。

llama-server 需要支持 OpenAI 兼容接口，建议参数：

    --jinja
    -c 262144
    --flash-attn
    --cache-type-k q8_0 --cache-type-v q8_0
    --host 127.0.0.1 --port 8080

翻译时应用会显式关闭 thinking（chat_template_kwargs.enable_thinking=false），
并在解析侧兜底剥离 think 标签；若构建不认这个字段，设置页可改 json_mode 与采样。

## 目录

    backend/app/           API、队列、翻译流水线
    backend/app/model/     llama.cpp 适配器（含 Fake 适配器用于单测）
    backend/app/documents/ DOCX / XLSX / PDF / 文本 解析与写回
    frontend/              React + TypeScript + Vite + Tailwind 前端
    scripts/               probe_model.py（环境探针）、translate_cli.py（命令行翻译）
    deploy/                systemd 与 Caddy 示例
    tests/                 单元测试（不需要模型）

## 开发模式

后端：

    .venv/bin/uvicorn backend.app.main:app --reload --env-file .env

前端（Vite 代理 /api 到 127.0.0.1:8000）：

    cd frontend && npm run dev

## 验证

    .venv/bin/python scripts/probe_model.py
    .venv/bin/python scripts/translate_cli.py a.docx --to zh-CN --out a.zh.docx

## 已知限制

- PDF 默认原位替换文本（保留版式）；可切 reflow 模式重排，版式不保留。
- DOCX 不处理脚注、尾注、文本框、批注、修订、SmartArt。
- XLSX 不改公式、图表、透视表；.xlsm 仅保留 VBA 工程。
- 无登录，默认只适合可信局域网；对外请自行加反代与访问控制。
