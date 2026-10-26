# 训练产物与本地快照

整理日期：2026-10-26

这里保存从 Modal Volume 取回的小型评估结果、checkpoint 元数据和历史对照快照。2026-10-26 已删除本地 smoke adapter、历史中间 checkpoint、`training_state.pt`、第二/第三阶段实验权重和重复 processor；当前保留两组工作 adapter、阶段实验指标、摘要、决策文件、错误来源分析和受控推理 smoke。实验 adapter 不作为运行候选。完整训练状态仍以 Modal `uveitis-runs` 为唯一真相源。

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
- `local-4060-oct-stage2-20261026-01/`、`local-4060-oct-stage2b-20261026-01/`：从第 20 步候选初始化的受控复核指标和实验日志；两次均在 10 步早停，未产生更好的 best adapter。
- `eval-oct-stage2-20261026-01/stage2_decision.json`：第二阶段结论，决定保留第 20 步候选，不提升实验 final adapter。
- `local-4060-oct-stage3-hires-20261026-01/`：高分率受控复核指标、切分快照和实验日志；6 步后早停，最佳点仍远低于第 20 步候选。
- `eval-oct-stage3-20261026-01/stage3_decision.json`：第三阶段结论，决定保留第 20 步候选，不提升高分率实验 adapter。
- `eval-oct-step20-vs-step100-20261025-01/error-analysis/step20-source-analysis.json`：第 20 步候选的类别、患者/来源组错误分析，以及与第 100 步基线的逐类变化。
- `eval-oct-step20-runtime-smoke-20261026-01/`：第 20 步候选的四类均衡本地推理 smoke，记录 16 条预测、指标、抽样模式和显存峰值。

选型决定为 `promote_step20_candidate`：候选 macro-F1 `0.947245`，基线 `0.918252`，提升 `+0.028993`，JSON 有效率均为 `100%`。该结果仍受数据来源、增强图和患者隔离限制约束。

第二阶段复核使用 `5e-6` 和 `1e-5` 两个学习率，均从第 20 步候选初始化，OCT 任务权重保持 4。两次运行的第 5、10 步验证 macro-F1 均为 `0.867725`，OCT macro-F1 均为 `0.774603`，低于入口的 `0.873358` / `0.791503`，因此都在第 10 步触发早停。该结果说明继续同一数据、同一任务权重和同一 8 GB 配置下的短程续训没有带来收益；后续优先检查数据和错误来源，而不是继续增加步数。

第三阶段把图像输入预算提高到 `131,072` 像素，保持第 20 步初始化、OCT 任务权重 4 和 `2.5e-6` 学习率，目标是增加 CNV/DRUSEN 边界细节。高分率初始化的 55 条验证只有 macro-F1 `0.826256`、OCT `0.718769`；最佳第 2 步为 `0.832019` / `0.736058`，第 4 步持平，第 6 步回落后早停。高分率改变了输入分布但未提高指标，因此运行候选仍为低分辨率第 20 步 adapter。

错误来源分析显示，第 20 步候选在 1,000 条测试中的主要错误为 `NORMAL->DRUSEN` 18 条、`DRUSEN->CNV` 14 条、`CNV->DME` 8 条，另有 `CNV->DRUSEN` 4 条、`DME->DRUSEN` 4 条、`DME->CNV` 3 条及两条其他错误。685 个患者/来源组中有 50 组存在错误，前 10 个错误组占全部错误约 `24.53%`。相对第 100 步基线，DRUSEN 纠正 38 条是主要收益，同时 CNV 退化 6 条、NORMAL 退化 4 条、DME 净改善 1 条。后续实验应围绕 NORMAL/DRUSEN 与 CNV/DME 的边界，而不是继续增加同配置步数或输入像素。

受控推理 smoke 使用第 20 步 adapter、`65,536` 像素、每类 4 条共 16 条，selection SHA256 为 `77a65218744fe84896bb06d7d216bdb9b2329fc06e2de90bdba428dcf9a6a0ee`。结果为 16/16 正确、JSON 有效率 `100%`、生成错误 0；adapter 加载后分配显存 `3.114870 GiB`，峰值分配 `3.233283 GiB`，峰值保留 `3.310547 GiB`，总耗时约 63 秒。该结果不构成准确率或泛化证据。

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
