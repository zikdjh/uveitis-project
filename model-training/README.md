# 模型训练管理

整理日期：2026-10-26

本目录是模型训练的单一管理入口。代码、Modal 任务、训练计划、预算记录、数据入口和本地产物入口都从这里查找。

训练工程目标收口日期：**2026-11-10**。统一跟踪见 `docs/2026-10-26-progress-tracking.html`，阶段汇总见 `docs/2026-10-26-model-training-progress.html`，当前运行态见 `docs/2026-10-26-model-training-status.html`。

## 目录结构

```text
model-training/
├── README.md
├── environment/                版本锁定、环境预检与依赖定义
├── code/
│   └── training/               QLoRA、评估、smoke、Volume 与数据检查代码
├── scripts/
│   ├── modal/                  训练子集构建、Volume 同步和批量上传
│   ├── run_local_4060_smoke.ps1 本地 4060 QLoRA 冒烟入口
│   └── run_local_4060_formal.ps1 本地 4060 可恢复正式训练入口
├── datasets/
│   ├── raw/                    新下载压缩包的临时暂存区
│   ├── extracted/              完整解压数据集与 manifests/ 清单
│   └── training/               训练图像、manifest 和标签
├── models/
│   └── qwen/Qwen3.5-4B/       从 Modal uveitis-models 拉取的本地基座权重
└── assets/
    └── qwen3.5-4b/             adapter、指标、评估和训练快照
```

完整数据集、训练子集、基座和产物均位于 `model-training/` 内，不再依赖根级 junction。模型运行侧只读取这些文件，不复制权重。

`models/qwen/Qwen3.5-4B/` 是本地基座副本，当前 14 个模型文件、9,342,907,469 字节（不含单独的 `pull-manifest.json`），包含两份 safetensors 分片、索引、配置和 tokenizer。它不替代 Modal 上的 `uveitis-models`；本地正式训练直接使用本地副本，Modal 卷仍是远端备份和训练恢复来源。

本地加载需要支持 `qwen3_5` 架构的 Transformers。项目训练脚本固定使用 `50e35cc0ca18ec19b80653690de553e6decf74f5`；后端当前的 Transformers 4.51.3 不识别该架构，不能直接用它加载这个模型目录。本地校验清单见 `models/qwen/Qwen3.5-4B/pull-manifest.json`。

本地 4060 使用独立的 `model-training/.venv-local/`，其中是 CUDA 12.8 的 PyTorch 和 Transformers 5.20.2，不使用 `backend/.venv` 的 CPU PyTorch。该环境已完成 4-bit NF4、bfloat16、LoRA 前向/反向、optimizer step、周期验证和可恢复正式训练实测；状态见 `docs/2026-10-26-model-training-status.html`，产物索引见 `assets/README.md`。

2026-10-26 已清理旧 smoke run、历史中间 checkpoint、`training_state.pt`、实验权重和重复 processor。当前保留两组工作 adapter、第二/第三阶段的指标、摘要和决策文件，以及冻结评估断点；实验 `best_adapter` / `final_adapter` 不作为运行候选，完整 checkpoint 与优化器状态仍以 Modal `uveitis-runs` 为真相源。

## 当前训练路线

- 主模型：Qwen3.5-4B，4-bit QLoRA，本地 RTX 4060 单卡训练。
- 数据集：`datasets/training/manifest.csv`，16,638 张图像；训练 14,734、验证 177、冻结测试 1,727。完整数据与精简训练子集均归 `model-training/datasets/` 管理。
- 基线：Qwen3.5-2B 仅作对照。
- 补充决策模型：Intern-Decision-4B；在真实病例文本、医生处置标签和独立评测集到位前默认不训练。
- 真相源：本轮训练使用本地 `datasets/training/manifest.csv` 和 `models/qwen/Qwen3.5-4B/`；checkpoint、验证指标和 adapter 位于 `assets/qwen3.5-4b/`。
- 当前冻结评估基线：`local-4060-grouped-cont-20261025-01/best_adapter`，第 100 步。
- 当前选定的 OCT 运行候选：`local-4060-oct-focus-cont-20261025-01/best_adapter`，第 20 步。
- 发布状态：第 20 步候选和基线均已完成 1,000 条同源 OCT 冻结测试；候选 macro-F1 `0.947245`，基线 `0.918252`，提升 `+0.028993`，通过 `0.02` 选型门槛。当前尚未作为临床模型发布。
- 11.10 前收口条件：冻结第 20 步候选 adapter、模型卡、指标文件和运行读取路径，并保留数据来源及患者隔离限制。

2026-10-26 已完成第二阶段受控复核：分别从第 20 步候选初始化，以 `5e-6` 和 `1e-5` 学习率、OCT 任务权重 4 训练 30 步上限。两次运行都在第 10 步因连续两次验证未改善而早停；第 5、10 步验证 macro-F1 为 `0.867725`，低于入口的 `0.873358`，JSON 有效率仍为 `100%`。因此没有产生新的提升候选，运行候选继续保留第 20 步 adapter，第二阶段 final adapter 不提升、不覆盖。结构化记录见 `assets/qwen3.5-4b/eval-oct-stage2-20261026-01/stage2_decision.json`。

2026-10-26 已启动并完成第三阶段受控复核：从同一条第 20 步候选出发，将图像输入预算由 `65,536` 提高到 `131,072` 像素，学习率降到 `2.5e-6`，每 2 步验证。高分率入口验证只有 macro-F1 `0.826256`、OCT macro-F1 `0.718769`；第 2、4 步最佳为 `0.832019` / `0.736058`，第 6 步回落并在连续两次未改善后早停。高分率显著低于低分辨率入口，因此没有产生提升候选，也不执行冻结测试提升门槛。结构化记录见 `assets/qwen3.5-4b/eval-oct-stage3-20261026-01/stage3_decision.json`。

## 常用命令

所有命令从项目根目录运行。

```powershell
# 构建训练子集
.\model-training\.venv-modal\Scripts\python.exe model-training\scripts\modal\build_budget_training_subset.py

# 上传训练数据
.\model-training\scripts\modal\upload_data_batches.ps1

# 运行 Qwen3.5-4B 训练
.\model-training\.venv-modal\Scripts\modal.exe run model-training\code\training\modal_qwen4b_train.py

# 运行评估
$env:UV_RUN_ID = "qwen4b-stage1-20261025-01"
.\model-training\.venv-modal\Scripts\modal.exe run model-training\code\training\modal_qwen4b_eval.py

# 验证本地训练清单
.\model-training\.venv-modal\Scripts\python.exe scripts\datasets\verify_archive_extraction.py --manifests-only

# 环境预检；不启动 GPU
.\model-training\.venv-modal\Scripts\python.exe model-training\environment\doctor.py

# 本地 4060 单步或短程 QLoRA 冒烟；不产生 Modal 费用
.\model-training\scripts\run_local_4060_smoke.ps1 `
  -RunId local-4060-smoke-20261025-06 -Steps 3 `
  -ImagePixels 65536 -MaxLength 256

# 本地正式阶段训练：分层验证、类别均衡、checkpoint 与 best adapter
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 `
  -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5

# 从选定 adapter 初始化的受控续训；先运行 -DryRun 核对切分和调度
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-oct-stage2-20261026-01 -Steps 30 -GradAccum 4 `
  -ValidationEvery 5 -SaveEvery 10 -EarlyStopPatience 2 -LearningRate 5e-6 `
  -InitAdapter 'model-training\assets\qwen3.5-4b\local-4060-oct-focus-cont-20261025-01\best_adapter' `
  -TaskWeights 'oct_aux_4class=4' -DryRun

# 中断后续训；仅在已从 Modal 恢复 checkpoints/ 和 training_state.pt 后使用
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 `
  -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5 -Resume

# 运行或续跑冻结测试集评估；已有部分预测时不要添加 -Overwrite
powershell -NoProfile -ExecutionPolicy Bypass -File `
  'model-runtime\scripts\run_local_4060_eval.ps1' `
  -AdapterDir 'model-training\assets\qwen3.5-4b\local-4060-grouped-cont-20261025-01\best_adapter' `
  -OutputDir 'model-training\assets\qwen3.5-4b\eval-oct-step20-vs-step100-20261025-01\step100' `
  -Tasks 'oct_aux_4class'

# 检查启动参数但不启动 GPU
.\model-training\scripts\launch_training.ps1 -RunId env-check-20261025 `
  -AllowedGpuMinutes 5 -BudgetConfirmed -TrainLimit 16 -MaxSteps 1 -DryRun
```

运行训练前，先在 `docs/2026-10-25-training-budget-plan-modal-l40s.html` 核对当前预算，在 `docs/2026-10-25-training-cost-ledger-modal.html` 核对最近一次实际消耗。训练命令依赖 Modal CLI 和 `model-training/code/training/modal_volumes.py`，不要把训练脚本单独复制到其他位置执行。

`environment/` 中锁定了本机 Modal 控制器、远端 Python/PyTorch/Transformers/PEFT/Accelerate/bitsandbytes 版本，以及数据清单和本地模型的 SHA256 或尺寸。`launch_training.ps1` 每次都会先运行 `doctor.py`；必须显式传入 `-BudgetConfirmed` 和 GPU 分钟上限，避免误启动无界训练。上述两个版本探测应用均无 GPU，运行后已停止。

## 文件边界

| 内容 | 位置 | 是否属于训练管理目录 |
|---|---|---|
| 训练代码与 Modal 应用 | `model-training/code/training/` | 是 |
| 环境锁定与启动闸门 | `model-training/environment/`、`model-training/scripts/launch_training.ps1` | 是 |
| 数据准备与上传脚本 | `model-training/scripts/modal/` | 是 |
| 训练计划、预算、消耗记录 | `docs/` 的 HTML 专题文档 | 是 |
| Modal 训练精简数据 | `model-training/datasets/training/` | 是 |
| 本地 Qwen3.5-4B 基座 | `model-training/models/qwen/Qwen3.5-4B/` | 是 |
| 本地评估快照 | `model-training/assets/qwen3.5-4b/` | 是 |
| 完整解压数据 | `model-training/datasets/extracted/` | 是 |
| 新下载数据暂存 | `model-training/datasets/raw/` | 是 |
| 模型运行服务与评估 | `model-runtime/` | 否，运行侧管理 |
| 业务推理与 RAG 扩展 | `ai-services/`、`backend/` | 否 |

每次正式训练应更新 HTML 状态页、预算排期和消耗记录；只有完成评估并记录数据版本与 adapter 指纹后，才把 checkpoint 视为候选产物。
