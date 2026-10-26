# 训练产物与本地快照

整理日期：2026-10-26

这里保存从 Modal Volume 取回的小型评估结果、checkpoint 元数据和历史对照快照。2026-10-26 已删除本地 smoke adapter、中间 checkpoint、`training_state.pt`、重复 processor 和非当前 final adapter；当前仅保留两组工作 adapter、指标和冻结评估断点。完整训练状态仍以 Modal `uveitis-runs` 为唯一真相源。

本目录属于训练侧。模型运行服务只读取 adapter，不在 `model-runtime/` 复制权重。

## Qwen3.5-4B

### focus01-20261025-02（历史实验）

该 run 的 step 250 是当时的小样本固定评估候选，不是当前工作 adapter，也不是正式部署 adapter，没有自动覆盖旧 run 的 `best_adapter/`。

- `step250-fixed-40/eval_manifest.json`：固定 40 样本的选择指纹和类别构成。
- `step250-fixed-40/eval_metrics.json`：01 `0.6833`、02 `1.0`、03 `1.0`、13 `0.9` 的 macro-F1，以及混淆矩阵。
- `step250-fixed-40/eval_predictions.json`：逐样本预测、原始输出和错误信息。
- `step250-fixed-40/checkpoint.json`：该 checkpoint 的元数据快照；完整权重在 `/runs/qwen3.5-4b/qwen4b-focus01-20261025-02/checkpoints/step-000250/`。
- `history/`：step 20、step 35 评估，以及 step 100、200、300 内部验证快照。

固定评估指纹：

```text
1ac1697d151a100c8ad4b906253804a055df0fd5e6bb06a2d64a44b886c6e549
```

step 100、200、300 的内部验证 loss 分别为 `0.018165`、`0.020989`、`0.030704`。后续训练没有改善内部验证；step 250 的固定测试改善来自另一批次的小样本评估，不能把两者混成同一个选模过程。

### stage1-20261025-01

早期正式 run 的最佳验证 checkpoint 是 step 100，验证 loss `0.027431930393807608`。正式部署仍使用：

```text
/runs/qwen3.5-4b/qwen4b-stage1-20261025-01/best_adapter/
```

本地文件包括：

- `best-checkpoint-corrected.json`：从已保存验证结果修正的 step 100 最佳点。
- `best-checkpoint-snapshot.json`：旧快照指向的 step 50，不代表最终最佳点。
- `last-checkpoint-150.json`：最后一次训练步。
- `train-summary-51-snapshot.json`：早期 51 步摘要，不能当作完整的 150 步摘要。
- `dataset-summary/`：数据集规模、任务分布和 manifest 哈希。
- `validation-step-000050.json`、`step-000100.json`、`step-000150.json`：验证 loss 快照。
- `step100-eval-metrics-paired40.json`、`step100-eval-predictions-paired40.json`：固定 40 样本评估。

### pilot 与 smoke

`pilot/` 保存 pilot run 的验证和评估快照；`smoke/` 保存早期配置、旧指标和中断步元数据。`local-4060-*` 冒烟目录中的 adapter、processor 和 checkpoint 已清理，只保留小型指标文件。smoke 指标只证明链路曾运行，不作为准确率证据。

### 当前本地工作适配器

- `local-4060-grouped-cont-20261025-01/best_adapter`：第 100 步同源冻结评估基线。
- `local-4060-oct-focus-cont-20261025-01/best_adapter`：第 20 步选定 OCT 运行候选。
- `eval-oct-step20-vs-step100-20261025-01/`：两个 adapter 的同集冻结评估、逐样本结果、1,000 条基线和 `selection_decision.json`。

选型决定为 `promote_step20_candidate`：候选 macro-F1 `0.947245`，基线 `0.918252`，提升 `+0.028993`，JSON 有效率均为 `100%`。该结果仍受数据来源、增强图和患者隔离限制约束。

## 参考材料

`reference/` 保存 24 GB GPU 云价格表的 HTML 和 XLSX。价格是历史调研快照，使用前应核对供应商当前报价。

## 完整权重的保存约定

QLoRA 只保存基座模型和 adapter。恢复训练需要 `adapter_model.safetensors`、`adapter_config.json`、`processor/` 和 `training_state.pt`；部署只加载基座加最佳 adapter。不要把 `training_state.pt` 当作 PEFT adapter 单独加载。当前本地 `best_adapter/` 可用于加载验证和部署，但不能单独恢复 AdamW 优化器状态。

完整产物仍保存在以下 Modal Volume：

| Volume | 路径 | 内容 |
|---|---|---|
| `uveitis-models` | `/models/qwen/Qwen3.5-4B` | 基座权重 |
| `uveitis-runs` | `/runs/qwen3.5-4b/qwen4b-focus01-20261025-02/` | 当前实验 checkpoint 和评估 |
| `uveitis-runs` | `/runs/qwen3.5-4b/qwen4b-stage1-20261025-01/` | 早期正式 run 和部署 adapter |
