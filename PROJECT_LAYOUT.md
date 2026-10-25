# 项目目录索引

整理日期：2026-10-25

## 顶层目录

| 目录或文件 | 作用 | 是否可重建 |
|---|---|---|
| `README.md` | 项目入口、启动和当前状态；HTML 总索引在 `docs/index.html` | 代码资料，保留 |
| `PROJECT_LAYOUT.md` | 本目录索引；HTML 版本见 `docs/2026-10-25-project-layout.html` | 文档，保留 |
| `backend/` | FastAPI、SQLite、BGE-M3 和后台测试 | 代码保留；`.venv/`、`models/` 可重建 |
| `frontend/` | React 三端和构建产物 | 代码保留；`node_modules/`、`dist/` 可重建 |
| `model-training/` | 模型训练统一入口：训练代码、Modal 脚本、计划、预算、数据与产物链接 | 训练管理，保留 |
| `model-training/environment/` | Python/Modal/远端依赖锁定、doctor 预检和实际探测报告 | 环境定义，保留 |
| `model-training/code/training/` | Qwen QLoRA、Modal Volume、评估和 smoke 代码 | 训练代码，保留 |
| `model-training/scripts/modal/` | 训练子集构建、Volume 同步和上传 | 训练脚本，保留 |
| `model-training/models/qwen/Qwen3.5-4B/` | 本地 Qwen3.5-4B 基座权重，与 Modal 模型卷对应 | 体积大，保留 |
| `ai-services/inference/`、`rag-kb/` | 推理与知识库代码扩展位 | 保留 |
| `scripts/research/` | 数据集调研浏览器脚本历史存档 | 保留，按日期检索 |
| `datasets/raw/` | 新下载压缩包的临时暂存区 | 空目录保留；解压和核验后清理 |
| `datasets/extracted/` | 解压后的完整眼科数据集与逐文件清单 | 原始数据，体积大，不重建 |
| `datasets/training/` | Modal 训练精简包、manifest 和标签 | 可从 `extracted/` 重建，但成本较高 |
| `artifacts/` | 小型训练评估、验证和参考快照 | 重要证据，保留 |
| `model-training/artifacts/qwen3.5-4b/` | 指向 `artifacts/qwen3.5-4b/` 的训练产物入口 | 不复制权重的访问链接 |
| `model-training/data/training/` | 指向 `datasets/training/` 的训练数据入口 | 不复制数据的访问链接 |
| `outputs/` | 临时运行输出 | 只保留说明，稳定结果移入 `artifacts/` |
| `docs/` | 项目调研、训练计划、预算、消耗记录及统一 HTML 索引 | 保留 |
| `logs/` | 后端、前端和下载任务日志 | 可重建 |

## 训练产物入口

- 统一训练入口：`model-training/README.md`
- 当前训练状态：`model-training/STATUS.md`
- 当前 Qwen 4B 实验最佳候选：`model-training/artifacts/qwen3.5-4b/focus01-20261025-02/step250-fixed-40/`
- 历史 Qwen 4B 正式 run：`model-training/artifacts/qwen3.5-4b/stage1-20261025-01/`
- 完整 adapter 和优化器状态：Modal Volume `uveitis-runs`，不是本地 `artifacts/`
- 数据集清单：`docs/2026-10-25-dataset-index.html`
- 训练数据 map：`docs/2026-10-25-dataset-training-map.html`
- 消耗和结果：`docs/2026-10-25-training-cost-ledger-modal.html`

## 占用与清理

初始扫描时项目约 101 GB：

- `datasets/extracted` 约 63.37 GB
- `datasets/training` 约 1.46 GB
- `model-training/models/qwen/Qwen3.5-4B` 约 9.34 GB
- `backend/models` 约 4.37 GB
- `backend/.venv` 约 3.62 GB
- 顶层 `uv` 缓存约 3.67 GB

本次已删除 14 个根目录 ZIP（24,212,809,851 字节）和 4 个重复内层 ZIP（8,504,821,552 字节），合计约 30.5 GiB。删除账本见 `datasets/extracted/manifests/archive-cleanup-2026-10-25.csv`。

不要清理 `datasets/extracted/01_uveitis_oct`、`02_toxofundus`、`03_eye_five_class` 或 `13_zhanglab` 中训练 manifest 指向的图像。其他数据集是否保留取决于后续实验计划。

已解压数据直接以 `datasets/extracted/` 为准，不要求保留原 ZIP。新下载内容先放 `datasets/raw/`；只有完成解压、完整性核验和清单更新后，才删除对应的临时包。

## 验证状态

- `datasets/training/manifest.csv` 的 16,638 条记录均能定位到本地图像，训练数据路径未被本次整理破坏。
- 删除前，17 个归档的 182,754 个数据成员全部通过名称、大小和 CRC 校验；0 缺失、0 大小不一致、0 CRC 不一致。
- `datasets/extracted/manifests/extracted-files.csv` 的 180,456 条保留记录均可定位；删除的 4 个重复 ZIP 已移除记录并收入删除账本。
- Modal 训练、评估和训练子集构建脚本语法检查通过。
- `backend/tests/test_health.py` 在测试收集阶段需要连接 `127.0.0.1:5432` PostgreSQL；当前 `.env` 对应的本地数据库不可用，连接在 131 秒后超时。该失败与文件整理无关，未修改数据库配置。
