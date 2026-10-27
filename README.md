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
├── model-runtime/             模型运行服务、评估与部署入口
│   ├── app/                   模型健康检查 API
│   ├── code/                  本地评估代码
│   ├── scripts/               运行脚本
│   └── assets/                运行资产索引
├── model-training/            模型训练统一管理入口
│   ├── code/training/         Qwen QLoRA 和 Modal 训练代码
│   ├── scripts/modal/         训练子集与 Volume 同步脚本
│   ├── datasets/raw/          新下载压缩包的临时暂存区
│   ├── datasets/extracted/    完整解压数据集与 manifests/ 清单
│   ├── datasets/training/     训练数据与 manifest
│   ├── models/                Qwen 基座
│   └── assets/                训练产物与评估快照
├── outputs/                   临时运行输出说明
├── scripts/
│   ├── datasets/              数据集清单校验与维护脚本
│   └── research/              浏览器检索脚本存档（.mjs，按任务日期归档）
├── backend/                   FastAPI 业务服务
├── frontend/                  React 三端
└── ai-services/              预留的 AI 服务扩展目录
```

## 当前状态（2026-10-27）

目标工程收口日期：**2026-11-10**。统一跟踪见 `docs/2026-10-26-progress-tracking.html`；项目开发进度见 `docs/2026-10-26-project-development-progress.html`，模型训练进度见 `docs/2026-10-26-model-training-progress.html`。

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
- [x] BGE-M3 通过 ModelScope 下载到本地，使用 CPU 生成 1024 维向量
- [x] zvec 检索使用本地 BGE-M3，管理端展示向量数据库状态
- [x] 混合判断编排：Qwen 判断、RAG、补充决策、网络搜索和外部总结均为可跳过增强分支
- [x] 项目目录完成训练资产、运行服务和项目文档归类；索引见 `docs/2026-10-26-project-layout.html`
- [x] 前端首轮工作区界面完善：桌面/移动端导航、账号权限概览、账号列表移动卡片化和权限页空状态
- [ ] 完成患者首页、病例详情、管理员概览、登录与状态页的统一视觉收口
- [ ] 将模型运行 API 从健康检查接入完整影像推理链路
- [ ] 完成 11.10 前工程验收：端到端流程、移动端检查、模型运行集成和文档冻结
- [ ] 决策模型补充路径：根据项目进度、真实标注与评测结果决定是否启用

## 使用说明

- HTML 文档统一从 `docs/index.html` 进入；文件名采用 `YYYY-MM-DD-kebab-case.html`。
- 模型训练统一从站点内的“模型训练管理”页或 `model-training/README.md` 管理；训练任务、数据入口和产物入口都从这里查找。
- 模型运行、评估与部署统一从站点内的“模型运行服务”页或 `model-runtime/README.md` 管理。
- 鉴权、角色权限、账号维护和会话安全统一见 [`2026-10-26-auth-access-control.html`](docs/2026-10-26-auth-access-control.html) 与 [`2026-10-27-auth-account-provisioning.html`](docs/2026-10-27-auth-account-provisioning.html)。
- 本页 HTML 版本为 [`2026-10-26-project-overview.html`](docs/2026-10-26-project-overview.html)。
- 文档总索引：[`docs/index.html`](docs/index.html)。
- 专题文档统一使用 HTML；除目录级 `README.md` 外，不保留专题 Markdown。重建与校验命令为 `.\model-training\.venv-modal\Scripts\python.exe scripts\docs\build_docs.py`。
- 数据集重新下载后先放 `model-training/datasets/raw/`；解压、核验后按 `model-training/datasets/extracted/<数据集名>/` 组织，并清理已展开的临时 ZIP。
- 训练评估和验证快照放入 `model-training/assets/qwen3.5-4b/<run-id>/`；模型运行与评估入口统一在 `model-runtime/`；完整 adapter 和优化器状态仍以 Modal `uveitis-runs` 为真相源。
- 训练子集位于 `model-training/datasets/training/`；逐文件数据清单位于 `model-training/datasets/extracted/manifests/`，已删除归档的来源账本也在那里。
- 检索脚本仅供归档复用，运行方式见各子目录内 round-*.mjs（ego-browser 环境）。

## 本地启动

模型运行服务（可选；先启动再让后端连接）：

```powershell
cd model-runtime
$env:MODEL_RUNTIME_UPLOAD_ROOT = (Resolve-Path '..\model-training\datasets\training').Path
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

后端只使用 PostgreSQL 持久化；`APP_DATABASE_URL` 未配置或数据库不可达时启动失败，不会回落到 SQLite。`APP_DATABASE_CONNECT_TIMEOUT_SECONDS` 默认 5 秒。`app.main:create_app` 是应用工厂，ASGI 启动入口为 `app.asgi:app`。数据库表和字段统一使用 `t_${业务名}`、`f_${业务名}`。管理员账号固定为 `root`，`APP_BOOTSTRAP_ADMIN_PASSWORD` 只在首次创建 root 时使用；root 已存在后，重启和应用层操作都不会覆盖密码，唯一变更方式是直接修改 `t_data_dictionary` 中的加密哈希记录。医生账号只能由管理员创建，系统不提供注册入口。管理员和医生分别从 `/admin/login`、`/login` 进入，两个入口在服务端分别校验角色。

前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。API 文档位于 `http://127.0.0.1:8000/docs`。

默认 `APP_MODEL_MODE=mock`，只验证业务链路，不生成临床结论。核心路径先完成病例结构化、影像理解、证据检索与医生复核；接入相应服务后切换为 `remote`。补充决策模型由 `APP_DECISION_ENABLED=false` 默认关闭，不作为核心流程的前置条件。

## 混合判断链路

`APP_MODEL_MODE=remote` 后，病例分析按以下顺序运行，每个增强组件都有独立超时和异常边界：

```text
病例结构化 -> 影像预处理
  -> Qwen3.5-4B 微调判断（可选）
  -> RAG 证据检索（可选）
  -> 补充决策模型（可选）
  -> 网络搜索辅助（可选）
  -> 外部 API 总结（可选）
  -> 安全校验 -> 报告整理 -> 医生复核
```

- Qwen3.5-4B 只输出受限标签、结构化发现和置信度，不生成最终临床报告。
- RAG 使用本地 BGE-M3 和 zvec；索引为空、模型缺失或检索失败时直接跳过。
- 网络搜索支持 Tavily、Brave Search、Serper、Google Programmable Search (CSE)、Bing Web Search、Exa、Perplexity 和自建 SearXNG；管理员可调整尝试顺序并逐项检查，单个提供方失败后继续下一个，全部失败只跳过搜索分支。默认不把主诉发送给外部搜索。
- 补充决策模型保持默认关闭，待真实脱敏病例、医生确认标签和独立评测齐备后启用。
- 外部总结支持 OpenAI Responses、OpenAI Chat Completions 和 Anthropic Messages 三种接口，调用时使用管理员在服务配置页保存的地址、模型与密钥；默认不发送原始影像、主诉和病史，不可用时使用确定性回退摘要。
- 外部服务配置由管理员维护；医生只能读取是否启用，不能读取或修改凭据。API Key 使用 AES-GCM 加密保存，接口响应只返回“是否已配置”，永不回传原文。
- 任一增强组件失败都只写 `failed` 或 `skipped`，病例仍进入 `awaiting_review`，不会阻断医生复核。

外部服务的操作性配置在管理端“服务配置”页维护，包括接口协议、API 地址、模型、密钥、搜索服务商顺序和临床文本发送开关。运行时始终读取数据库中的管理员配置，不把环境变量作为外部 API 或网络搜索的运营配置入口；部署文件只保留启动主密钥 `APP_INTEGRATION_SECRET_KEY`。不要将第三方 API Key 提交到仓库。环境变量样例位于仓库的 `backend/.env.example`。外部 API 启用前需要完成数据处理和合规评估；项目 MIT License 只覆盖代码，不覆盖第三方数据、影像、模型权重或外部 API 内容。

## 本地 BGE-M3

模型通过 ModelScope 固定来源 `BAAI/bge-m3` 下载到 `backend/models/bge-m3/`。该目录已加入 `.gitignore`，不随代码提交。首次启动 API 时不加载模型，第一次写入知识或执行文本检索时才加载权重并常驻 CPU。

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from modelscope.hub.snapshot_download import snapshot_download; snapshot_download('BAAI/bge-m3', local_dir='models/bge-m3')"
```

推理依赖包括 CPU 版 `torch`、`torchvision`、`modelscope` 和 `FlagEmbedding`。默认配置如下：

```dotenv
APP_VECTOR_PROVIDER=local
APP_BGE_M3_MODEL_PATH=models/bge-m3
APP_BGE_M3_BATCH_SIZE=8
APP_BGE_M3_MAX_LENGTH=1024
```

本地提供者固定使用 `devices=["cpu"]`、`use_fp16=False` 和稠密 `dense_vecs`。默认只会使用最多 8 个 PyTorch CPU 线程。模型首次加载需要数秒到数十秒；后续请求复用已加载权重。

## 知识检索

向量数据库选用 [zvec](https://github.com/alibaba/zvec)，作为嵌入式本地索引运行在 FastAPI 进程内。BGE-M3 负责将知识文档和查询转换为向量，zvec 负责向量的持久化、HNSW 检索和标量过滤。默认索引目录为 `backend/data/zvec/`，集合名为 `uveitis_knowledge`，维度为 1024。

- `POST /api/v1/knowledge/documents`：写入知识文档。可以传 `vector`；未传时使用当前 embedding provider。
- `POST /api/v1/knowledge/search`：按文本或向量检索，支持 `category` 过滤。
- `GET /api/v1/knowledge/status`：查看 zvec 集合、文档数和向量维度。

`APP_VECTOR_PROVIDER=local` 使用本地 CPU BGE-M3。`memory` 只用于无模型的链路测试，确定性哈希向量不具备语义检索质量；`remote` 则调用 `APP_RETRIEVAL_SERVICE_URL`。切换 embedding provider 后不要复用旧集合的向量，应重建 zvec 索引，避免不同向量空间混检。zvec 集合默认按单写进程使用，生产部署不要让多个 Uvicorn worker 同时写同一集合。

## 补充决策模型

`Intern-Decision-4B` 与 `Kev-4B` 属于可选补充方案，不作为第一阶段核心链路的一部分。在真实脱敏病例、医生确认的决策标签、独立测试集和稳定评测结果齐备前，保持 `APP_DECISION_ENABLED=false`。

```dotenv
APP_DECISION_ENABLED=false
APP_DECISION_SERVICE_URL=
```

达到启用门槛后，再配置决策服务地址并设置 `APP_DECISION_ENABLED=true`。管理端会区分核心模型与补充模型；未启用时分析记录明确标记为“跳过”，流程直接进入安全校验与医生复核。决策模型只能提供补充建议，最终结论仍由医生复核。

## 开源协议

本项目采用 MIT License，详见 [LICENSE](https://github.com/zikdjh/uveitis-project/blob/main/LICENSE)。
