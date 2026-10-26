# 葡萄膜炎辅助诊断智能系统

开源多模态模型 + 专项训练 + RAG 知识增强，决策模型作为按进度启用的补充方案；FastAPI + React 三端系统（公开端 / 医生端 / 管理员端）。项目性质：非商用科研原型，输出仅作辅助参考、不构成诊断。

## 目录结构

```text
uveitis-project/
├── README.md                  本文件
├── PROJECT_LAYOUT.md          当前目录、占用和清理说明
├── docs/                      项目文档与训练记录
│   ├── index.html              浏览器文档入口
│   ├── 2026-10-25-training-cost-ledger-modal.html  Modal 训练消耗与结果
│   └── 2026-10-25-training-budget-plan-modal-l40s.html 训练预算计划
├── datasets/                  数据集存放区
│   ├── raw/                   新下载压缩包的临时暂存区
│   ├── extracted/             完整解压数据集与 manifests/ 清单
│   └── training/              Modal 训练精简包、标签与 manifest
├── artifacts/                 本地训练结果快照和参考材料
│   └── qwen3.5-4b/            训练产物的物理目录，经 model-training/artifacts 链接访问
├── model-training/            模型训练统一管理入口
│   ├── code/training/         Qwen QLoRA、评估和 Modal Volume 代码
│   ├── scripts/modal/         训练子集与 Volume 同步脚本
│   ├── docs/                  训练计划、预算和消耗记录
│   ├── data/training/         训练数据的物理目录，经 model-training/data 链接访问
│   └── artifacts/             本地产物入口
├── outputs/                   临时运行输出，稳定结果归档到 artifacts/
├── scripts/
│   ├── datasets/              数据集清单校验与维护脚本
│   └── research/              浏览器检索脚本存档（.mjs，按任务日期归档）
├── backend/                   FastAPI 业务服务
├── frontend/                  React 三端
└── ai-services/
    ├── training/              模型训练代码与配置
    ├── inference/             推理服务（vLLM 部署）
    └── rag-kb/                RAG 知识库构建与检索
```

## 当前状态（2026-10-25）

- [x] 数据集调研：国内开源眼科数据集梳理、许可逐项核验（见 docs/ 调研文档）
- [x] 项目计划书与模型训练计划书（v1.0，12 周里程碑 A–E 训练方案）
- [x] 葡萄膜炎 OCT 75 图、五分类 2,298 图、ToxoFundus 592 文件下载并校验
- [x] 数据集已重新下载、解压并整理（2026-10-25），索引见 `docs/2026-10-25-dataset-index.html`
- [x] 训练结果快照已按 run 和评估阶段归档，索引见 `docs/2026-10-25-artifacts-index.html`
- [x] M1 前后端基础框架：病例建档、影像上传、分析任务、医生复核、管理概览
- [x] SQLite 病例持久化与本地影像存储
- [x] 核心模型适配边界与演示模式
- [x] zvec 嵌入式知识库适配层：文档写入、过滤检索与本地持久化
- [x] BGE-M3 通过 ModelScope 下载到本地，使用 CPU 生成 1024 维向量
- [x] zvec 检索使用本地 BGE-M3，管理端展示向量数据库状态
- [ ] 接入 Qwen3.5-4B 推理服务
- [ ] 决策模型补充路径：根据项目进度、真实标注与评测结果决定是否启用

## 使用说明

- HTML 文档统一从 `docs/index.html` 进入；文件名采用 `YYYY-MM-DD-kebab-case.html`。
- 模型训练统一从站点内的“模型训练管理”页或 `model-training/README.md` 管理；训练任务、数据入口和产物入口都从这里查找。
- 本页 HTML 版本为 [`2026-10-25-project-overview.html`](2026-10-25-project-overview.html)。
- 文档总索引：[`docs/index.html`](docs/index.html)。
- 13 份项目 Markdown 已生成对应 HTML，原始 Markdown 保留；重建命令为 `.\.venv-modal\Scripts\python.exe scripts\docs\build_docs.py`。
- 数据集重新下载后先放 `datasets/raw/`；解压、核验后按 `datasets/extracted/<数据集名>/` 组织，并清理已展开的临时 ZIP。
- 训练评估和验证快照放入 `artifacts/qwen3.5-4b/<run-id>/`，管理入口为 `model-training/artifacts/qwen3.5-4b/`；完整 adapter 和优化器状态仍以 Modal `uveitis-runs` 为真相源。
- 训练子集位于 `datasets/training/`；逐文件数据清单位于 `datasets/extracted/manifests/`，已删除归档的来源账本也在那里。
- 检索脚本仅供归档复用，运行方式见各子目录内 round-*.mjs（ego-browser 环境）。

## 本地启动

后端（Windows PowerShell）：

```powershell
cd backend
uv sync --group dev --cache-dir .uv-cache
Copy-Item .env.example .env
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。API 文档位于 `http://127.0.0.1:8000/docs`。

默认 `APP_MODEL_MODE=mock`，只验证业务链路，不生成临床结论。核心路径先完成病例结构化、影像理解、证据检索与医生复核；接入相应服务后切换为 `remote`。补充决策模型由 `APP_DECISION_ENABLED=false` 默认关闭，不作为核心流程的前置条件。

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

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
