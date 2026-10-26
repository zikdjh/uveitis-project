# 模型运行服务

模型运行侧的代码、健康检查、评估脚本和部署入口统一放在本目录。当前服务提供模型与 adapter 状态查询，完整影像推理链路仍在接入中。

- `app/`：模型运行 API，默认监听 `8010`。
- `code/local_qwen4b_eval.py`：本地 4060 冻结测试集评估器。
- `scripts/run_local_4060_eval.ps1`：Windows 本地评估入口。
- `assets/README.md`：可用 adapter 与评估结果索引。
- `docs/2026-10-26-model-runtime-evaluation.html`：评估、续跑、显存限制和推理边界。

模型基座和训练产物位于 `model-training/`，运行服务只读取，不在本目录复制权重。

## 健康检查

```powershell
cd model-runtime
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

打开 `http://127.0.0.1:8010/health`。返回 `ready` 表示基座目录和 adapter 文件均可定位；返回 `degraded` 表示路径缺失，服务本身仍可启动。`/v1/models` 提供感知模型、adapter 和补充决策模型的角色索引。

## 本地评估

```powershell
.\model-runtime\scripts\run_local_4060_eval.ps1 `
  -AdapterDir 'model-training\assets\qwen3.5-4b\local-4060-grouped-cont-20261025-01\best_adapter' `
  -OutputDir 'model-training\assets\qwen3.5-4b\eval-layout-smoke-20261026' `
  -Tasks 'oct_aux_4class' -MaxSamples 1
```

评估会读取 `model-training/datasets/training/manifest.csv` 和冻结测试图像，不参与训练或 checkpoint 选择。没有 `-Overwrite` 时会从已有部分预测续跑。
