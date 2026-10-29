# 葡萄膜炎辅助诊断智能系统

Qwen3.5-4B 微调判断 + 可选 RAG、决策模型、网络搜索和外部 API 总结，所有增强组件均可独立降级；FastAPI + React 三端系统（公开端 / 医生端 / 管理员端）。项目性质：非商用科研原型，输出仅作辅助参考、不构成诊断。

## 目录结构

```text
uveitis-project/
├── README.md                  本文件
├── docs/2026-10-26-project-layout.html 项目目录索引
├── docs/                      项目文档与训练记录
│   ├── index.html              浏览器文档入口
│   ├── 2026-10-26-model-training-status.html 当前训练状态
│   ├── 2026-10-25-training-cost-ledger-modal.html  Modal 训练消耗与结果
│   ├── 2026-10-25-training-budget-plan-modal-l40s.html 训练预算计划
│   └── 2026-10-26-model-runtime-evaluation.html 评估与推理说明
├── qwen3.5-4b/                Qwen3.5-4B 模型运行服务（FastAPI）
│   ├── app/                   判断 API 与健康检查
│   ├── code/                  本地评估代码
│   ├── scripts/               运行脚本
│   ├── assets/                运行资产索引与冻结契约
│   └── models/                基座与最终 adapter（gitignore）
├── bge-m3/                    BGE-M3 向量模型服务（FastAPI）
│   ├── app/                   向量 API 与健康检查
│   └── models/                BGE-M3 权重（gitignore）
├── model/                     模型训练统一目录
│   └── training/              模型训练统一管理入口
│       ├── code/training/     Qwen QLoRA 和 Modal 训练代码
│       ├── scripts/modal/     训练子集与 Volume 同步脚本
│       ├── datasets/raw/      新下载压缩包的临时暂存区
│       ├── datasets/extracted/ 完整解压数据集与 manifests/ 清单
│       ├── datasets/training/  训练数据与 manifest
│       └── assets/             训练产物与评估快照
├── outputs/                   临时运行输出说明
├── scripts/
│   ├── datasets/              数据集清单校验与维护脚本
│   └── research/              浏览器检索脚本存档（.mjs，按任务日期归档）
├── backend/                   FastAPI 业务服务
├── frontend/                  React 三端
└── ai-services/              预留的 AI 服务扩展目录
```

## 当前状态（2026-10-28）

目标工程收口日期：**2026-11-10**。统一跟踪见 `docs/2026-10-26-progress-tracking.html`；项目开发进度见 `docs/2026-10-26-project-development-progress.html`，模型训练进度见 `docs/2026-10-26-model-training-progress.html`。

部署、容器验收、生产发布和回滚暂时移出 11.10 主计划，后续单独排期；本期继续保留本地运行服务、业务回写、失败恢复、页面收口和文档冻结。

- [x] 数据集调研：国内开源眼科数据集梳理、许可逐项核验（见 docs/ 调研文档）
- [x] 项目计划书与模型训练计划书（v1.0，12 周里程碑 A–E 训练方案）
- [x] 葡萄膜炎 OCT 75 图、五分类 2,298 图、ToxoFundus 592 文件下载并校验
- [x] 数据集已重新下载、解压并整理（2026-10-25），索引见 `docs/2026-10-26-dataset-index.html`
- [x] 训练结果快照已按 run 和评估阶段归档，索引见 `docs/2026-10-26-training-assets-index.html`
- [x] M1 前后端基础框架：病例建档、影像上传、分析任务、医生复核、管理概览
- [x] 鉴权与权限体系：唯一 `root` 管理员、管理员开户医生、禁止自助注册、双令牌无感刷新、CSRF、登录限流与审计；见 `docs/2026-10-26-auth-access-control.html` 和 `docs/2026-10-27-auth-account-provisioning.html`
- [x] PostgreSQL 病例、账号、审计与服务配置持久化
- [x] 核心模型适配边界与演示模式
- [x] zvec 嵌入式知识库适配层：文档写入、过滤检索与本地持久化
- [x] BGE-M3 通过 ModelScope 下载到 `bge-m3`，以独立 FastAPI 服务提供 1024 维向量
- [x] zvec 检索通过接口调用独立 BGE-M3 向量服务，管理端展示向量数据库状态
- [x] 混合判断编排：Qwen 判断、RAG、补充决策、网络搜索和外部总结均为可跳过增强分支
- [x] Qwen3.5-4B 最终训练产物（基座、第 20 步 best_adapter、冻结契约）收拢到 `qwen3.5-4b/` 包内；训练数据集与中间态权重已清理，manifests 台账与指标证据保留
- [x] 项目目录完成训练资产、运行服务和项目文档归类；索引见 `docs/2026-10-26-project-layout.html`
- [x] 前端首轮工作区界面完善：桌面/移动端导航、账号权限概览、账号列表移动卡片化和权限页空状态
- [x] 完成患者首页、病例详情、管理员概览、登录与状态页的统一视觉收口
- [ ] 完成真实模型与辅助功能的本地端到端回归，包括结果回写、超时、降级和失败恢复
- [ ] 完成 11.10 前工程验收：本地端到端流程、移动端检查、模型运行集成和文档冻结
- [ ] 决策模型补充路径：根据项目进度、真实标注与评测结果决定是否启用
- [ ] 部署、容器验收、生产发布和回滚：暂时移出 11.10 主计划，后续单独排期

## 使用说明

- HTML 文档统一从 `docs/index.html` 进入；文件名采用 `YYYY-MM-DD-kebab-case.html`。
- 模型训练统一从站点内的“模型训练管理”页或 `model/training/README.md` 管理；训练任务、数据入口和产物入口都从这里查找。
- 模型运行、评估与部署统一从站点内的“模型运行服务”页或 `qwen3.5-4b/README.md` 管理；向量模型服务统一见 `bge-m3/README.md`。
- 鉴权、角色权限、账号维护和会话安全统一见 [`2026-10-26-auth-access-control.html`](docs/2026-10-26-auth-access-control.html) 与 [`2026-10-27-auth-account-provisioning.html`](docs/2026-10-27-auth-account-provisioning.html)。
- 本页 HTML 版本为 [`2026-10-26-project-overview.html`](docs/2026-10-26-project-overview.html)。
- 文档总索引：[`docs/index.html`](docs/index.html)。
- 系统操作手册（前置条件、登录、医生工作流、管理员操作、常见问题）已并入本 README。
- 专题文档统一使用 HTML；除目录级 `README.md` 外，不保留专题 Markdown。重建与校验命令为 `.\model\training\.venv-modal\Scripts\python.exe scripts\docs\build_docs.py`。
- 数据集重新下载后先放 `model/training/datasets/raw/`；解压、核验后按 `model/training/datasets/extracted/<数据集名>/` 组织，并清理已展开的临时 ZIP。
- 训练评估和验证快照放入 `model/training/assets/qwen3.5-4b/<run-id>/`；最终运行产物（基座、best_adapter、冻结契约）在 `qwen3.5-4b/` 包内，训练数据集与中间态产物验收后可整体清理；完整 adapter 和优化器状态仍以 Modal `uveitis-runs` 为真相源。
- 训练子集位于 `model/training/datasets/training/`；逐文件数据清单位于 `model/training/datasets/extracted/manifests/`，已删除归档的来源账本也在那里。
- 检索脚本仅供归档复用，运行方式见各子目录内 round-*.mjs（ego-browser 环境）。

## 前置条件

| 项 | 要求 |
|---|---|
| GPU | NVIDIA RTX 4060（8 GB）或更高；真实模型推理需要 CUDA 版 PyTorch |
| 数据库 | PostgreSQL 16（必填），Redis（用于会话与队列） |
| Python | 3.12+，后端依赖在 `backend/.venv`，运行服务依赖在 `.venv-runtime-smoke` |
| Node.js | 18+，前端依赖在 `frontend/node_modules` |
| 模型文件 | Qwen3.5-4B 基座和 adapter 在 `qwen3.5-4b/models/`，向量模型权重在 `bge-m3/models/bge-m3/`；训练数据集与中间态产物已清理，不影响运行 |

## 本地启动

向量模型服务（可选；知识检索使用时先启动再让后端连接）：

```powershell
cd bge-m3
uv venv .venv
uv pip install --python .venv\Scripts\python.exe --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
$env:EMBEDDING_INTERNAL_TOKEN = 'replace-with-shared-token'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

模型运行服务（可选；先启动再让后端连接）：

```powershell
cd qwen3.5-4b
$env:MODEL_RUNTIME_UPLOAD_ROOT = (Resolve-Path '..\backend\data\uploads').Path
..\.venv-runtime-smoke\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

后端（Windows PowerShell）：

```powershell
cd backend
uv sync --group dev --cache-dir .uv-cache
Copy-Item .env.example .env
docker compose up -d postgres redis
.\.venv\Scripts\uvicorn.exe app.asgi:app --reload --host 127.0.0.1 --port 8000
```

分析任务会先写入 PostgreSQL 的 `t_analysis_job`，再由 Web 进程和独立 worker 共享租约领取。只启动 Web 进程时任务仍可执行；生产环境建议同时启动 worker：

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

Docker Compose 已包含 `analysis-worker` 服务。任务默认 300 秒租约、最多尝试 2 次；Web 或 worker 重启后，过期租约会被回收并重新排队，不会永久停留在“分析中”。

任务使用 `f_job_key` 作为业务标识，执行前校验租约持有者和有效期；非持有者不能重复执行。病例已经生成完整分析结果时，任务重试只补齐完成状态，不会再次调用分析服务。任务队列的契约、验收证据和剩余边界见 [`2026-10-27-analysis-job-queue.html`](docs/2026-10-27-analysis-job-queue.html)。

真实模型运行要求后端与运行服务共享病例上传根目录。Docker Compose 使用 `case-uploads` 卷，后端和 worker 可写、模型服务只读；本机启动时设置 `APP_DATA_DIR`、`MODEL_RUNTIME_UPLOAD_ROOT` 和相同的 `APP_INTERNAL_SERVICE_TOKEN`。本地 Qwen 冷启动与推理合计可能超过 45 秒，后端默认 `APP_PERCEPTION_TIMEOUT_SECONDS=90`。真实回写和资源证据见 [`2026-10-27-model-runtime-business-integration.html`](docs/2026-10-27-model-runtime-business-integration.html)。

后端只使用 PostgreSQL 持久化；`APP_DATABASE_URL` 未配置或数据库不可达时启动失败，不会回落到 SQLite。`APP_DATABASE_CONNECT_TIMEOUT_SECONDS` 默认 5 秒。`app.main:create_app` 是应用工厂，ASGI 启动入口为 `app.asgi:app`。数据库表和字段统一使用 `t_${业务名}`、`f_${业务名}`；每张表使用 `f_id BIGINT` 自增主键，API 和跨表引用使用独立的唯一业务键。管理员账号固定为 `root`，`APP_BOOTSTRAP_ADMIN_PASSWORD` 只在首次创建 root 时使用；root 已存在后，重启和应用层操作都不会覆盖密码，唯一变更方式是直接修改 `t_data_dictionary` 中的加密哈希记录。医生账号只能由管理员创建，系统不提供注册入口。管理员和医生分别从 `/admin/login`、`/login` 进入，两个入口在服务端分别校验角色。

前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。API 文档位于 `http://127.0.0.1:8000/docs`。

默认 `APP_MODEL_MODE=mock`，只验证业务链路，不生成临床结论。核心路径先完成病例结构化、影像理解、证据检索与医生复核；接入相应服务后切换为 `remote`。补充决策模型由 `APP_DECISION_ENABLED=false` 默认关闭，不作为核心流程的前置条件。

## 登录

| 角色 | 入口 | 说明 |
|---|---|---|
| 医生 | `http://127.0.0.1:5173/login` | 账号由管理员创建；首次登录后可修改密码 |
| 管理员 | `http://127.0.0.1:5173/admin/login` | 用户名固定为 `root`，密码只能通过修改 `t_data_dictionary` 中的加密哈希变更 |

系统不提供自助注册。医生会话为双 Token 无感刷新（15 分钟 access + 30 天 refresh）；管理员会话为单一 10 分钟短期令牌，每次操作成功后自动续期。

## 医生工作流

创建病例：

1. 进入病例页，点击新建病例。
2. 填写患者年龄、性别、受累眼和主诉。
3. 上传 OCT 或眼底影像（JPG/PNG，最大 25 MB）。
4. 勾选数据授权确认，点击提交。

辅助分析：

1. 进入病例详情，切换到辅助分析标签。
2. 点击启动辅助分析。系统按 intake → planning → preprocess → Qwen 判断 → 检索 → 安全复核 → 报告的顺序执行。
3. 真实推理冷启动约 22 秒，热请求约 3.4 秒，页面自动轮询任务状态。
4. 分析完成后病例进入待复核状态。

医生复核：

1. 在病例详情的复核标签中审阅分析结果。
2. 填写复核决定（接受/修改/拒绝）、最终印象和备注。
3. 提交后病例状态变为已复核。模型输出不会自动成为诊断，必须经医生确认。

报告：在报告标签中查看医生确认后的结构化报告，只展示医生确认的内容，刷新页面后状态不丢失。

## 管理员操作

账号管理（账号权限页）：

1. 点击创建医生账号，输入用户名、显示名和密码（至少 12 位）。
2. 停用账号后该账号所有会话立即失效。
3. 重置密码后旧会话全部撤销，旧密码不可再登录。

服务配置（服务配置页）：

1. 配置外部总结 API，支持 OpenAI Responses、OpenAI Chat Completions 和 Anthropic Messages 三种协议。
2. 配置网络搜索服务商（Tavily、Brave、Serper 等 8 家），可调整尝试顺序并逐项启用/禁用。
3. 点击检查连接验证凭据可用性；API Key 加密只写不回显，保存后立即作用于后端调用链。

知识库管理（知识库页）：

1. 上传临床指南或文献（分类 guideline / literature / case / other）。
2. 向量由独立 BGE-M3 服务（端口 8011）提供，权重在首次检索时加载并常驻内存。
3. 辅助分析通过 RAG 检索命中条目并注入结果；服务不可用时检索分支自动跳过。

活跃会话审计：在账号权限页下方查看当前在线账号的角色、登录 IP、最近活跃和过期时间。

## 停止服务

```powershell
Get-NetTCPConnection -LocalPort 8000,5173,8010,8011 | ForEach-Object { Stop-Process -Id $_.OwningProcess }
```

PostgreSQL 和 Redis 是 Docker Compose 容器，执行 `docker compose down` 停止。

## 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 后端启动报 `APP_DATABASE_URL` 错误 | PostgreSQL 未启动或连接配置缺失 | 先启动数据库，确认 `backend/.env` 中 `APP_DATABASE_URL` 正确 |
| 分析时 Qwen 判断阶段返回 403 | 模型运行服务的 `MODEL_RUNTIME_UPLOAD_ROOT` 未指向后端上传目录 | 重启模型服务并设置 `MODEL_RUNTIME_UPLOAD_ROOT` 为 `backend/data/uploads` 绝对路径 |
| 分析长时间卡在排队 | Worker 未启动且 Web 进程任务处理较慢 | 启动独立 Worker：`python -m app.worker` |
| 页面提示"请先登录" | Access 令牌已过期且刷新令牌不可用 | 重新登录即可；医生令牌过期时前端会自动刷新 |
| 管理员端刷新返回 401 | 管理员短期令牌 10 分钟超时 | 重新登录；使用期间系统自动续期，通常不会触发 |
| 模型推理超时 | 冷启动加载时间较长 | 后端默认等待 `APP_PERCEPTION_TIMEOUT_SECONDS=90`；服务恢复后重新分析 |

## 混合判断链路

`APP_MODEL_MODE=remote` 后，病例分析按以下顺序运行，每个增强组件都有独立超时和异常边界：

```text
病例结构化 -> 影像预处理
  -> AgentScope 工具链规划（可选）
  -> Qwen3.5-4B 微调判断（可选）
  -> RAG 证据检索（可选）
  -> 补充决策模型（可选）
  -> 网络搜索辅助（可选）
  -> 外部 API 总结（可选）
  -> 安全校验 -> 报告整理 -> 医生复核
```

- Qwen3.5-4B 只输出受限标签、结构化发现和置信度，不生成最终临床报告。
- 原始病例和影像只允许发送到项目自有的本地或受控内网模型服务；统一 HTTP 出站钩子会阻止公开主机接收这类数据。
- RAG 使用 `bge-m3` 的 BGE-M3 向量服务和 zvec 索引；索引为空、服务不可用或检索失败时直接跳过。
- 网络搜索支持 Tavily、Brave Search、Serper、Google Programmable Search (CSE)、Bing Web Search、Exa、Perplexity 和自建 SearXNG；管理员可调整尝试顺序并逐项检查，单个提供方失败后继续下一个，全部失败只跳过搜索分支。搜索词只使用模型标签和固定医学检索词，绝不包含主诉、病史、病例标识或影像信息。
- 补充决策模型保持默认关闭，待真实脱敏病例、医生确认标签和独立评测齐备后启用。
- 工具链规划由 AgentScope 承担：规划代理只决定本次运行哪些可选技能，执行顺序、超时与失败处理仍由后端确定性代码控制。规划关闭、依赖缺失、凭据不完整或规划失败时回退到确定性顺序，病例分析照常完成。细则见 [AgentScope 工具链编排](docs/2026-10-27-agent-toolchain-plan.html)。
- 外部总结支持 OpenAI Responses、OpenAI Chat Completions 和 Anthropic Messages 三种接口，调用时使用管理员在服务配置页保存的地址、模型与密钥。外发载荷按字段白名单构造，只包含模型标签、置信度和检索证据；原始影像、病例字段和未受控的自由文本绝不外发。不可用时使用确定性回退摘要。
- 外部服务配置由管理员维护；医生只能读取是否启用，不能读取或修改凭据。API Key 使用 AES-GCM 加密保存，接口响应只返回“是否已配置”，永不回传原文。
- 外部 HTTP 请求在执行前经过 `httpx` 请求钩子复核：第三方总结、搜索和规划链路默认禁止病例或影像字段，项目自有模型端点也必须通过受控主机检查。
- 任一增强组件失败都只写 `failed` 或 `skipped`，病例仍进入 `awaiting_review`，不会阻断医生复核。

外部服务的操作性配置在管理端“服务配置”页维护，包括接口协议、API 地址、模型、密钥和搜索服务商顺序。系统不提供“发送病例文本”或“发送影像”开关，隐私边界由代码强制校验。运行时始终读取数据库中的管理员配置，不把环境变量作为外部 API 或网络搜索的运营配置入口；部署文件只保留启动主密钥 `APP_INTEGRATION_SECRET_KEY`。不要将第三方 API Key 提交到仓库。环境变量样例位于仓库的 `backend/.env.example`。外部 API 启用前需要完成数据处理和合规评估；项目 MIT License 只覆盖代码，不覆盖第三方数据、影像、模型权重或外部 API 内容。

## 向量模型服务（BGE-M3）

BGE-M3 统一在 `bge-m3/` 作为独立 FastAPI 服务运行，默认端口 `8011`；backend 不再内嵌模型权重，只通过 `APP_RETRIEVAL_SERVICE_URL` 获取向量。权重通过 ModelScope 固定来源 `BAAI/bge-m3` 下载到 `bge-m3/models/bge-m3/`（约 2.3 GB，已加入 `.gitignore`）：

```powershell
.\backend\.venv\Scripts\python.exe -c "from modelscope.hub.snapshot_download import snapshot_download; snapshot_download('BAAI/bge-m3', local_dir='bge-m3/models/bge-m3')"
```

服务首次收到向量化请求时加载权重并常驻 CPU，`GET /health` 不触发加载。默认配置如下：

```dotenv
APP_VECTOR_PROVIDER=remote
APP_RETRIEVAL_SERVICE_URL=http://127.0.0.1:8011
```

设置 `APP_INTERNAL_SERVICE_TOKEN` 后，backend 与向量服务之间使用 `X-Internal-Service-Token` 头。接口契约、环境变量与本地启动方式见 `bge-m3/README.md`。

## 知识检索

向量数据库选用 [zvec](https://github.com/alibaba/zvec)，作为嵌入式本地索引运行在 backend 进程内。BGE-M3 由独立的 `bge-m3` FastAPI 服务提供向量，zvec 负责向量的持久化、HNSW 检索和标量过滤。默认索引目录为 `backend/data/zvec/`，集合名为 `uveitis_knowledge`，维度为 1024。

- `POST /api/v1/knowledge/documents`：写入知识文档。可以传 `vector`；未传时使用当前 embedding provider。
- `POST /api/v1/knowledge/search`：按文本或向量检索，支持 `category` 过滤。
- `GET /api/v1/knowledge/status`：查看 zvec 集合、文档数和向量维度。

`APP_VECTOR_PROVIDER=remote` 调用 `bge-m3` 服务。`memory` 只用于无模型的链路测试，确定性哈希向量不具备语义检索质量。切换 embedding provider 后不要复用旧集合的向量，应重建 zvec 索引，避免不同向量空间混检。zvec 集合默认按单写进程使用，生产部署不要让多个 Uvicorn worker 同时写同一集合。

## 补充决策模型

`Intern-Decision-4B` 与 `Kev-4B` 属于可选补充方案，不作为第一阶段核心链路的一部分。在真实脱敏病例、医生确认的决策标签、独立测试集和稳定评测结果齐备前，保持 `APP_DECISION_ENABLED=false`。

```dotenv
APP_DECISION_ENABLED=false
APP_DECISION_SERVICE_URL=
```

达到启用门槛后，再配置决策服务地址并设置 `APP_DECISION_ENABLED=true`。管理端会区分核心模型与补充模型；未启用时分析记录明确标记为“跳过”，流程直接进入安全校验与医生复核。决策模型只能提供补充建议，最终结论仍由医生复核。

## 开源协议

本项目采用 MIT License，详见 [LICENSE](https://github.com/zikdjh/uveitis-project/blob/main/LICENSE)。
