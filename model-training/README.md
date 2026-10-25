# 模型训练管理

整理日期：2026-10-25

本目录是模型训练的单一管理入口。代码、Modal 任务、训练计划、预算记录、数据入口和本地产物入口都从这里查找。

## 目录结构

```text
model-training/
├── README.md
├── STATUS.md
├── environment/                版本锁定、环境预检与依赖定义
├── code/
│   └── training/               QLoRA、评估、smoke、Volume 与数据检查代码
├── scripts/
│   ├── modal/                  训练子集构建、Volume 同步和批量上传
│   ├── run_local_4060_smoke.ps1 本地 4060 QLoRA 冒烟入口
│   └── run_local_4060_formal.ps1 本地 4060 可恢复正式训练入口
├── docs/
│   ├── training-plan-modal-l40s-20261023.md
│   ├── training-budget-plan-modal-l40s-44usd-20261025.md
│   └── training-cost-ledger-modal-20261025.md
├── data/
│   └── training/               指向 datasets/training 的目录链接
├── models/
│   └── qwen/Qwen3.5-4B/       从 Modal uveitis-models 拉取的本地基座权重
└── artifacts/
    └── qwen3.5-4b/             指向 artifacts/qwen3.5-4b 的目录链接
```

`data/training` 和 `artifacts/qwen3.5-4b` 是指向原目录的 Windows junction，不复制数据。训练数据和运行产物仍然分别位于：

```text
datasets/training/
artifacts/qwen3.5-4b/
```

`models/qwen/Qwen3.5-4B/` 是本地基座副本，当前 14 个模型文件、9,342,907,469 字节（不含单独的 `pull-manifest.json`），包含两份 safetensors 分片、索引、配置和 tokenizer。它不替代 Modal 上的 `uveitis-models`；正式训练仍从 Modal 卷加载基座。

本地加载需要支持 `qwen3_5` 架构的 Transformers。项目训练脚本固定使用 `50e35cc0ca18ec19b80653690de553e6decf74f5`；后端当前的 Transformers 4.51.3 不识别该架构，不能直接用它加载这个模型目录。本地校验清单见 `models/qwen/Qwen3.5-4B/pull-manifest.json`。

本地 4060 使用独立的 `model-training/.venv-local/`，其中是 CUDA 12.8 的 PyTorch 和 Transformers 5.20.2，不使用 `backend/.venv` 的 CPU PyTorch。该环境已完成 4-bit NF4、bfloat16、LoRA 前向/反向、optimizer step、周期验证和可恢复正式训练实测；详见 `STATUS.md` 与 `artifacts/qwen3.5-4b/local-4060-formal-20261025-01/`。

## 当前训练路线

- 主模型：Qwen3.5-4B，4-bit QLoRA，本地 RTX 4060 单卡训练。
- 数据集：`data/training/manifest.csv`，16,638 张图像；训练 14,734、验证 177、冻结测试 1,727。
- 基线：Qwen3.5-2B 仅作对照。
- 补充决策模型：Intern-Decision-4B；在真实病例文本、医生处置标签和独立评测集到位前默认不训练。
- 真相源：本轮训练使用本地 `datasets/training/manifest.csv` 和 `model-training/models/qwen/Qwen3.5-4B/`；正式 checkpoint、验证指标和 adapter 位于 `artifacts/qwen3.5-4b/local-4060-formal-20261025-01/`。
- 发布候选：`best_adapter/`，对应第 150 步和最佳验证损失 `0.0261653`；`final_adapter/` 仅用于记录最后一步。

## 常用命令

所有命令从项目根目录运行。

```powershell
# 构建训练子集
.\.venv-modal\Scripts\python.exe model-training\scripts\modal\build_budget_training_subset.py

# 上传训练数据
.\model-training\scripts\modal\upload_data_batches.ps1

# 运行 Qwen3.5-4B 训练
.\.venv-modal\Scripts\modal.exe run model-training\code\training\modal_qwen4b_train.py

# 运行评估
$env:UV_RUN_ID = "qwen4b-stage1-20261025-01"
.\.venv-modal\Scripts\modal.exe run model-training\code\training\modal_qwen4b_eval.py

# 验证本地训练清单
.\.venv-modal\Scripts\python.exe scripts\datasets\verify_archive_extraction.py --manifests-only

# 环境预检；不启动 GPU
.\.venv-modal\Scripts\python.exe model-training\environment\doctor.py

# 本地 4060 单步或短程 QLoRA 冒烟；不产生 Modal 费用
.\model-training\scripts\run_local_4060_smoke.ps1 `
  -RunId local-4060-smoke-20261025-06 -Steps 3 `
  -ImagePixels 65536 -MaxLength 256

# 本地正式阶段训练：分层验证、类别均衡、checkpoint 与 best adapter
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 `
  -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5

# 中断后续训；扩展步数时必须保留原调度为完整前缀
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 `
  -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5 -Resume

# 检查启动参数但不启动 GPU
.\model-training\scripts\launch_training.ps1 -RunId env-check-20261025 `
  -AllowedGpuMinutes 5 -BudgetConfirmed -TrainLimit 16 -MaxSteps 1 -DryRun
```

运行训练前，先在 `model-training/docs/training-budget-plan-modal-l40s-44usd-20261025.md` 核对当前预算，在 `model-training/docs/training-cost-ledger-modal-20261025.md` 核对最近一次实际消耗。训练命令依赖 Modal CLI 和 `model-training/code/training/modal_volumes.py`，不要把训练脚本单独复制到其他位置执行。

`environment/` 中锁定了本机 Modal 控制器、远端 Python/PyTorch/Transformers/PEFT/Accelerate/bitsandbytes 版本，以及数据清单和本地模型的 SHA256 或尺寸。`launch_training.ps1` 每次都会先运行 `doctor.py`；必须显式传入 `-BudgetConfirmed` 和 GPU 分钟上限，避免误启动无界训练。上述两个版本探测应用均无 GPU，运行后已停止。

## 文件边界

| 内容 | 位置 | 是否属于训练管理目录 |
|---|---|---|
| 训练代码与 Modal 应用 | `model-training/code/training/` | 是 |
| 环境锁定与启动闸门 | `model-training/environment/`、`model-training/scripts/launch_training.ps1` | 是 |
| 数据准备与上传脚本 | `model-training/scripts/modal/` | 是 |
| 训练计划、预算、消耗记录 | `model-training/docs/` | 是 |
| Modal 训练精简数据 | `datasets/training/` | 通过 `data/training` 链接管理 |
| 本地 Qwen3.5-4B 基座 | `model-training/models/qwen/Qwen3.5-4B/` | 是 |
| 本地评估快照 | `artifacts/qwen3.5-4b/` | 通过 `artifacts/qwen3.5-4b` 链接管理 |
| 完整解压数据 | `datasets/extracted/` | 否，由数据集清单管理 |
| 推理服务与 RAG 服务 | `ai-services/inference/`、`ai-services/rag-kb/` | 否 |

每次正式训练应更新 `STATUS.md`、预算排期和消耗记录；只有完成评估并记录数据版本与 adapter 指纹后，才把 checkpoint 视为候选产物。
