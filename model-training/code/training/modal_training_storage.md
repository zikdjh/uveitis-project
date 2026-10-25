# Modal 训练文件与模型保存约定

## Volume

| Volume | 挂载点 | 内容 | 是否可重建 |
|---|---|---|---|
| `uveitis-data` | `/data` | manifest、训练图、标签、患者元数据 | 可，但重新上传昂贵 |
| `uveitis-models` | `/models` | Qwen3.5-2B、Qwen3.5-4B、Intern-Decision-4B 基座权重 | 可，但重新下载昂贵 |
| `uveitis-runs` | `/runs` | 训练配置、adapter、checkpoint、优化器状态、评估结果 | 不可随意重建，是主要训练产物 |

三个卷都显式挂载到训练函数，不依赖 Modal 临时容器的本地磁盘。

训练函数读取数据时使用：

```text
/data/data/manifest.csv
/data/data/data/<dataset>/<relative_path>
```

## 保存路径

每次训练使用唯一 run id。当前主线 4B run：

```text
/runs/qwen3.5-4b/qwen4b-stage1-20261025-01/
  config.json
  dataset_summary.json
  train_metrics.jsonl
  eval_metrics.json
  best_checkpoint.json
  best_adapter/
    adapter_config.json
    adapter_model.safetensors
    adapter_manifest.json
  processor/
  paired40/
    eval_manifest.json
    eval_metrics.json
    eval_predictions.json
  checkpoints/
    step-000050/
    step-000100/
    step-000150/
  final_adapter/
  model_card.md
```

`final_adapter/` 是最后一次内存权重，不能默认视为最佳模型；本 run 已把 step 100 的 adapter 提升到 `best_adapter/`，恢复训练仍使用 `checkpoints/step-000100/training_state.pt`。

决策模型使用独立目录：

```text
/runs/intern-decision-4b/uv_decision_20261112_01/
  config.json
  schema.json
  train_metrics.jsonl
  eval_metrics.json
  checkpoints/
  final_adapter/
  model_card.md
```

## 必须保存的内容

- `config.json`：基座模型、量化方式、LoRA rank、目标模块、序列长度和随机种子。
- `dataset_summary.json`：manifest 哈希、数据集版本、训练/验证/测试数量和排除项。
- `best_adapter/`：最佳验证步 LoRA adapter；由对应 checkpoint 的 adapter 配置和权重按 SHA256 校验复制生成。
- `final_adapter/`：最后一次优化步的 adapter，仅用于诊断，不作为默认部署产物。
- `checkpoints/`：至少保留最佳 checkpoint 和最后一次 checkpoint。
- `train_metrics.jsonl`：loss、学习率和吞吐量。
- `eval_metrics.json`：macro-F1、JSON 合法率、混淆矩阵和任务级结果。
- `model_card.md`：训练数据、限制、许可和人工复核要求。

## 保存方式

QLoRA/LoRA 训练只保存 adapter，不重新保存整份 4B 基座模型。推理时读取：

```text
/models/qwen/Qwen3.5-4B
/runs/qwen3.5-4b/<run_id>/best_adapter
```

不要加载 checkpoint 目录中的 `training_state.pt` 到 PEFT。

这比每轮保存完整模型更省 Volume 空间，也保留基座模型与训练产物的版本对应关系。

如果部署方要求单目录自包含模型，可以在训练节点执行 adapter merge，将合并后的 safetensors 写入：

```text
/runs/merged/qwen3.5-4b/<run_id>/
```

不能在 4-bit NF4 量化权重上直接 merge。应在未量化的基座权重上合并 adapter，再按部署格式另行量化。合并模型是派生产物，不是训练的唯一真相源。原始基座、adapter、config 和 manifest 哈希仍需保留。

## 持久化与恢复

- Modal Volume 写入后必须 `commit()`，否则容器退出后可能看不到新文件。
- 训练每 N 步保存 checkpoint，并在保存后提交 Volume。
- 训练任务开始前先检查同一 run id 的 checkpoint，从最新可恢复点续训。
- checkpoint 只保留最佳和最后一次，避免把额度浪费在无限增长的优化器状态上。
- 训练完成后生成只读 manifest，记录 adapter、评估结果和基座版本。

## 从 Volume 取回本地

```powershell
modal volume get uveitis-runs qwen3.5-4b/<run_id> ./model-training/artifacts/qwen3.5-4b/<run_id>
modal volume get uveitis-runs intern-decision-4b/<run_id> ./artifacts/intern-decision-4b/<run_id>
```

模型卷中的基座权重不需要取回；如果本地推理需要，可单独下载对应基座。

如果从本项目的本地 CLI 环境取回：

```powershell
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv-modal\Scripts\modal.exe volume get uveitis-runs qwen3.5-4b/<run_id> .\model-training\artifacts\qwen3.5-4b\<run_id>
```

下载多个文件后，先核对最佳 checkpoint 的 adapter 两文件、`training_state.pt`、`best_checkpoint.json`、`config.json` 和 `eval_metrics.json` 是否齐全，再清理 Modal 上不需要保留的中间 checkpoint。不要只下载 `pytorch_lora_weights.safetensors`，却遗漏 adapter 配置、processor 或数据版本记录。
