# 本地 AI 文档翻译平台 — 实施计划

> 依据：`local-ai-document-translator-plan.md`（v1.1，技术方案）
> 本计划版本：**v1.5** ／ 2026-10-26
> 状态：**已开工**（翻译 + 聊天 + React 前端 + 术语库 + 设置已落地，见 README）。v1.5 明确分工：模型服务与服务器部署由你负责，我只交付应用代码与部署物，
> 不在本机启动服务、不做本地环境测试。v1.4 落地实际 llama.cpp 参数与页面动态配置。
> v1.3 修正了批预算公式、think 标签渲染、停止生成语义、附件链路、解析错误码，并补齐 SSE 过反向代理等 16 处问题。
> 与原方案不一致处集中在 §2.2。

---

## 0. 一页摘要

**要做的事**：在同一台 Ubuntu 机器上，与已运行的 llama.cpp 服务共存，建设一个局域网内电脑/手机可用的 Web 平台：Word / Excel / PDF 文档翻译 + AI 对话 + 文件上传 + 任务进度 + 结果下载。

### 0.1 外部条件

| 项 | 结论 |
|---|---|
| 部署 | API + Worker 与模型**同机 Ubuntu**；API 只听 `127.0.0.1`，Caddy 统一入口 |
| 模型 | Qwen3.5-9B，**Q4 GGUF**，llama.cpp 部署 |
| 架构 | 32 层，每 4 层 1 层全注意力（8 层），4 个 KV 头，head_dim 256；其余为 Gated DeltaNet 线性注意力 |
| 上下文 | 实际启动 `-c 262144`、KV q8_0（≈16 KiB/token，共 4 GiB）；`--parallel` 未显式设置，按 1 槽处理，以 `/slots` 为准 |
| 多模态 | 加载 `--mmproj`（视觉投影），占额外显存；为后续扫描件 OCR 留了接口 |
| 思考模式 | **请求侧显式关闭 + 解析侧兜底**；不依赖模型默认值 |
| 配置 | `.env` 只保留引导项；模型、采样、预算、保留期等在**页面动态配置**，改完即生效 |
| 分工 | llama.cpp 的启动、显存调优、服务器部署归你；我交付应用代码、部署物（systemd / Caddy / env 模板）与探针脚本 |
| 访问 | 仅局域网，无账号密码；用网络边界与限流补偿 |

### 0.2 修正清单（v1.3 + v1.4）

| # | 修正 | 原问题 |
|---|---|---|
| 1 | KV 换算改为 32 KiB/token | 按 Qwen3 8B 的 144 KiB 计算，高估 4.5 倍 |
| 2 | 预算改用 `/slots` 的每槽 n_ctx | `/props` 已是每槽值，再除 parallel 会二次折半 |
| 3 | 新增 thinking 关闭与剥离 | 只写了“剥代码围栏”，think 块会打爆 JSON 契约 |
| 4 | 输出上限与切批统一 | `MAX_OUTPUT_TOKENS` 与预算矛盾，长批次被截断 |
| 5 | 显式采样参数 | 原配置没有 temperature/top_p |
| 6 | 修正端口暴露 | `0.0.0.0` 可绕过 Caddy 的限流与安全头 |
| 7 | 指标分硬／软两档 | 占位符 100% 当硬门槛，对 9B 过于乐观 |
| 8 | 双语对照移出 v1 | 与 §1.2 “不做”自相矛盾 |
| 9 | 补文本适配器 | §1.2 承诺 TXT/MD，但目录与 M3 都没有 |
| 10 | 补 queued 取消、0 单元语义、术语库 API、DDL 索引 | 状态机与接口缺路径 |
| 11 | **批预算公式修正** | overhead 被扣了两次，批次比设计小 42% |
| 12 | **think 标签改用 HTML 实体** | `&lt;think&gt;` 在渲染中被当作标签吞掉，执行者拿不到匹配字面量 |
| 13 | **补停止生成的服务端语义** | 客户端 abort 后无人取消上游，槽位继续被占用 |
| 14 | **打通聊天附件链路** | 消息接口没有 file_ids，`chat_attachments` 成为死表 |
| 15 | **补解析类错误码** | 加密/损坏文件无码可写 |
| 16 | **拆分模型根地址与 /v1 地址** | `/health` `/props` `/slots` `/tokenize` 在根路径，拼到 `/v1` 下会 404 |
| 17 | **落地实际启动参数** | 原计划假设 64k / 2 槽，与实际 256k / 1 槽不符 |
| 18 | **新增页面动态配置** | 运行参数原本只放 `.env`，改一次要改文件、重启 |
| 19 | **明确分工** | 原计划默认由我启动模型并做服务器验证 |
| 20 | **取消本机测试** | 交付物改为代码 + 探针脚本，真实链路由你在服务器执行 |

### 0.3 三个已采纳的决策（可低价回退）

| 决策 | 结论 | 回退成本 |
|---|---|---|
| 双语对照 | **移出 v1**，回到“后续增强” | 加回约 1.5 人日 |
| 聊天输出 | **v1 采用流式**（SSE），用于区分“排队”与“生成中” | 改回非流式约 -0.5 人日 |
| 上下文 | **沿用你现有的 `-c 262144` / 单槽**，应用从 `/slots` 读取；需要隔离聊天与翻译时再评估 `--parallel 2` | 改启动参数即可 |

### 0.4 落地主线

1. **先竖切再横切**：M0 先在真实 llama.cpp 上打通“一个 DOCX 段落 → 模型 → 写回 → 能打开”，同时把 thinking、槽位、版本、吞吐四个未知量变成实测数字。
2. **状态以数据库为唯一真相**：SQLite 任务表既是业务数据也是队列，Worker 原子领取、心跳恢复，用 `JobQueue` 接口隔离。
3. **模型只输出 `{id: text}`**：分段、术语、写回、结构校验、文件重建全部由程序负责。
4. **PDF 第一版不承诺保版式**：只输出重建单语 DOCX，原位覆盖是实验开关。
5. **一套响应式前端 + 轮询 + 流式聊天**：任务用轮询，对话用 SSE，不引入 WebSocket。

### 0.5 工作量

MVP 约 **24.0 人日**；含页面动态配置与部署物的完整第一版约 **33.5 人日**（1 人全职约 7 周，详见 §8）。
上述人日只含我的编码与文档工作量，不含你在服务器上的部署、联调与验收时间。

### 0.6 开工前需要你确认

1. **应用监听**：服务器上监听哪个地址与端口（默认 `0.0.0.0:8000`），前面是否再加 Caddy。
2. **模型地址**：应用与 llama.cpp 是否同机（默认 `127.0.0.1:8080`）；不同机则给内网地址。
3. **探针执行**：你在服务器跑 `scripts/probe_model.py` 与 `scripts/smoke_docx.py`，把输出回贴，我据此调默认参数。

我这边**不启动 llama、不部署、不在本机跑真实联调**；上述三类事实只能由你提供。

---

## 1. 需求确认

### 1.1 我理解的核心需求

1. **局域网多端**：手机、平板、电脑访问同一地址，一套响应式页面。
2. **文档翻译为主**：DOCX / XLSX / 原生文本 PDF；扫描 PDF 与 OCR 放到第二阶段。
3. **格式尽量保真**：明确区分“内容正确”和“版式一致”，不承诺逐像素还原。
4. **异步任务**：上传即返回任务 ID，排队、进度、失败重试、取消、错误可追溯。
5. **可复用翻译策略**：源/目标语言、风格、领域、术语库、Skill 规则；版本入库备查。
6. **本地优先**：文件、数据库、日志全部留在本机，不出内网。
7. **安全边界**：文档内容是不可信数据（防提示词注入）；模型无权执行命令、读文件、访问网络。
8. **输出可控**：模型不输出思考过程，只返回结构化译文；异常输出可被识别与隔离。
9. **可演进**：先在单机把事做对；多人、多机、OCR 出现真实需求后再升级。

### 1.2 第一版范围

| 维度 | 第一版做 | 第一版不做（留到后续） |
|---|---|---|
| 文件格式 | `.docx`、`.xlsx`、受控 `.xlsm`、原生文字 `.pdf`、`.txt`/`.md` | `.doc`/`.xls` 旧格式、扫描件 OCR、CAD/PPT |
| 对话 | 新建/历史/删除、连续对话、**流式回复**、**停止生成（保存部分内容）** | 会话搜索、对话导出、RAG |
| 翻译 | DOCX/XLSX/PDF/TXT 单文件、语言、风格、领域、术语库、进度、下载 | 批量并发、**双语对照**、逐页预览 |
| 任务 | 队列、进度、重试、取消、心跳恢复、事件记录、清理 | 优先级抢占、定时任务、多机调度 |
| 术语 | 术语库 CRUD、术语 CRUD、CSV 导入导出 | 多术语库权限、冲突合并、向量检索 |
| 设置 | **页面动态配置**：模型连接、采样、批预算、聊天、保留期、格式开关；带校验、测试连接、变更审计 | 多套预设、按用户配置、定时生效 |
| 用户 | **单租户、无登录**；表保留 `user_id`（固定 `local`） | 注册、登录、团队、配额、SSO |
| 附件 | 附件可挂到消息、可一键转翻译任务；**不注入对话上下文** | 对话内文档问答（RAG） |
| 部署 | Ubuntu：systemd（api + worker）+ Caddy(:80) + ufw | Kubernetes、对象存储、Redis、PostgreSQL |

### 1.3 已确认与仍按默认值的参数

**已确认**

| # | 事项 | 结论 |
|---|---|---|
| 1 | 模型服务 | llama.cpp，Qwen3.5-9B Q4 GGUF；默认 `127.0.0.1:8080` |
| 2 | 部署位置 | 与模型同机 Ubuntu，回环访问 |
| 3 | 访问与认证 | 仅局域网，无账号密码 |
| 4 | 上下文 | `-c 262144`、KV q8_0（≈4 GiB）、单槽；应用以 `/slots` 实测为准 |
| 5 | 思考模式 | 显式关闭，解析侧兜底 |

**仍按默认值（可随时改）**

| # | 事项 | 默认值 |
|---|---|---|
| 6 | PDF 输出 | 重建单语 DOCX；原位覆盖为实验开关 |
| 7 | Excel 范围 | 页眉页脚开；表名称、批注、超链接关；`.xlsm` 只保证 VBA 工程存在 |
| 8 | 文件保留期 | 原文 7 天 / 结果 30 天 / 临时 24 小时 |
| 9 | 前端风格 | Tailwind + Radix 风格，轻量自定义 |
| 10 | Docker | 不提供 |

### 1.4 验收指标（分两档）

**硬门槛（不满足不能发布）**

- 声明范围内的文本单元 **100% 有归属**：翻译、带原因跳过、或隔离；不允许静默丢弃。
- 输出文件可打开；DOCX 段落/表格计数一致；XLSX 公式哈希、工作表、合并区域、冻结窗格一致。
- 状态机无非法跃迁；取消 / 重试 / 崩溃恢复三类演练通过。
- **停止生成后 5 秒内上游请求关闭，槽位释放，消息以 stopped 状态落库。**
- 暴露面：内网只能访问 80；8000 与 8080 不可达。
- 100 页级文档不 OOM；`kill -9` Worker 后 5 分钟内任务回到 `queued`。

**软指标（写入报告与 UI 提示，不阻塞任务）**

| 指标 | 目标 | 未达处理 |
|---|---|---|
| 数字 / 日期 / URL / 占位符保留率 | ≥ 98% | 报告标记 + “建议人工复核” |
| 术语遵循率 | ≥ 95% | 同上 |
| 空译文率 | < 0.5% | 同上，并列出单元 ID |
| 目标语种字符占比 | ≥ 90% | 标记可疑单元 |

**仅记录、不设门槛**：每千字耗时、每批 token 数、请求数、超时率、重试率。

---
## 2. 关键设计决策

### 2.1 决策清单

| 编号 | 决策 | 理由 | 影响 |
|---|---|---|---|
| D1 | 适配器对接 **llama.cpp 两套地址**：根路径 `/health` `/props` `/slots` `/tokenize`，以及 `/v1/chat/completions` | 元数据端点不在 `/v1` 下，拼错会 404 | 配置 `MODEL_ROOT_URL` 与 `MODEL_BASE_URL` |
| D2 | **文件与任务分离**：`POST /files` → `POST /translation-jobs` | 附件复用、重试不重传、上传独立限流 | 见 §2.2-1 |
| D3 | **单租户、无认证**：固定 `local` 用户；无登录页、无 Cookie | 仅局域网；少一层代码与运维 | 所有记录写固定 `user_id` |
| D4 | 队列 = **SQLite 任务表 + `BEGIN IMMEDIATE` 原子领取 + 心跳**，单 Worker | 少一个常驻组件；状态天然持久化 | `workers/queue.py` |
| D5 | **状态机在 service 层集中校验**；僵死恢复靠 `heartbeat_at` | 避免各入口随手改状态 | 状态表见 §5.4 |
| D6 | DOCX **段落级翻译 + 主 Run 样式回写** | 段内跨 Run 映射复杂度高 | 二期做 Run 级映射 |
| D7 | XLSX **只写文本单元格**，`keep_vba=True`，不重算公式 | 公式与结构是底线 | 保存前后快照对比 |
| D8 | PDF **提取 → 翻译 → 重建单语 DOCX** | 覆盖原文本不可控 | 双语对照移出 v1 |
| D9 | 批次预算用 **`/tokenize` 精确计数**（LRU 缓存） | 自带分词端点 | 粗切 → 精确收敛 |
| D10 | Skill 只作为 **白名单提示词片段**，版本入库 | 9B 模型不会自动读目录 | 不做工具调用 |
| D11 | 输出契约固定为 `{"translations":[{"id","text"}]}`，**集合相等校验** | 思考块会破坏 JSON | 见 D18 |
| D12 | 术语匹配在应用侧完成（精确 / 忽略大小写 / 最长优先） | 可控可测 | 命中注入 + 事后校验 |
| D13 | 前端 React + TS + Vite + Tailwind + TanStack Query；任务轮询 2 秒，**对话走 SSE** | 轮询最稳；流式区分排队与生成 | PWA 只缓存应用壳 |
| D14 | 部署 **Ubuntu systemd（api / worker）+ Caddy** | 与模型同机，最少组件 | 部署物在 M6 |
| D15 | **暴露面**：API 只监听 `127.0.0.1:8000`，Caddy :80；llama-server 只听 `127.0.0.1:8080` | 无认证时网络边界是唯一边界 | 限流在应用层 |
| D16 | 上下文预算以 **`/slots` 的每槽 `n_ctx` 为权威值**，不再除以 parallel | `/props` 已是每槽值 | 公式见 §5.2 |
| D17 | **输出上限与切批联动**；翻译与聊天使用**不同的输出上限** | 6144 的输出上限套给聊天会超时 | 见 §5.6 |
| D18 | **采样参数按用途分两套并固定 seed**；思考模式显式关闭 | 结果需可复现 | 两套都进 `.env` |
| D19 | **停止生成 = 客户端断连**：服务端检测断连 → 关闭上游流 → 以 `status=stopped` 保存部分内容 | 不能只靠前端 abort，否则槽位继续被占 | 见 §5.5 |
| D20 | **附件只挂载、不注入**：`file_ids` 挂到消息，仅用于展示与“一键转翻译”；不进入提示词 | 附件内容进对话会打爆上下文 | 见 §5.5 与 §5.3 |
| D21 | **配置分层**：默认值 < 环境变量 < 数据库覆盖；`.env` 只保留引导项（路径、DB、监听、令牌），其余走页面 | 改参数不必改文件、不必重启 | 见 §5.6 |
| D22 | **配置快照**：Worker 在任务开始时冻结一份有效配置写入 `options_json`，运行中改配置不影响在途任务 | 结果可复现、可追溯 | 见 §5.3 |

### 2.2 对原方案的修订点

1. **新增 `POST /api/v1/files`**：上传与建任务拆开，附件与翻译共用文件对象。
2. **新增 `translation_job_events` 表**：原方案提到“任务事件表”但未定义。
3. **新增 `worker_heartbeats` 表**：设置页要显示 Worker 存活。
4. **移除 `uploaded` 状态**：任务创建即入队。
5. **删除认证接口与登录页**：局域网免登录（已确认）。
6. **PDF 只保留“重建 DOCX”**；双语对照按原方案属后续增强。
7. **批次预算改为精确 token 计数**。
8. **术语匹配第一版不做模糊/向量**。
9. **前端补工程细节**：路由、轮询、SSE、上传进度、移动端导航。
10. **部署落地到 Ubuntu**：systemd + Caddy + ufw。
11. **补 llama.cpp 约束**：`--parallel` 平分上下文、`--jinja` 决定模板、thinking 默认值不可依赖。
12. **PWA 预期校正**：局域网 HTTP 非安全上下文，安装需 HTTPS。
13. **聊天改为流式**：原方案列为阶段 2，本计划提前到 v1。
14. **文本格式纳入 v1**：`.txt`/`.md` 作为最低成本验证载体。
15. **新增“声明范围”概念**：覆盖率只对声明支持的元素生效。
16. **补停止生成语义**：原方案没有定义“停止”的行为边界。
17. **附件仅挂载不注入**：原方案的“对话中分析文件”推迟到 RAG 阶段。

---

## 3. 工作方式（协作与交付）

### 3.1 交付节奏

- 以**里程碑（M0–M6）为交付单元**，一次只推进一个 M；每个 M 结束都能独立运行、可回滚、有测试。
- **每周一个可见产物**：第 1 周能“上传 DOCX 并拿到译文文件”，第 2 周有真实队列与进度，第 3–4 周覆盖四种格式，第 5 周有完整界面。
- **先纵向打通，再横向扩展**：M0 的垂直切片决定后面所有适配器的接口形状，不允许跳过。
- **决策落文档**：偏离本计划的实现，先在 `docs/adr/NNNN-*.md` 记一段 ADR。

### 3.2 每个里程碑的完成定义（DoD）

- [ ] `ruff check` + `ruff format --check` 通过，`pytest -q` 全绿。
- [ ] 新增 API 有集成测试（成功 + 至少 2 个失败分支）。
- [ ] 前端改动通过 `npm run build` 与 `npm run test`。
- [ ] 手动验证步骤记录在 `docs/verification/Mx.md`，含实际执行结果。
- [ ] 已知限制追加到 `docs/LIMITATIONS.md`。
- [ ] 数据库变更提供 Alembic 迁移（`render_as_batch=True`，含 downgrade）。
- [ ] 打 tag（`m0` … `m6`），CHANGELOG 写 3–10 行。

### 3.3 协作约定

**需要你提供**

1. **探针回贴**：在服务器执行 `scripts/probe_model.py` 与 `scripts/smoke_docx.py`，把输出贴回（我无法访问你的机器）。
2. **llama.cpp 信息**：`llama-server --version`、完整启动参数（尤其 `--ctx-size`、`--parallel`、`--jinja`、`--chat-template-kwargs` 是否可用、`--cache-type-*`）、GGUF 量化类型。
3. **Ubuntu 版本与 Python / Node 版本**。
4. **局域网网段**与固定 IP / 主机名。
5. **3–5 个真实样本**，放 `tests/fixtures/real/`（不进版本库）。

**我不会做的事**

- 不擅自引入 Redis、PostgreSQL、MinIO、Docker、OCR、向量库。
- 不把真实文档、内网地址、模型路径提交进仓库；不写入日志。
- 不修改你的原始方案文件。
- 不做范围外功能（小程序、桌面端、多租户、计费）。
- 不在模型接口未知时假装“已适配”，先用 `FakeModelAdapter` 跑通其余链路。
- 不启动、不重启、不调试你的 llama.cpp；不登录你的服务器；不做线上排障。

**验证方式**

- 我这边只用 `FakeModelAdapter` 跑单元测试，不需要模型、GPU 或网络。
- 每个 M 结束给出可直接复制的命令，由你在服务器执行并把结果回贴。
- 文档类结果同时给“质量报告 JSON 摘要”。
- 真实链路的联调（含停止生成、槽位释放）由你在服务器验，我只负责按回贴调参。

### 3.4 工程约定

- 仓库：`git init`，`main` 保护，功能分支 `feat/m3-docx`，Conventional Commits。
- 目录：`backend/`、`frontend/`、`scripts/`、`deploy/`、`docs/`、`tests/fixtures/`。
- 质量门：`ruff` + `mypy`（adapters/services 必过）+ `pytest`（覆盖率 ≥ 70%）。
- 样本：`tests/fixtures/synthetic/` 可提交；`real/` 进 `.gitignore`。
- 配置：`.env` 不入库，`.env.example` 完整可读。
- 交付：代码仓库 + 部署物交给你，由你同步到服务器并执行；我不做远程部署。

---
## 4. 里程碑计划

> 人日为单人全职估算，含测试与文档，不含需求返工。

### M0 · 环境核实与垂直切片（2.0 人日）

**目标**：我交付探针与冒烟脚本；你在服务器执行并回贴，把**上下文口径、thinking 行为、构建版本、吞吐、断连释放**五个未知量变成实测数字。

任务：

- [ ] `git init`、`.gitignore`、`README.md` 骨架、`Makefile`、`.env.example`。
- [ ] `scripts/probe_model.py`，探测项：
  1. `llama-server --version`（记录支持 qwen35 的最低构建号）。
  2. 根路径 `GET /health`：加载中 503 / 就绪 200。
  3. 根路径 `GET /props`：`total_slots`、`default_generation_settings.n_ctx`（**每槽值**）。
  4. 根路径 `GET /slots`：逐槽 `n_ctx`（权威值）；与 `/props`、`--ctx-size/--parallel` 三方对齐；若返回 401/404/501，记录并走回退逻辑。
  5. `GET /v1/models`：模型别名。
  6. 根路径 `POST /tokenize`：中英各 10 段，校准“字 → token”系数。
  7. **thinking 开/关双向**：观察 `content` 里是否出现 `&lt;think&gt;`、是否有独立 `reasoning_content`、`--jinja` 是否真正生效（有无原始模板串泄漏）。
  8. **服务端 `--chat-template-kwargs` 是否被当前构建接受**（`--help` / 启动日志 / 失败退出）。
  9. `response_format=json_object` 与 `json_schema` 的支持情况。
  10. `--cache-type-k/v q8_0` 是否被该混合架构接受；`--flash-attn` 是否必需。
  11. 实际 tok/s、首 token 延迟、所选 ctx 下 `nvidia-smi` 峰值。
  12. **断连释放测试**：发起一次流式请求后客户端主动断开，观察 `/slots` 中该槽多久释放（决定 `stopped` 语义是否可依赖）。
- [ ] `backend/app/model_adapters/base.py`：`chat` / `chat_stream` / `translate_batch` / `health` / `tokenize` 五个方法定稿。
- [ ] `backend/app/model_adapters/llamacpp_adapter.py`：双地址（根 + `/v1`）、超时、连接失败、非 JSON 输出的最小实现。
- [ ] `scripts/smoke_docx.py`：抽取段落 → 翻译 → 写回 → 重新打开校验。
- [ ] 合成样本（DOCX/XLSX/PDF/TXT）到 `tests/fixtures/synthetic/`。
- [ ] **Q4 质量基线**：20 段真实文本翻译各一遍，人工记录术语与长句问题。
- [ ] `docs/phase-0-environment.md`：按 §10 模板填写，给出推荐批预算。

**验收（由你在服务器执行并回贴）**：真实模型完成一次 10 段翻译，写回后可打开、段落数不变；环境表完整；**thinking 关闭后输出不含 `&lt;think&gt;` 且 JSON 可解析**；断连后槽位能在秒级释放；批预算有实测依据。

### M1 · 后端骨架 + 文件 + 任务入口 + 设置服务（3.5 人日）

**目标**：可上传、可建任务、可看系统状态（任务暂不执行）。无登录。

- [ ] FastAPI 骨架、统一错误响应、结构化日志、`/healthz`、`/readyz`。
- [ ] 配置层（pydantic-settings）+ `.env.example`（含 §5.6 全部键）。
- [ ] SQLAlchemy 2.0 模型 + Alembic 初始化（`render_as_batch=True`）+ 首版迁移，启动时种子 `local` 用户。
- [ ] 文件上传：大小、扩展名、magic bytes、ZIP 炸弹防护、sha256、内部 ID 存储。
- [ ] 任务创建/列表/详情/删除接口（状态停在 `queued`）。
- [ ] **文件删除规则**：被任务或聊天附件引用时返回 409；否则软删（只删 blob，保留行）。
- [ ] **设置服务**：`app_settings` 表 + 分层取值（default < env < db）+ 分组与范围定义 + PATCH 校验 + 审计写入。
- [ ] **设置 API**：GET / PATCH / reset / history + `POST /system/test-model`。
- [ ] 任务创建时把有效配置快照写入 `options_json`（D22）。
- [ ] `GET /api/v1/system/status`：模型别名、每槽 `n_ctx`、槽位占用、Worker 心跳、磁盘余量。
- [ ] 前端最小壳：Vite + 路由 + 布局 + API 客户端 + 工作台占位。
- [ ] 应用层限流中间件：只信任来自回环的 `X-Forwarded-For`。
- [ ] 测试：超大文件、伪装扩展名、ZIP 炸弹、损坏文件、越界参数、被引用文件删除。

**验收**：`make dev` 同时起前后端；无需登录；上传 DOCX 后看到 `queued` 任务；**PATCH 一次 settings 能立即反映到状态与后续任务**；`pytest` 全绿。

### M2 · 队列与 Worker（2.5 人日）

**目标**：任务被领取执行，具备进度、重试、取消、崩溃恢复。

- [ ] `workers/queue.py`：`JobQueue` 协议 + `SQLiteJobQueue`。
- [ ] 原子领取事务（WAL、`busy_timeout`、`BEGIN IMMEDIATE`）。
- [ ] Worker 主循环：信号处理、优雅退出、空转 1 秒、进度写节流。
- [ ] 状态机 service：合法转换校验、事件写入。
- [ ] **取消两条路径**：`queued` 由 API 直接置 `cancelled`；运行中写 `cancel_requested`，Worker 在批次边界生效。
- [ ] **0 单元三态**：`no_translatable_units` / `scanned_pdf_no_text`（失败）；`all_units_skipped` / `already_target_language`（成功 + 警告）。
- [ ] 重试与退避、`max_attempts`、僵死恢复、临时目录清理、Worker 心跳。
- [ ] 测试：双 Worker 不重复领取、`kill -9` 恢复、取消无半成品、幂等重跑、queued 直接取消。

**验收**：杀 Worker 后 5 分钟内任务回到 `queued` 并完成；取消不产生结果文件。

### M3 · 文档适配器（8.5 人日：DOCX 3 / XLSX 2.5 / PDF 2.5 / 文本 0.5）

**目标**：四种格式解析、写回、校验，输出统一质量报告。

统一接口：

```python
class DocumentAdapter(Protocol):
    def detect(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> ParsedDocument:          # 文本单元 + 结构句柄
    def rebuild(self, doc: ParsedDocument, texts: dict[str, str], out: Path) -> RebuildResult: ...
    def verify(self, source: Path, out: Path) -> list[CheckResult]: ...
```

**DOCX（3 人日）**

- 支持：正文段落、标题、列表、普通表格、页眉页脚（开关）、超链接显示文本（默认关）。
- 显式不支持（检测计数 → 报告 + LIMITATIONS）：脚注/尾注、文本框与形状内文字、批注、修订痕迹、SmartArt、内容控件、域代码、嵌入对象、TOC 域结果。
- 回写：主 Run 保留格式，其余 Run 清空；混合格式段落登记。
- 校验：可打开、段落/表格计数、样式指纹、超链接数量、zip 完整性。

**XLSX（2.5 人日）**

- 只翻译字符串单元格；跳过公式、数字、日期、布尔、错误、空白。
- 开关：`XLSX_TRANSLATE_SHEET_NAMES`、`XLSX_TRANSLATE_COMMENTS`、`XLSX_TRANSLATE_HYPERLINKS`（默认全关）。
- `.xlsm` 用 `keep_vba=True`，保持扩展名。
- 保存前后快照：公式哈希、工作表、合并区域、冻结窗格、行列维度、条件格式数量。
- 显式不支持：图表标题/数据标签、透视表标签、数据验证提示、定义名称。

**PDF（2.5 人日）**

- PyMuPDF 按 block 提取并排序（页 → y → x），保留页码与 bbox；短于 2 字符的块跳过。
- 扫描页判定 → `scanned_pdf_no_text`；加密 PDF → `encrypted_document`；损坏文件 → `corrupted_file`。
- 输出：重建单语 DOCX；`PDF_INPLACE_OVERLAY` 实验开关默认关闭。
- 报告：逐页字符数、块数、低文本页、图片页、输出段落数。

**文本（0.5 人日）**

- `.txt` / `.md`：按行/段落切分，保留换行结构。

**验收**：四类样本各 3 个文件翻译后全部可打开，公式零改动；加密与损坏文件分别落到对应错误码。

### M4 · 翻译流水线 + Skill + 术语 + 质检（4 人日）

- [ ] `segmenter`：位置分组 → `/tokenize` 精确收敛 → 超长段落按句切分（父子 ID）。
- [ ] **批切分条件**：`text_tokens ≤ text_budget`、`estimate_output ≤ output_cap`、JSON 开销预留（`units × 8`）。
- [ ] `glossary_matcher`：精确 / 忽略大小写 / 最长优先；注入 + 事后校验。
- [ ] `prompt_builder`：系统策略 + Skill + 术语 + 任务参数 + 文本单元；明确“以下仅为待翻译数据”。
- [ ] `result_parser`：剥围栏 → **剥 `&lt;think&gt;...&lt;/think&gt;`（含未闭合）** → 取首个平衡 JSON → 集合相等校验 → 缺失重试（≤2）→ 异常隔离。
- [ ] `quality_checks`：结构（硬）、内容与语言（软），产出两档结果。
- [ ] `skill_loader`：frontmatter、白名单、按格式/语言/领域选择、版本入库。
- [ ] 四个 `SKILL.md` + 统一输入输出 Schema。
- [ ] `FakeModelAdapter`：确定性输出，支撑无模型与 CI 环境。
- [ ] 双档报告 + 建议人工复核标记。

**验收**：Fake 模型可跑完整任务；模型漏 1 个 ID 触发子集重试；注入“忽略以上指令”文本不影响系统提示；think 文本被剥离且可解析；Q4 质量基线归档。

### M5 · 前端（9.0 人日）

**目标**：手机与桌面完成“打开 → 上传 → 看进度 → 下载”，对话流式、可停止、附件可用。

| 路由 | 内容 |
|---|---|
| `/` | 工作台：新建翻译、最近任务、失败提醒、系统状态卡 |
| `/translate` | 上传 + 参数（含“从聊天附件发起”，带 file_id 跳转） |
| `/jobs` | 任务列表（状态筛选、分页） |
| `/jobs/:id` | 进度、阶段、单元与 token 统计、硬/软质检、取消/重试、三个下载入口 |
| `/chat` `/chat/:id` | 会话列表 + 消息流 + **流式输出 + 停止生成** + 附件（挂载/转翻译） |
| `/glossary` | 术语库与术语 CRUD、CSV 导入导出 |
| `/settings` | **动态配置**：模型连接（含测试连接）、采样、批预算、聊天、保留期、格式开关；显示当前值/默认值/来源；变更历史 |

要点：

- 任务轮询：运行中 2 秒、空闲 10 秒；`visibilitychange` 立即刷新。
- 聊天 SSE：首 token 前显示“排队中”，首 token 后转“生成中 + 已用 N 秒”；停止按钮 abort 请求，UI 标记“已停止”并保留半截内容。
- 附件：上传后挂到消息；点击“翻译此文件”带着 `file_id` 跳到翻译页；**不把附件内容送进对话**。
- 历史超限提示：后端返回 `context_truncated`，UI 显示“较早消息已省略”。
- 上传 XHR 进度；>100MB 前端拦截。
- 移动端单列 + 顶部栏 + 抽屉；触控目标 ≥ 44px。
- 错误提示区分“可重试 / 需换文件 / 模型忙”。
- 无任何登录入口；设置页标注“仅局域网可访问”。
- 设置页：分组卡片 + 脏状态保存栏 + 校验提示 + “测试连接”结果 + 历史抽屉（可回滚单个键）。
- 设置保存后**当前页立即生效**；在途任务不受影响（后端快照），UI 明确提示这一点。

**验收**：手机完成完整翻译并下载；聊天流式可停止且半截内容保留；附件可转成翻译任务；**设置页改采样后新任务生效、在途任务不受影响**；状态卡显示真实 `/slots` 数据。

### M6 · 硬化、回归与 Ubuntu 部署（4.0 人日）

- [ ] 安全复查：上传校验、路径构造、中文文件名下载头（RFC 5987）、速率限制、CSP 与安全响应头、日志脱敏。
- [ ] 暴露面：API 仅 `127.0.0.1:8000`；Caddy :80；llama-server 仅回环；ufw 生效；`curl IP:8000` 与 `IP:8080` 必须失败。
- [ ] Caddy：`request_body max_size 110MB`、安全头、反代超时。
- [ ] **SSE 经反代验证**：`curl -N http://IP/api/v1/chats/{id}/messages/stream` 必须逐块到达；若被缓冲，对 `/api/*` 关闭 `encode` 并设 `flush_interval -1`。
- [ ] 保留期清理：过期文件、`temp/`、孤儿报告、旧事件（`JOB_EVENT_RETENTION_DAYS=180`）。
- [ ] 备份/恢复脚本 + 一次演练（`sqlite3 .backup` + `rsync`）。
- [ ] 部署物：两个 systemd unit、Caddyfile、`/etc/corefix/env` 模板、runbook。
- [ ] 版本锁定：记录 llama.cpp 构建号，升级前必须重跑 `probe_model.py` 与冒烟。
- [ ] （可选）局域网 HTTPS：Caddy 内部 CA，用于 PWA 安装。
- [ ] 固定测试集全量回归；文档：README / ARCHITECTURE / LIMITATIONS / PRIVACY / RUNBOOK。

**验收（由你执行）**：按 runbook 在服务器完成部署；重启后服务自动恢复、任务不丢；SSE 过反代不粘包。部署动作与线上排障归你。

---
## 5. 技术骨架

### 5.1 目录结构

```text
CoreFixTranslator/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/{system,files,translations,chats,glossary,meta}.py
│   │   ├── core/{config,logging,exceptions,deps,ratelimit}.py
│   │   ├── db/{base,session,models}.py
│   │   ├── schemas/*.py
│   │   ├── services/{chat,translation,task,glossary,storage,cleanup,system}_service.py
│   │   ├── model_adapters/{base,llamacpp_adapter,fake_adapter}.py
│   │   ├── document_adapters/{base,docx_adapter,xlsx_adapter,pdf_adapter,text_adapter}.py
│   │   ├── translation/{segmenter,glossary_matcher,prompt_builder,result_parser,quality_checks,report}.py
│   │   ├── chat/{context_budget.py,streaming.py}
│   │   ├── skills/{skill_loader.py, docx-translation/SKILL.md, ...}
│   │   └── workers/{queue.py, translation_worker.py, heartbeat.py}
│   ├── migrations/            # Alembic（render_as_batch=True）
│   ├── tests/{unit,integration,fixtures}
│   └── pyproject.toml
├── frontend/                  # Vite + React + TS
├── scripts/{probe_model.py,smoke_docx.py,make_fixtures.py,backup.sh,restore.sh}
├── deploy/{systemd,caddy,env.example}
├── docs/{adr,verification,phase-0-environment.md,LIMITATIONS.md}
├── storage/                   # 运行时生成，不入库
└── Makefile
```

### 5.2 与 llama.cpp 的对接契约

**两套地址**：元数据端点在根路径，只有推理接口在 `/v1` 下。

| 端点 | 用途 | 关键注意 |
|---|---|---|
| `GET {ROOT}/health` | 就绪探针 | 加载中 503 |
| `GET {ROOT}/props` | `total_slots`、`default_generation_settings.n_ctx` | **该 n_ctx 是每槽值**，不要再除 parallel |
| `GET {ROOT}/slots` | 逐槽 `n_ctx` | 预算权威来源；不可用时回退 `/props` |
| `POST {ROOT}/tokenize` | 精确 token 计数 | LRU 缓存（按文本哈希） |
| `GET {BASE}/models` | 模型别名 | 前端状态卡展示 |
| `POST {BASE}/chat/completions` | 对话与翻译 | 支持 `stream`；`chat_template_kwargs` 关 thinking |

> `ROOT=http://127.0.0.1:8080`，`BASE=http://127.0.0.1:8080/v1`。
> 拼成 `/v1/props` 会 404——这是 v1.2 遗留的隐性 bug。

**上下文换算**

```text
Qwen3.5-9B 混合注意力：
  32 层，full_attention_interval = 4 → 仅 8 层全注意力
  4 个 KV 头，head_dim 256
  每 token KV = 8 层 × 2(K,V) × 4 头 × 256 维 × 2 B = 32,768 B = 32 KiB

fp16 KV：6 GiB ≈ 196,608 token；32k ≈ 1 GiB；q8_0 再减半。
Gated DeltaNet 状态按序列固定（不随 token 增长），按槽单列，实测计入显存。
本机配置：-c 262144 + q8_0 → KV ≈ 16 KiB/token × 262144 = 4 GiB；再加 Q4_K_XL 权重（≈5.5GB）、
mmproj 与计算缓冲，实际峰值必须用 nvidia-smi 实测。
```

**批预算（v1.3 修正：overhead 只从总输入里扣一次）**

```text
slot_ctx      = /slots 的该槽 n_ctx
output_cap    = min(0.35 × slot_ctx, TRANSLATION_MAX_OUTPUT_TOKENS)
target_output = min(output_cap, TRANSLATION_TARGET_OUTPUT_TOKENS)

# 文本预算：先按“目标输出 / 扩展比”反推，再与“槽位输入上限 − 提示开销”取小
text_budget   = min(0.55 × slot_ctx − PROMPT_OVERHEAD_TOKENS,
                    target_output / TRANSLATION_TOKEN_EXPANSION)

prompt_est    = text_budget + PROMPT_OVERHEAD_TOKENS     # 实际提示长度
切批条件：text_tokens ≤ text_budget 且 estimate_output ≤ output_cap
estimate_output ≈ text_tokens × EXPANSION + units × 8    # JSON 开销
```

校验：`slot_ctx=262144`、`target_output=2500`、`EXPANSION=1.3`、`OVERHEAD=800` 时
`text_budget = min(143379, 1923) = 1923`，`prompt_est ≈ 2723`，加输出 2500 共约 5.2k。
结论：**256k 槽位下上下文完全不是约束**，批次大小由目标输出与生成时延决定。

> **真正的瓶颈是生成时延，不是上下文。** 2500 token 输出在 Q4、30–60 tok/s 下约 40–85 秒/批；
> 批大小按“目标输出 ≈2500 token”反推，而不是把槽塞满。

**实际启动参数（你提供的，v1.4 落地）**

```bash
cd ~/llama.cpp
./build/bin/llama-server \
  -m /home/user_0/models/qwen35-9b/Qwen3.5-9B-UD-Q4_K_XL.gguf \
  --mmproj /home/user_0/models/qwen35-9b/mmproj-BF16.gguf \
  -ngl 99 \
  -c 262144 \
  --flash-attn \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja \
  --host 127.0.0.1 --port 8080
```

> ⚠️ 你贴的原命令在 `--cache-type-v q8_0` 后**少了一个续行符 `\`**，照抄会让 `--jinja` 被当成独立命令执行；上面已补。

从这条命令能确定的：

- `n_ctx = 262144`，KV q8_0 → 16 KiB/token → **KV 共 4 GiB**。
- `--parallel` 未设置，按 **1 槽**处理：聊天与翻译共用同一个槽，长批次运行时聊天会排队。
- `--mmproj` 说明加载了视觉投影，模型是多模态的——**为后续扫描件 OCR 留了后路**，第一版不用。
- 未设 `--alias`，`/v1/models` 返回名可能不稳定；建议补 `--alias qwen3.5-9b`。
- 未设 `--chat-template-kwargs`，只能靠请求体 `chat_template_kwargs` 关 thinking（M0 验证是否被接受）。

可选调整（M0 实测显存后再定，不改也能跑）：

```text
--parallel 2        # 聊天与翻译各占一槽；总 ctx 不变，仍 262144，每槽 131072
--alias qwen3.5-9b  # 固定 /v1/models 返回的名字
```

> 注意：混合架构下每个并行槽还有一份 Gated DeltaNet 状态，`--parallel 2` 会让这部分显存翻倍。

**thinking 处理（两侧都要做）**

- 请求侧：`{"chat_template_kwargs": {"enable_thinking": false}}`；构建不认此字段时改用服务端参数。
- 服务端：`--jinja` 必须开；可选 `--reasoning-format none`。
- 解析侧：剥离 `&lt;think&gt;...&lt;/think&gt;`、`&lt;think&gt;...`（未闭合，截断场景），再提取 JSON。
- 不能依赖“默认关闭”：不同 GGUF/模板默认值不一致，M0 必须双向实测。

### 5.3 数据库（核心 DDL）

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE users (
  id           TEXT PRIMARY KEY,          -- 第一版固定 'local'
  username     TEXT NOT NULL UNIQUE,
  display_name TEXT,
  role         TEXT NOT NULL DEFAULT 'owner',
  is_active    INTEGER NOT NULL DEFAULT 1,
  created_at   TEXT NOT NULL
);

CREATE TABLE glossaries (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL REFERENCES users(id),
  name            TEXT NOT NULL,
  source_language TEXT NOT NULL,
  target_language TEXT NOT NULL,
  domain          TEXT,
  is_default      INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL
);

CREATE TABLE glossary_terms (
  id             TEXT PRIMARY KEY,
  glossary_id    TEXT NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
  source_term    TEXT NOT NULL,
  target_term    TEXT NOT NULL,
  match_mode     TEXT NOT NULL DEFAULT 'exact',  -- exact | case_insensitive
  force          INTEGER NOT NULL DEFAULT 0,
  note           TEXT,
  updated_at     TEXT NOT NULL,
  UNIQUE (glossary_id, source_term)
);

-- 文件只软删（deleted_at + 删 blob），不硬删行，避免 FK 悬挂
CREATE TABLE files (
  id                TEXT PRIMARY KEY,
  user_id           TEXT NOT NULL REFERENCES users(id),
  purpose           TEXT NOT NULL,   -- translation_source | translation_result | chat_attachment
  original_filename TEXT NOT NULL,
  stored_relpath    TEXT NOT NULL,
  mime_type         TEXT NOT NULL,
  size_bytes        INTEGER NOT NULL,
  sha256            TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  expires_at        TEXT,
  deleted_at        TEXT
);
CREATE INDEX idx_files_expires ON files(expires_at) WHERE deleted_at IS NULL;

CREATE TABLE translation_jobs (
  id               TEXT PRIMARY KEY,
  user_id          TEXT NOT NULL REFERENCES users(id),
  source_file_id   TEXT NOT NULL REFERENCES files(id),
  result_file_id   TEXT REFERENCES files(id),
  source_language  TEXT NOT NULL,
  target_language  TEXT NOT NULL,
  style            TEXT,
  domain           TEXT,
  glossary_id      TEXT REFERENCES glossaries(id) ON DELETE SET NULL,
  skill_name       TEXT NOT NULL,
  skill_version    TEXT NOT NULL,
  options_json     TEXT NOT NULL DEFAULT '{}',
  status           TEXT NOT NULL,
  progress_percent INTEGER NOT NULL DEFAULT 0,
  current_stage    TEXT,
  total_units      INTEGER,
  done_units       INTEGER,
  total_tokens     INTEGER,
  priority         INTEGER NOT NULL DEFAULT 100,
  attempts         INTEGER NOT NULL DEFAULT 0,
  max_attempts     INTEGER NOT NULL DEFAULT 3,
  available_at     TEXT NOT NULL,
  locked_by        TEXT,
  heartbeat_at     TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error_code       TEXT,
  error_summary    TEXT,
  report_relpath   TEXT,
  created_at       TEXT NOT NULL,
  started_at       TEXT,
  completed_at     TEXT,
  CHECK (status IN ('queued','parsing','translating','rebuilding','validating',
                    'completed','failed','cancelled'))
);
CREATE INDEX idx_jobs_claim   ON translation_jobs(status, available_at, priority, id);
CREATE INDEX idx_jobs_user    ON translation_jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_created ON translation_jobs(created_at);

CREATE TABLE translation_job_events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id    TEXT NOT NULL REFERENCES translation_jobs(id) ON DELETE CASCADE,
  at        TEXT NOT NULL,
  level     TEXT NOT NULL,          -- info | warn | error
  stage     TEXT,
  code      TEXT,
  message   TEXT,
  data_json TEXT
);
CREATE INDEX idx_events_job ON translation_job_events(job_id, id);

CREATE TABLE worker_heartbeats (
  worker_id   TEXT PRIMARY KEY,
  status      TEXT NOT NULL,        -- idle | busy | stopping
  current_job TEXT,
  started_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE chats (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id),
  title      TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE chat_messages (
  id             TEXT PRIMARY KEY,
  chat_id        TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role           TEXT NOT NULL,     -- user | assistant | system
  content        TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'complete',  -- complete | stopped | error
  model_metadata TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX idx_messages_chat ON chat_messages(chat_id, created_at);

CREATE TABLE chat_attachments (
  message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  file_id    TEXT NOT NULL REFERENCES files(id),
  PRIMARY KEY (message_id, file_id)
);
CREATE INDEX idx_attachments_file ON chat_attachments(file_id);

-- 页面动态配置：只存被覆盖的键，读取时与 env / 内置默认合并
CREATE TABLE app_settings (
  key           TEXT PRIMARY KEY,
  value_json    TEXT NOT NULL,
  version       INTEGER NOT NULL DEFAULT 1,
  updated_at    TEXT NOT NULL,
  updated_by_ip TEXT
);

CREATE TABLE app_settings_history (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  key       TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  at        TEXT NOT NULL,
  client_ip TEXT
);
CREATE INDEX idx_settings_history ON app_settings_history(at DESC);
```

**error_code 取值**

| 层级 | 取值 |
|---|---|
| 上传（HTTP 4xx） | `unsupported_format`、`corrupted_file`、`zip_bomb_suspected`、`file_too_large` |
| 任务解析 | `encrypted_document`、`parse_failed`、`no_translatable_units`、`scanned_pdf_no_text` |
| 任务执行 | `model_unreachable`、`model_timeout`、`model_overloaded`、`invalid_model_output` |
| 任务收尾 | `rebuild_failed`、`verify_failed`、`cancelled_by_user`、`internal_error` |
| 下载 | `file_expired`（HTTP 410） |

### 5.4 状态机

```text
queued ──claim──▶ parsing ──▶ translating ──▶ rebuilding ──▶ validating ──▶ completed
   │                  │             │               │              │
   │                  └─────────────┴───────────────┴──────────────┴──▶ failed
   │                                                                     │
   ├──cancel(API 直接)──────────────────────────────────────────────────▶ cancelled
   │                                                                     │
   └──────────────── manual retry ◀──────────────────────────────────────┘

运行中 + cancel_requested=1 ──批次边界检查──▶ cancelled
僵死（heartbeat 超时）──────▶ queued（attempts 已计），超限则 failed
```

| 转换 | 触发 | 守卫 |
|---|---|---|
| `queued → parsing` | Worker claim | `available_at <= now` 且 `attempts < max_attempts` |
| `queued → cancelled` | API 取消 | 无（不需要 Worker） |
| `parsing → translating` | 单元数 > 0 | 未请求取消 |
| `parsing → failed` | 单元数 = 0 或解析异常 | `no_translatable_units` / `parse_failed` / `encrypted_document` |
| `translating → rebuilding` | 全部单元有归属 | 未请求取消 |
| `rebuilding → validating` | 文件写出成功 | 输出存在且可读 |
| `validating → completed` | 质检完成 | 硬指标通过；软指标仅告警 |
| `* → failed` | 不可恢复 / 重试耗尽 | 记录 `error_code` |
| `failed → queued` | 手动重试 | 用户显式重置 `attempts` |
| 运行中 `* → cancelled` | Worker 看到标记 | 删除半成品，保留事件 |
| 僵死 `* → queued` | 心跳超时 | `attempts` 超限则 `failed` |

**0 单元与“无变化”的区分**

| 场景 | 终态 | 说明 |
|---|---|---|
| 提取到 0 个单元 | `failed` | `no_translatable_units`；PDF 另给 `scanned_pdf_no_text` |
| 有单元但全部受保护/跳过 | `completed` + warning | `all_units_skipped` |
| 译文与原文一致（已是目标语言） | `completed` + warning | `already_target_language` |

### 5.5 API（第一版，无认证）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/meta` | 语言、风格、领域、限制 |
| GET | `/api/v1/system/status` | 模型别名、每槽 `n_ctx`、槽位占用、Worker 心跳、磁盘 |
| POST | `/api/v1/files` | multipart 上传，返回 file_id |
| GET | `/api/v1/files/{id}` | 元数据 |
| DELETE | `/api/v1/files/{id}` | 被任务或附件引用时 409；否则软删 |
| POST | `/api/v1/translation-jobs` | `{source_file_id, ...}`（附件也能直接建任务） |
| GET | `/api/v1/translation-jobs` | 列表（状态筛选、游标分页） |
| GET | `/api/v1/translation-jobs/{id}` | 状态、进度、token、硬/软质检 |
| GET | `/api/v1/translation-jobs/{id}/events` | 任务事件 |
| POST | `/api/v1/translation-jobs/{id}/cancel` | queued 直接取消；运行中置标记；终态幂等 200 |
| POST | `/api/v1/translation-jobs/{id}/retry` | 重置 attempts 并回 `queued` |
| GET | `/api/v1/translation-jobs/{id}/result` | 结果元数据 + 质量报告 |
| GET | `/api/v1/translation-jobs/{id}/download` | `kind=result\|source\|report`；过期 410 |
| DELETE | `/api/v1/translation-jobs/{id}` | 运行中 409；其余软删 |
| POST/GET | `/api/v1/chats` | 创建 / 列表 |
| GET/PATCH/DELETE | `/api/v1/chats/{id}` | 详情（含消息与附件）/ 改标题 / 删除 |
| POST | `/api/v1/chats/{id}/messages` | `{content, file_ids?}` 非流式 |
| POST | `/api/v1/chats/{id}/messages/stream` | 同上 payload，`text/event-stream` |
| POST/GET | `/api/v1/glossaries` | 术语库 |
| GET/PATCH/DELETE | `/api/v1/glossaries/{id}` | 详情 / 改名 / 删除 |
| GET/POST | `/api/v1/glossaries/{id}/terms` | 列表（分页 + 搜索）/ 新增 |
| PATCH/DELETE | `/api/v1/glossaries/{id}/terms/{term_id}` | 修改 / 删除 |
| POST | `/api/v1/glossaries/{id}/import` | CSV 导入 |
| GET | `/api/v1/glossaries/{id}/export.csv` | CSV 导出 |
| GET | `/api/v1/settings` | 分组返回可配置项：当前值、默认值、来源（default/env/db）、范围、单位 |
| PATCH | `/api/v1/settings` | 局部更新；校验失败 422；返回新值列表 |
| POST | `/api/v1/settings/reset` | 恢复默认（指定 key 或全部） |
| GET | `/api/v1/settings/history` | 最近 50 次变更（时间、来源 IP、旧值 → 新值） |
| POST | `/api/v1/system/test-model` | 探测 health/props/slots + 一次 1-token 生成，返回 n_ctx、槽位、别名、延迟、thinking 行为 |
| GET | `/healthz` `/readyz` | 存活 / 就绪 |

**附件语义（v1.3 补齐）**

- `file_ids` 必须属于本地文件表且未被删除；只挂载，**不进入提示词**。
- 消息详情返回附件元数据（文件名、大小、是否过期），供前端展示与“翻译此文件”。
- `POST /translation-jobs {source_file_id}` 接受任意 purpose 的文件，附件可直接转任务。

**停止生成语义（v1.3 补齐）**

1. 前端 abort `fetch`；服务端在流式生成器中轮询 `request.is_disconnected()`。
2. 检测到断连 → 关闭上游 `httpx` 流 → 让 llama.cpp 收到断连（M0 已验证槽位释放时延）。
3. 在 `finally` 中把已收到内容以 `status=stopped` 落库，事件记 `stopped_by_user`。
4. 上游报错时同样落库，`status=error`，保留已生成部分。
5. SSE 事件类型：`delta`、`done`、`stopped`、`error`；`done` 携带最终消息 ID。

**设置语义（v1.4 新增）**

- 分组：模型连接 / 采样 / 批预算 / 聊天 / 文件与保留 / 格式开关。
- 优先级：内置默认 < `.env` < 数据库；页面保存写库，**立即生效，不需要重启**。
- 只读项（只认 `.env`）：数据库路径、存储根、监听地址、`TRUSTED_PROXY`、`ACCESS_TOKEN`、`SETTINGS_TOKEN`。
- 任务快照：Worker 启动任务时把有效配置写入 `options_json`，在途任务不受后续修改影响。
- 保存前校验：范围 / 类型 / URL 格式；提供“测试连接”，失败只告警不阻止保存。
- 审计：每次写入 `app_settings_history`，记录来源 IP 与旧值；“恢复默认”同样留痕。
- 越权：无认证，对局域网开放写；可用 `SETTINGS_TOKEN` 加写保护（默认空 = 开放）。

**其他约定**

- 无认证：不设登录接口、不用 Cookie；`user_id` 固定 `local`。
- 限流：应用层令牌桶，只信任来自 `127.0.0.1` 的 `X-Forwarded-For`。
- 错误统一 `{"error": {"code": "...", "message": "..."}}`。
- 流式用 `POST` + `fetch` 读取 `ReadableStream`（`EventSource` 只支持 GET）。
- 下载带 RFC 5987 文件名头。

### 5.6 配置项

分两层：**引导项**只走 `.env`（`APP_*`、`DATABASE_URL`、`STORAGE_ROOT`、`TRUSTED_PROXY`、令牌）；
**运行参数**可在页面改、写库覆盖。下面按此顺序排列。

```dotenv
APP_ENV=production
APP_HOST=127.0.0.1              # 只给 Caddy 访问
APP_PORT=8000
TRUSTED_PROXY=127.0.0.1

# llama.cpp：根地址 + /v1 地址
MODEL_ROOT_URL=http://127.0.0.1:8080
MODEL_BASE_URL=http://127.0.0.1:8080/v1
MODEL_ALIAS=qwen3.5-9b
MODEL_TRANSLATE_TIMEOUT_SECONDS=300
MODEL_CHAT_TIMEOUT_SECONDS=180
MODEL_ENABLE_THINKING=false
MODEL_REASONING_FORMAT=none
MODEL_JSON_MODE=auto                    # auto | json_object | json_schema | none

# 输出上限：翻译与聊天分开
TRANSLATION_MAX_OUTPUT_TOKENS=6144
CHAT_MAX_OUTPUT_TOKENS=2048

# 采样（两套）
MODEL_TEMPERATURE_TRANSLATE=0.25
MODEL_TEMPERATURE_CHAT=0.7
MODEL_TOP_P=0.9
MODEL_TOP_K=20
MODEL_REPEAT_PENALTY=1.05
MODEL_SEED=42

# 批预算
TRANSLATION_TARGET_OUTPUT_TOKENS=2500
TRANSLATION_TOKEN_EXPANSION=1.3
PROMPT_OVERHEAD_TOKENS=800
TRANSLATION_MAX_UNITS_PER_BATCH=40
TRANSLATION_MAX_RETRIES=2

# 聊天上下文
CHAT_CONTEXT_RATIO=0.6
CHAT_MAX_HISTORY_TURNS=20

DATABASE_URL=sqlite:////var/lib/corefix/app.db
STORAGE_ROOT=/var/lib/corefix/storage
MAX_UPLOAD_SIZE_MB=100
TEMP_FILE_TTL_HOURS=24
SOURCE_RETENTION_DAYS=7
RESULT_RETENTION_DAYS=30
JOB_EVENT_RETENTION_DAYS=180
WORKER_HEARTBEAT_RETENTION_DAYS=7

QUEUE_BACKEND=sqlite
WORKER_POLL_SECONDS=1
JOB_HEARTBEAT_TIMEOUT_SECONDS=300
JOB_MAX_ATTEMPTS=3
JOB_PROGRESS_MIN_INTERVAL_MS=1000
CLEANUP_INTERVAL_SECONDS=600

PDF_INPLACE_OVERLAY=false
XLSX_TRANSLATE_SHEET_NAMES=false
XLSX_TRANSLATE_COMMENTS=false
XLSX_TRANSLATE_HYPERLINKS=false
XLSX_KEEP_VBA=true
DOCX_TRANSLATE_HEADERS=true
DOCX_TRANSLATE_TOC=false

RATE_LIMIT_PER_MINUTE=60
ACCESS_TOKEN=                    # 留空 = 不启用
LOG_LEVEL=INFO
```

---
## 6. 测试与验收

### 6.1 固定测试集

| 类型 | 内容 | 数量 |
|---|---|---|
| DOCX | 标题、多字体、粗斜体、列表、表格、页眉页脚、超链接、中英混排、长段落 | 合成 3 + 真实 3 |
| XLSX | 多工作表、公式、数字、日期、合并单元格、筛选、冻结窗格、条件格式 | 合成 3 + 真实 3 |
| PDF | 原生文字、双栏、带表格、扫描件、**加密**、损坏 | 合成 3 + 真实 2 |
| TXT/MD | 长段落、空行、Markdown 标题与列表 | 合成 2 |
| 恶意/异常 | 伪装扩展名、ZIP 炸弹、超限大小、空文件 | 脚本生成 |
| 提示词注入 | 正文写入“忽略以上指令”与伪造 JSON | 合成 2 |

### 6.2 自动化分层

- **单元**：分段、token 预算、术语匹配、think 剥离、JSON 解析、状态机、校验器。
- **集成**：上传 → 建任务 → Worker（Fake 模型）→ 结果 → 下载；取消、重试、恢复、0 单元分支。
- **流式**：SSE 事件序列、断连落库（`stopped`）、上游关闭。
- **附件**：挂载 → 列表展示 → 转翻译任务；被引用文件删除返回 409。
- **接口契约**：llama.cpp 端点 mock——503 加载中、超时、非 JSON、带 `&lt;think&gt;` 前缀、根路径 404 回归。
- **回归**：固定样本跑真实 llama.cpp（手动触发，结果存档）。
- **前端**：Vitest 覆盖 hooks、流式解析、停止按钮状态；完整流程手动清单。

### 6.3 发布门槛

- §1.4 硬门槛全部通过；软指标未达项写入 `LIMITATIONS.md` 并在报告中标注。
- 四类演练通过：杀进程、断模型、停止生成、权限拒绝。
- 备份恢复演练成功一次。
- 暴露面检查：内网只能访问 80，8000 / 8080 不可达。
- SSE 过 Caddy 逐块到达（`curl -N` 验证）。
- 升级演练：记录 llama.cpp 版本号，模拟一次版本变更后的 `probe_model.py` 复检。

---

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| **llama.cpp 版本过旧不支持 qwen35** | 启动失败或模板错乱 | 记录构建号并锁定；升级前重跑探测 |
| **think 默认值不可依赖** | JSON 契约被打爆 | 请求侧显式关闭 + 解析侧兜底 + M0 双向实测 |
| **根路径与 /v1 拼错** | 探测与预算全错（404） | 双地址配置；mock 测试覆盖 |
| **停止生成不生效** | 槽位被占、回复继续生成 | 断连检测 + 关闭上游 + `status=stopped`；M0 测释放时延 |
| **无认证 + 局域网** | 同网段任何人可读写 | ufw 限网段；只监听内网入口；限流；预留 `ACCESS_TOKEN` |
| **槽位争用** | 翻译运行时聊天变慢 | 翻译并发固定 1；流式“排队中”提示；`id_slot` 仅探测不依赖 |
| **聊天历史超上下文** | 长会话报错 | 预算截断 + 丢弃旧轮次 + `context_truncated` + 413 兜底 |
| **聊天输出被超时掐断** | 长回复被截 | `CHAT_MAX_OUTPUT_TOKENS=2048` + 超时 180s 配对 |
| **生成时延** | 2.5k 输出约 40–85 秒 | 批目标输出可控；进度按批更新；流式展示 |
| **Q4 质量损失** | 术语与长句准确率下降 | M0 质量基线；术语强制；软指标告警 |
| **6144 输出被截断** | JSON 中途断 | `output_cap` 与 `target_output` 联动；截断计错误码并重试 |
| **显存波动** | OOM 或服务被挤掉 | 实测峰值；按需调 ctx 与槽数 |
| **SSE 经反代被缓冲** | 直连正常、过 Caddy 卡住 | 对 `/api/*` 关 `encode` 或 `flush_interval -1`；M6 用 `curl -N` 验证 |
| **DOCX 段内混合格式丢失** | 观感下降 | 段落级回写 + 报告登记 |
| **openpyxl 往返改变图表/透视** | 业务表格异常 | 保存前后属性对比；明确边界 |
| **PDF 版式无法还原** | 预期落差 | 明确“可读译文”；页面统计报告 |
| **局域网 HTTP 下 PWA 不可安装** | 手机体验打折 | 明说可选；需要时 Caddy 内部 CA 开 HTTPS |
| **Caddy 核心无限流模块** | 限流不可用 | 应用层令牌桶 + 可信 XFF |
| **SQLite 写锁** | 任务卡顿 | WAL + busy_timeout + 单 Worker + 进度节流 |
| **手机后台节流** | 进度看似卡死 | `visibilitychange` 立即刷新 |
| **大文件弱网中断** | 重复劳动 | 前端重试 + 进度；分片上传列阶段 2 |
| **提示词注入** | 模型偏离任务 | 文档区隔、固定契约、无工具权限、输出校验 |
| **单槽争用（parallel 默认 1）** | 翻译批次运行时聊天排队几十秒 | 页面显示“排队中”；M0 实测；显存允许时开 `--parallel 2` |
| **256k 上下文 + mmproj 吃显存** | 余量变小，并发或长上下文易 OOM | 实测峰值；不追求长上下文；必要时降 `-c` |
| **设置页无认证** | 同网段任何人可改模型地址 | 审计 + 可选 `SETTINGS_TOKEN`；文档标注边界 |
| **过早堆组件** | 维护成本 | 严格按 §1.2 “不做”清单 |

---

## 8. 排期

| 里程碑 | 内容 | 人日 | 累计 |
|---|---|---|---|
| M0 | 环境核实与垂直切片 | 2.0 | 2.0 |
| M1 | 后端骨架 + 文件 + 任务入口 + 设置服务 | 3.5 | 5.5 |
| M2 | 队列与 Worker | 2.5 | 8.0 |
| M3 | 四种文档适配器 | 8.5 | 16.5 |
| M4 | 翻译流水线 + Skill + 术语 + 质检 | 4.0 | 20.5 |
| M5 | 前端（流式、停止、附件、动态设置） | 9.0 | 29.5 |
| M6 | 硬化 + 回归 + Ubuntu 部署 | 4.0 | 33.5 |

**MVP 切点**：M0–M4 + 简化前端（上传、进度、下载、非流式聊天，约 3.5 人日）≈ **24.0 人日**（配置先用 API/`.env`，设置页留到 M5）。

**7 周建议节奏**（1 人全职，每周 5 人日）

| 周 | 内容 | 周末可见成果 |
|---|---|---|
| W1 | M0 + M1 | 能上传 DOCX、看到排队任务、状态卡显示模型与槽位 |
| W2 | M2 + M3（DOCX） | 队列可恢复；DOCX 出译文并可下载 |
| W3 | M3（XLSX + 文本 + PDF 起步） | 表格与文本格式可用 |
| W4 | M3（PDF 收尾）+ M4 主体 | 四种格式 CLI 可跑；流水线成型 |
| W5 | M4 收尾 + M5 主体 | 前端主流程可用 |
| W6 | M5 收尾 + M6 起步 | 流式聊天、停止生成、任务详情完善 |
| W7 | M6 | Ubuntu 部署、SSE 验证、备份、文档 |

并行建议：M3 与 M5 可两人并行；M1 的前端壳提前到 W1 降低集成风险。

---

## 9. 立即行动

### 9.1 你说「开始」之后的第一批交付

1. 仓库骨架 + `FakeModelAdapter` + DOCX 端到端冒烟（不需要你的模型）。
2. `scripts/probe_model.py`、`scripts/smoke_docx.py`：你复制到服务器执行，把输出回贴即可。
3. 合成测试样本与 fixture 生成脚本（TXT/MD、加密 PDF、ZIP 炸弹）。

### 9.2 我这边的开发约束

- 不在本机启动 API / Worker / llama-server，不安装运行环境。
- 单元测试只用 `FakeModelAdapter`，不依赖 GPU、网络或你的模型。
- 真实链路的验证全部在你的服务器完成；我按你回贴的输出调默认参数。
- 部署物（systemd、Caddyfile、env 模板、runbook）随代码交付，由你执行。

### 9.3 目标机预期布局

```text
/opt/corefix/app              # 代码
/etc/corefix/env              # 环境变量（600，属主 corefix）
/var/lib/corefix/app.db       # SQLite（WAL）
/var/lib/corefix/storage/     # originals / results / temp / reports
/etc/systemd/system/corefix-api.service
/etc/systemd/system/corefix-worker.service
/etc/caddy/Caddyfile          # :80 静态文件 + /api 反代到 127.0.0.1:8000
```

### 9.4 开工前需要你确认

1. **应用监听地址与端口**（默认 `0.0.0.0:8000`），前面是否再加 Caddy。
2. **模型地址**（默认 `127.0.0.1:8080`）；与 llama.cpp 不同机时给内网地址。
3. **探针回贴**：确认由你在服务器执行脚本。

---

## 10. 附录：M0 环境记录模板

```markdown
# 阶段 0 环境记录

## 机器
- 系统 / 内核：            CPU / 内存：
- GPU 型号 / 显存：        nvidia-smi 空闲显存：
- Python / Node 版本：
- 磁盘：/var/lib 可用空间

## llama.cpp
- 版本 / 构建号：          最低支持 qwen35 的版本：
- 完整启动命令：
- --jinja 是否开启：           模板渲染是否正常：
- --chat-template-kwargs 是否被接受：       失败现象：
- --parallel / 实际槽位：       每槽 ctx：
- mmproj 是否加载：       视觉编码器显存占用：
- KV 实测是否 ≈ 4 GiB（262144 × 16 KiB）：
- {ROOT}/props：total_slots=        default_generation_settings.n_ctx=（每槽值）
- {ROOT}/slots：slot0.n_ctx=        slot1.n_ctx=
- 与 --ctx-size / --parallel 是否吻合：        差异说明：
- 模型别名：                  GGUF 量化类型：
- KV cache 类型：             是否开启 flash-attn：
- /health 就绪耗时：
- response_format=json_object：         json_schema：
- thinking 开：输出形态=
- thinking 关：输出形态=         是否仍有 think 标签或 reasoning_content：
- 500 字中文：首 token 延迟=        总耗时=        tok/s=
- 并发 1 / 2 请求耗时对比：
- 断连释放：发起流式请求后断开，槽位释放耗时=        秒
- 实测显存峰值（当前 ctx）：
- /tokenize 校准：中文 1 字 ≈         token；英文 1 词 ≈         token

## 推荐批预算（据实测填写）
- slot_ctx =        output_cap =        target_output =
- text_budget =        prompt_est =        PROMPT_OVERHEAD_TOKENS =
- 每批最大字符数（粗切）=

## Q4 质量基线
- 20 段样本：术语错误数=        长句问题=        数字/占位符异常=

## 验证结果
- [ ] 10 段 DOCX 翻译并写回，文件可打开
- [ ] thinking 关闭后无 think 标签，JSON 可解析
- [ ] XLSX 往返后公式哈希一致
- [ ] PDF 提取块数与页文本统计正常
- [ ] 加密 PDF 落到 encrypted_document
- [ ] 取消 / 重启后任务状态正确
- [ ] 停止生成后 5 秒内槽位释放
- [ ] 从另一台内网机器访问 8080 被拒绝
- [ ] 设置页改采样后新任务生效、在途任务不变

## 已知限制
-
```
