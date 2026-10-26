# 模型运行资产

运行资产不复制权重，统一从 `model-training/assets/qwen3.5-4b/` 读取。

- 冻结评估基线：`local-4060-grouped-cont-20261025-01/best_adapter`
- OCT 候选：`local-4060-oct-focus-cont-20261025-01/best_adapter`
- 冻结评估：`eval-oct-step20-vs-step100-20261025-01/`

当前运行服务默认索引 OCT 候选，但只做路径和文件状态检查。切换 adapter 时设置 `MODEL_RUNTIME_ADAPTER_DIR`，不需要移动权重文件。
