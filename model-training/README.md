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

2026-10-26 已清理旧 smoke run、历史中间 checkpoint、`training_state.pt`、早期实验权重和重复 processor。当前保留两组 OCT 工作 adapter、一个弓形虫病辅助研究 adapter、第二至第五阶段的指标、摘要和决策文件、错误来源分析、受控推理 smoke，以及冻结评估断点；第 4、5 阶段新生成的实验权重仍留在各自目录，均不作为运行候选。完整 checkpoint 与优化器状态仍以 Modal `uveitis-runs` 为真相源。

## 当前训练路线

- 主模型：Qwen3.5-4B，4-bit QLoRA，本地 RTX 4060 单卡训练。
- 数据集：`datasets/training/manifest.csv`，16,638 张图像；训练 14,734、验证 177、冻结测试 1,727。完整数据与精简训练子集均归 `model-training/datasets/` 管理。
- 基线：Qwen3.5-2B 仅作对照。
- 补充决策模型：Intern-Decision-4B；在真实病例文本、医生处置标签和独立评测集到位前默认不训练。
- 真相源：本轮训练使用本地 `datasets/training/manifest.csv` 和 `models/qwen/Qwen3.5-4B/`；checkpoint、验证指标和 adapter 位于 `assets/qwen3.5-4b/`。
- 当前冻结评估基线：`local-4060-grouped-cont-20261025-01/best_adapter`，第 100 步。
- 当前选定的 OCT 运行候选：`local-4060-oct-focus-cont-20261025-01/best_adapter`，第 20 步。
- 弓形虫病辅助研究 adapter：`local-4060-uveitis-focus-20261027-01/best_adapter`，第 200 步；仅使用 ToxoFundus 训练行和 Open UWF 训练行，已排除 Open UWF 已消费的测试与验证行。
- 弓形虫病冻结评估：`toxo-test-20261027-01/evaluation.json`；82 条图像级测试 accuracy `0.914634`、macro-F1 `0.907345`、JSON 有效率 `100%`。
- 发布状态：第 20 步候选和基线均已完成 1,000 条同源 OCT 冻结测试；候选 macro-F1 `0.947245`，基线 `0.918252`，提升 `+0.028993`，通过 `0.02` 选型门槛。当前尚未作为临床模型发布。
- 错误来源：第 20 步候选主要错误为 `NORMAL->DRUSEN` 18 条、`DRUSEN->CNV` 14 条、`CNV->DME` 8 条；相对第 100 步基线，DRUSEN 纠正 38 条，但 CNV 退化 6 条、NORMAL 退化 4 条。
- 受控推理 smoke：第 20 步候选在四类各 4 条本地测试中正确 16/16，JSON 有效率 100%，峰值保留显存 `3.31 GiB`；结果只证明链路可用，不作为泛化精度证据。
- 真实运行服务：`POST /v1/judge` 已加载 4-bit 基座和第 20 步 adapter；冷启动约 22 秒，预处理修正后热请求 `3.363 秒`，单图峰值保留 `3.355469 GiB`，8 并发无 OOM。单张 CNV 训练图返回 DRUSEN、置信度 0，只证明链路和结构契约可用，不能作为准确率或置信度证据。证据见 `assets/qwen3.5-4b/runtime-smoke-local-4060-20261026-01/runtime_smoke.json`。
- 11.10 前收口条件：冻结第 20 步候选 adapter、模型卡、指标文件和运行读取路径，并保留数据来源及患者隔离限制。
- Open UWF 700：CC BY 4.0，7 类与葡萄膜炎二分类任务清单位于 `datasets/tasks/`；数据直接从 `datasets/extracted/14_open_uwf700/` 读取。患者组键必须包含诊断，因为源 `Patient ID` 在不同诊断队列中复用。
- 弓形虫病辅助任务：ToxoFundus 标签由眼科医生确认，但没有患者 ID，现有 train/test 为图像级切分；该 adapter 只作研究补充，不报告患者级外部验证，也不替换第 20 步 OCT 运行候选。

2026-10-26 已完成第二阶段受控复核：分别从第 20 步候选初始化，以 `5e-6` 和 `1e-5` 学习率、OCT 任务权重 4 训练 30 步上限。两次运行都在第 10 步因连续两次验证未改善而早停；第 5、10 步验证 macro-F1 为 `0.867725`，低于入口的 `0.873358`，JSON 有效率仍为 `100%`。因此没有产生新的提升候选，运行候选继续保留第 20 步 adapter，第二阶段 final adapter 不提升、不覆盖。结构化记录见 `assets/qwen3.5-4b/eval-oct-stage2-20261026-01/stage2_decision.json`。

2026-10-26 已启动并完成第三阶段受控复核：从同一条第 20 步候选出发，将图像输入预算由 `65,536` 提高到 `131,072` 像素，学习率降到 `2.5e-6`，每 2 步验证。高分率入口验证只有 macro-F1 `0.826256`、OCT macro-F1 `0.718769`；第 2、4 步最佳为 `0.832019` / `0.736058`，第 6 步回落并在连续两次未改善后早停。高分率显著低于低分辨率入口，因此没有产生提升候选，也不执行冻结测试提升门槛。结构化记录见 `assets/qwen3.5-4b/eval-oct-stage3-20261026-01/stage3_decision.json`。

2026-10-26 已完成第四阶段训练集困难组复核。冻结 adapter 对 `12,101` 条训练样本、`5,184` 个患者组计算 loss 和错误，全程未读取冻结测试图像；全量扫描峰值保留显存 `7.310546875 GiB`。随后按 OCT 四类各 6 组生成 24 组、权重 2 的平衡清单，从第 20 步候选以 `1e-6` 学习率、OCT 任务权重 4、`65,536` 像素训练 3 步后早停。macro-F1 和 OCT 四步都保持 `0.8733582322` / `0.7915032680`，仅第 1 步 loss 从 `0.0350562277` 降到 `0.0350383057`，不能视为提升。峰值分配显存 `5.452396869659424 GiB`、峰值保留 `5.689453125 GiB`，Modal 费用 `$0.00`。结构化记录见 `assets/qwen3.5-4b/eval-oct-stage4-20261026-01/stage4_decision.json`。

2026-10-26 已完成第五阶段新患者组轮换复核。为避免续训反复回放首批患者组，训练调度增加可复现的 `group_offset=50`；偏移后的 138 个 OCT 训练组与初始批次零重叠，前 50 步计划仍保持四类基本均衡。实验从第 20 步候选初始化，以 `1e-6` 学习率、OCT 任务权重 4、`65,536` 像素训练，目标 50 步、每 5 步验证、早停 patience 3。实际完成 15 步后早停；第 1、5、10 步 macro-F1 和 OCT 均保持 `0.8733582322` / `0.7915032680`，第 15 步退化为 `0.8677248677` / `0.7746031746`，JSON 有效率始终 `100%`。峰值分配显存 `5.452396869659424 GiB`、峰值保留 `5.69140625 GiB`，总耗时约 `690.96` 秒，Modal 费用 `$0.00`。组轮换证明调度覆盖了新的训练患者，不代表泛化提升；实验 adapter 不提升，运行候选继续保留第 20 步。结构化结论见 `assets/qwen3.5-4b/eval-oct-stage5-20261026-01/stage5_decision.json`。

当前 55 条筛选验证包含 33 个患者组，OCT 为 CNV 8、DME 5、DRUSEN 18、NORMAL 3。它适合快速剔除明显退化实验，但不足以证明类别级改善。下一步应优先完成模型卡与运行契约、获取患者隔离验证或明确标签修正；没有新的数据假设时不再重复短程续训、高分率、困难组加权或训练组轮换。

2026-10-26 已完成 Open UWF 700 两项本地研究实验，均未启动 Modal GPU。7 类任务训练 60 步，最佳验证 accuracy `0.2222`、macro-F1 `0.214286`，葡萄膜炎 F1 为 0，判定不可用且未读取测试集。二分类任务训练 60 步，最佳 step 50，验证 accuracy `0.684211`、macro-F1 `0.676136`、葡萄膜炎召回 `1.00`、非葡萄膜炎召回 `0.4545`；best adapter SHA256 为 `097d4293eb0e...c9d3e`。两轮训练峰值保留显存最高 `5.697265625 GiB`，说明本地 8 GB 4060 能完成该 4B QLoRA 配置。

二分类 adapter 已完成唯一一次患者隔离测试，共 90 张、78 个患者组。测试 accuracy `0.377778`、macro-F1 `0.338235`、JSON 有效率 `100%`；葡萄膜炎召回 `0.75`、precision `0.10`，非葡萄膜炎 recall `0.341`，54 个阴性样本被误报为阳性。该结果已冻结，不用于选择 checkpoint、学习率或其他超参数；UWF adapter 只作为研究实验，不替换第 20 步 OCT 运行候选。结构化决策见 `assets/qwen3.5-4b/eval-open-uwf-stage1-20261026-01/decision.json`。

Open UWF 数据处理和隔离审计已复核：两份 manifest 各 700 行，图像缺失 0、患者组跨切分 0、图像内容重复 0；7 类哈希为 `6a89bb38...8d498178`，二分类为 `bacc37ed...551c2b253`。二分类的 negative 覆盖 AMD、DR、Healthy、PM、RD、RVO，不等同临床排除全部非葡萄膜炎炎症疾病。下一轮训练应先增加患者隔离阳性、医生确认标签、异质性阴性样本与独立外部验证，不应继续用已消费的测试集调参。

二分类正式训练的验证选择通过 `datasets/tasks/open_uwf_uveitis_binary/validation_split.json` 显式固化，避免任务集合扩展后重新抽取验证面板。该快照不包含测试行；训练器会核对 manifest、任务、验证行和 `validation_selection_sha256`。复现 60 步配置的 DryRun 已得到 `484` 训练、`19` 验证、`415/16` 患者组，验证哈希 `cf103d219977...11633d`，调度哈希 `cae2d1e9e4f6...bea5ea1e`，与正式记录一致。

2026-10-26 已完成第 20 步预测的错误来源分析和受控推理 smoke。错误分析覆盖 1,000 条同源冻结测试，685 个患者/来源组中有 50 组出现错误，前 10 个错误组占全部错误约 `24.53%`；候选相对第 100 步基线的总体提升几乎全部来自 DRUSEN 修正，同时出现 CNV/NORMAL 退化。smoke 使用类别均衡抽样，每类 4 条，共 16 条，结果 16/16 正确、JSON 有效率 `100%`、峰值保留显存 `3.31 GiB`。结构化分析见 `assets/qwen3.5-4b/eval-oct-step20-vs-step100-20261025-01/error-analysis/step20-source-analysis.json`，smoke 证据见 `assets/qwen3.5-4b/eval-oct-step20-runtime-smoke-20261026-01/`。

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

# Open UWF 任务隔离 DryRun；-Task 可重复传入，不会启动训练
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId uwf-binary-dryrun-20261026-01 -Steps 10 -GradAccum 4 `
  -Manifest 'model-training\datasets\tasks\open_uwf_uveitis_binary\manifest.csv' `
  -SplitSnapshot 'model-training\datasets\tasks\open_uwf_uveitis_binary\validation_split.json' `
  -Task uwf_uveitis_binary -MetricTask uwf_uveitis_binary `
  -TaskWeights 'uwf_uveitis_binary=1' -DryRun

# 中断后续训；仅在已从 Modal 恢复 checkpoints/ 和 training_state.pt 后使用
.\model-training\scripts\run_local_4060_formal.ps1 `
  -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 `
  -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5 -Resume

# 运行或续跑冻结测试集评估；已有部分预测时不要添加 -Overwrite
powershell -NoProfile -ExecutionPolicy Bypass -File `
  'model-runtime\scripts\run_local_4060_eval.ps1' `
  -AdapterDir 'model-training\assets\qwen3.5-4b\local-4060-oct-focus-cont-20261025-01\best_adapter' `
  -OutputDir 'model-training\assets\qwen3.5-4b\eval-oct-step20-runtime-smoke-20261026-01' `
  -Tasks 'oct_aux_4class' -SamplesPerClass 4

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
| Open UWF 任务清单 | `model-training/datasets/tasks/` | 是 |
| 完整解压数据 | `model-training/datasets/extracted/` | 是 |
| 新下载数据暂存 | `model-training/datasets/raw/` | 是 |
| 模型运行服务与评估 | `model-runtime/` | 否，运行侧管理 |
| 业务推理与 RAG 扩展 | `ai-services/`、`backend/` | 否 |

每次正式训练应更新 HTML 状态页、预算排期和消耗记录；只有完成评估并记录数据版本与 adapter 指纹后，才把 checkpoint 视为候选产物。
