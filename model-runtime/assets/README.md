# 模型运行资产

运行资产不复制权重，统一从 `model-training/assets/qwen3.5-4b/` 读取。

- 冻结评估基线：`local-4060-grouped-cont-20261025-01/best_adapter`
- 选定的 OCT 运行候选：`local-4060-oct-focus-cont-20261025-01/best_adapter`，第 20 步
- 冻结评估：`eval-oct-step20-vs-step100-20261025-01/`
- 错误来源分析：`eval-oct-step20-vs-step100-20261025-01/error-analysis/step20-source-analysis.json`
- 本地受控推理 smoke：`eval-oct-step20-runtime-smoke-20261026-01/`
- 真实运行服务烟测：`runtime-smoke-local-4060-20261026-01/runtime_smoke.json`

当前运行服务默认索引选定的第 20 步 OCT adapter，并通过 `POST /v1/judge` 执行真实本地推理。同源冻结测试显示其 macro-F1 为 `0.947245`，比第 100 步基线提升 `0.028993`。切换 adapter 时设置 `MODEL_RUNTIME_ADAPTER_DIR`，不需要移动权重文件。

2026-10-26 的第二阶段受控续训没有产生更好的验证候选：`5e-6` 和 `1e-5` 两组都在第 10 步早停，最佳点仍是初始化时的第 20 步 adapter。运行侧默认 adapter 不变，不读取第二阶段的实验 `final_adapter`。决策证据见 `model-training/assets/qwen3.5-4b/eval-oct-stage2-20261026-01/stage2_decision.json`。

第 20 步候选的 1,000 条错误分析显示，主要错误为 `NORMAL->DRUSEN` 18 条、`DRUSEN->CNV` 14 条、`CNV->DME` 8 条；相对第 100 步基线，DRUSEN 纠正 38 条，但 CNV 退化 6 条、NORMAL 退化 4 条。四类各 4 条的本地推理 smoke 为 16/16 正确、JSON 有效率 100%，峰值保留显存 `3.31 GiB`。该 smoke 只用于验证运行链路，不作为准确率依据。
