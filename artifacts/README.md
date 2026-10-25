# 训练产物与本地快照

整理日期：2026-10-25

这里保存从 Modal Volume 取回的小型评估结果、checkpoint 元数据和历史对照快照。大体积 adapter、`training_state.pt` 和 processor 仍以 Modal `uveitis-runs` 为唯一真相源，本地目录没有复制完整权重。

## Qwen3.5-4B

### focus01-20261025-02

当前实验最佳候选是 step 250。它不是正式部署 adapter，也没有自动覆盖旧 run 的 `best_adapter/`。

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

`pilot/` 保存 pilot run 的验证和评估快照；`smoke/` 保存早期 adapter 配置、旧指标和中断步元数据。smoke 指标只证明链路曾运行，不作为准确率证据。

## 参考材料

`reference/` 保存 24 GB GPU 云价格表的 HTML 和 XLSX。价格是历史调研快照，使用前应核对供应商当前报价。

## 完整权重的保存约定

QLoRA 只保存基座模型和 adapter。恢复训练需要 `adapter_model.safetensors`、`adapter_config.json`、`processor/` 和 `training_state.pt`；部署只加载基座加最佳 adapter。不要把 `training_state.pt` 当作 PEFT adapter 单独加载。

完整产物仍保存在以下 Modal Volume：

| Volume | 路径 | 内容 |
|---|---|---|
| `uveitis-models` | `/models/qwen/Qwen3.5-4B` | 基座权重 |
| `uveitis-runs` | `/runs/qwen3.5-4b/qwen4b-focus01-20261025-02/` | 当前实验 checkpoint 和评估 |
| `uveitis-runs` | `/runs/qwen3.5-4b/qwen4b-stage1-20261025-01/` | 早期正式 run 和部署 adapter |
