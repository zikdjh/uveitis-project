# 训练状态

更新日期：2026-10-25

## 当前状态

| 项目 | 状态 |
|---|---|
| 主模型 | Qwen3.5-4B |
| 本地基座 | `model-training/models/qwen/Qwen3.5-4B/`，14 个模型文件，9.34 GB |
| 训练方式 | 4-bit NF4 QLoRA，本地 RTX 4060 Laptop |
| 训练数据 | `datasets/training/manifest.csv`，16,638 张图像 |
| 数据划分 | train 14,734 / validation 177 / test 1,727 |
| 当前本地候选 adapter | `artifacts/qwen3.5-4b/local-4060-formal-20261025-01/best_adapter` |
| 最近正式本地训练 | `local-4060-formal-20261025-01`，低学习率续训至 500 步，最佳验证步 450 |
| 补充决策模型 | 默认关闭，等待真实决策数据与医生审核 |
| 活跃训练容器 | 无 |
| 本机控制环境 | Python 3.11.17、Modal 1.6.2，预检 18/18 通过 |
| 远端依赖探测 | 固定提交镜像可识别 `qwen3_5`、processor 和 AutoModel；无 GPU 探测成功 |
| 本地 CUDA 环境 | RTX 4060 Laptop 8 GB，PyTorch 2.8.0+cu128，CUDA 可用 |
| 本地 4B 冒烟训练 | 已完成 1 步和连续 3 步 4-bit QLoRA 前向、反向、AdamW 更新 |
| 本地 20 步短训 | `local-4060-short-20261025-01` 完成，20/20 optimizer steps，23.7 秒 |
| 本地正式训练显存 | 峰值分配 `5.45 GiB`，峰值保留 `5.69 GiB`，设备总显存 `8.00 GiB` |

本轮正式训练全程在本地 RTX 4060 执行，新增 Modal GPU 计量为 `$0.00`。此前的 Modal 执行账目仍以控制台账单为准，不由本地训练改变。

本地基座已从 Modal `uveitis-models` 拉取完成，两份掩码权重分片均通过 safetensors 头校验。本地正式训练直接读取 `model-training/models/qwen/Qwen3.5-4B/`，不需要启动 Modal 容器。

本地正式训练已完成，并从第 300、375、450 步继续受控续训。最终目标为 `500` 个优化步、梯度累积 `4`（共 2,000 次样本曝光），图像像素上限 `65,536`、最大序列长度 `256`。首次训练耗时 `1,310.02` 秒，400 步扩展续训 485.62 秒，450 步低学习率续训 425.22 秒，500 步低学习率续训 317.50 秒；四次本地运行累计约 `2,538.36` 秒（42.31 分钟）。

前 375 步的最佳验证损失为第 150 步的 `0.0261653`。第 400、425 步在低学习率续训中分别为 `0.0542480`、`0.0446721`；第 450 步降至 `0.0254597`，首次优于原最佳值。第 475、500 步分别为 `0.0272464`、`0.0260542`，均未超过第 450 步，因此发布候选保持为第 450 步的 `best_adapter`，SHA256 为 `8820450d565b5c139d9b0bda228b4375e2ed5b3af7c87670d8637069a0384b3e`。

训练划分固定为 12,159 条训练行和 68 条分层验证行。300、400、450、500 步调度逐级保留为完整前缀；15 个任务标签类别在 500 步计划中各曝光 133–134 次。验证文件 SHA256 为 `f0f08cdd3f2dbcd194f925cf75283ebc67fb164d15b0dbac868bf26916b3aa34`；300、400、450、500 步调度 SHA256 分别为 `47ac1b54a1b74ddc54044471d555fa59ebdcd0b6ca164ffad039bda69a4f60cd`、`208ac912d1e9c28c3412c9d138c65c41e387e8c7487f9bf7daf0c93209f1c5bd`、`6d9cdd25f25a1f1839515678b0e60a2e25fc43122d38edc64c35eca57200e724`、`04f1bd3793be7469639e125b8e5f13c6a9e031b7f8fb0d0bcbc3c9b749e3a12a`。450 和 500 步续训学习率为 `2.5e-5`，此前为 `1e-4`。

第 450 步最佳 adapter 约 `40.54 MiB`，对应 checkpoint 为 `checkpoints/step-000450/`。前一个第 150 步最佳 adapter 的 SHA256 为 `03bb2cbc09facd88b4b8a292691533225245b07cc494fa6fe9f8f3d72c7c572a`，已由新最佳覆盖；旧 adapter 仍可从 `checkpoints/step-000150/` 恢复。旧最佳曾完成本地 4-bit 基座装载验证，processor 为 `Qwen3VLProcessor`。

这是第一阶段 LoRA 训练结果，不是已通过临床验证的模型。当前验证仅使用生成式验证损失；尚缺少冻结 test 集上的 F1/AUC、亚组评估和医生复核。01/03 数据缺少患者 ID，指标不能视为跨患者泛化；少数类别存在过采样，过拟合风险仍在。

## 本地 4060 验证

本地隔离环境位于 `model-training/.venv-local/`，版本锁定在 `environment/requirements-local-cuda.txt` 和 `environment/runtime.lock.json`。`bitsandbytes` 在 Windows 上通过 `BNB_CUDA_VERSION=128` 加载 CUDA 12.8 后端，已实际完成 4-bit 量化往返和 GPU 运算。

已完成六次独立冒烟运行和一次 20 步短训，结果均为 `ok`：

| Run | 样本/步数 | 图像 token 上限 | 最大序列 | 峰值分配显存 |
|---|---:|---:|---:|---:|
| `local-4060-smoke-20261025-01` | 1 / 1 | 16,384 px | 256 | 5.45 GiB |
| `local-4060-smoke-20261025-02` | 3 / 3 | 65,536 px | 256 | 5.45 GiB |
| `local-4060-smoke-20261025-03` | 1 / 1 | 200,704 px | 512 | 5.51 GiB |
| `local-4060-smoke-20261025-04` | 1 / 1 | 262,144 px | 640 | 5.75 GiB |
| `local-4060-smoke-20261025-05` | 1 / 1 | 451,584 px | 1024 | 6.47 GiB |
| `local-4060-short-20261025-01` | 20 / 20 | 65,536 px | 256 | 5.45 GiB |

冒烟运行保存 LoRA adapter、processor、`smoke_metrics.json` 和周期显存采样 `memory_monitor.jsonl`。完整 4B 权重未修改，adapter 是可重新加载的独立增量权重。冒烟 adapter 只用于验证训练栈，不能作为临床模型或正式训练结果；正式候选只指向 `local-4060-formal-20261025-01/best_adapter`。

本地正式训练已验证 `--image-pixels 65536 --max-length 256 --grad-accum 4` 配置。由于 8 GB 显存仅余约 2.3 GiB，不能沿用 L40S 的 `448×448 + 1024 tokens + 较大 batch` 配置。当前 `causal_conv1d` 和 `flash-linear-attention` 使用参考实现，速度较慢，但不影响已通过的正确性验证。

正式本地训练单步约 `4.0–6.0 秒`，验证约 `21–27 秒`。周期 checkpoint 位于 `checkpoints/step-000050` 至 `step-000500`，恢复状态文件为 `training_state.pt`。中断后可在项目根目录运行 `.\model-training\scripts\run_local_4060_formal.ps1 -RunId local-4060-formal-20261025-01 -Steps 500 -GradAccum 4 -ValidationEvery 25 -SaveEvery 25 -LearningRate 2.5e-5 -Resume`；恢复脚本会拒绝与原调度不兼容的扩展。

本次安装遗留的 `.tmp-local/tmpw_3gndeh` 是 `uv` 创建的无内容临时目录，当前用户没有读取或删除权限；它不包含训练数据、模型或 adapter。大型 wheel 临时文件已删除，CUDA 环境和训练产物未受影响。

## 训练前检查

- 确认 `datasets/training/manifest.csv` 可定位全部图像。
- 确认数据清单哈希、任务分布和排除项与本次 run 配置一致。
- 确认 `uveitis-data`、`uveitis-models`、`uveitis-runs` 均有预期内容。
- 确认当前预算和允许运行时长；不要使用常驻 GPU 服务。
- 设置唯一 `UV_RUN_ID`，保留 config、指标、checkpoint、评估和 model card。
- 用 `model-training/scripts/launch_training.ps1 -DryRun` 检查参数；确认后再去掉 `-DryRun`。

## 训练后检查

- 将 best adapter 与对应 checkpoint 分开记录，不把最后一步 adapter 自动当成最佳模型。
- 提交 Volume，保存训练指标、验证指标和固定 holdout 结果。
- 更新 `model-training/docs/training-cost-ledger-modal-20261025.md`。
- 将小型评估快照放入 `artifacts/qwen3.5-4b/<run-id>/`。
- 记录是否触发停止条件、累计消耗和未完成事项。
