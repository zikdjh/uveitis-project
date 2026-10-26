# 模型运行资产

运行资产不复制权重，统一从 `model-training/assets/qwen3.5-4b/` 读取。

- 冻结评估基线：`local-4060-grouped-cont-20261025-01/best_adapter`
- 选定的 OCT 运行候选：`local-4060-oct-focus-cont-20261025-01/best_adapter`，第 20 步
- 冻结评估：`eval-oct-step20-vs-step100-20261025-01/`

当前运行服务默认索引选定的第 20 步 OCT adapter，但只做路径和文件状态检查。同源冻结测试显示其 macro-F1 为 `0.947245`，比第 100 步基线提升 `0.028993`。切换 adapter 时设置 `MODEL_RUNTIME_ADAPTER_DIR`，不需要移动权重文件。

2026-10-26 的第二阶段受控续训没有产生更好的验证候选：`5e-6` 和 `1e-5` 两组都在第 10 步早停，最佳点仍是初始化时的第 20 步 adapter。运行侧默认 adapter 不变，不读取第二阶段的实验 `final_adapter`。决策证据见 `model-training/assets/qwen3.5-4b/eval-oct-stage2-20261026-01/stage2_decision.json`。
