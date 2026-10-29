# 模型运行服务

模型运行侧的代码、健康检查、评估脚本和部署入口统一放在本目录。当前服务提供 Qwen3.5-4B 结构化判断、模型与 adapter 状态查询。

- `app/`：模型运行 API，默认监听 `8010`。
- `code/local_qwen4b_eval.py`：本地 4060 冻结测试集评估器，支持全量、按序截取和类别均衡抽样。
- `scripts/run_local_4060_eval.ps1`：Windows 本地评估入口。
- `assets/README.md`：可用 adapter 与评估结果索引。
- `docs/2026-10-26-model-runtime-evaluation.html`：评估、续跑、显存限制和推理边界。

模型基座和训练产物位于 `model/training/`，运行服务只读取，不在本目录复制权重。

## 健康检查

```powershell
cd model\runtime
..\..\.venv-runtime-smoke\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

打开 `http://127.0.0.1:8010/health`。返回 `ready` 表示基座目录和 adapter 文件均可定位；返回 `degraded` 表示路径缺失，服务本身仍可启动。`/v1/models` 提供感知模型、adapter 和补充决策模型的角色索引，不会触发 GPU 加载。

后端分析链路调用 `POST /v1/judge`：输入病例元数据和受限影像引用，返回结构化标签、发现、置信度、adapter 指纹与推理时延，并固定要求 `requires_human_review=true`。服务只在首个有效请求时加载 4-bit 基座与 adapter，串行执行推理，失败或不可用时由后端独立降级，不影响核心流程和医生复核。

真实业务流程已经验证：后端上传病例影像后，运行服务通过共享上传根目录读取同一文件，结构化结果和运行元数据写回病例，持久任务一次完成。后端默认 Qwen 等待时间为 90 秒，覆盖首次加载；本机两次热推理为 2.528 秒和 2.958 秒，adapter 指纹一致，峰值保留显存 3.311 GiB。该结果只证明真实运行和回写链路，不代表模型置信度或临床泛化。

失败恢复回归可用 `scripts/run_recovery_regression.py` 复跑：依次验证运行服务不可用、推理超时、真实回写和服务重启恢复四个阶段，证据写入 `model/training/assets/qwen3.5-4b/runtime-recovery-local-4060-20261028-01/`。

## 本地 GPU 启动

运行服务必须使用 CUDA 版 PyTorch，不能把 CPU 版 `backend/.venv` 加入 `PYTHONPATH`。已验证的启动方式：

```powershell
cd model\runtime
$env:MODEL_RUNTIME_UPLOAD_ROOT = (Resolve-Path '..\training\datasets\training').Path
$env:MODEL_RUNTIME_INTERNAL_TOKEN = 'replace-with-shared-token'
..\..\.venv-runtime-smoke\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

真实基座与第 20 步 adapter 的本地烟测已完成：首次请求约 22 秒，热请求约 2.4–3.6 秒；常驻显存约 3.5 GiB，单图推理峰值分配 `3.275485 GiB`、峰值保留 `3.355469 GiB`。8 个并发请求经串行保护全部返回 HTTP 200，最慢约 14 秒。该结果只证明运行链路可用，不代表新增准确率证据；单图预测和受控 smoke 均不能替代独立外部验证。证据清单位于 `model/training/assets/qwen3.5-4b/runtime-smoke-local-4060-20261026-01/runtime_smoke.json`。

本地首次加载和推理串联执行时，后端默认等待时间设为 `APP_PERCEPTION_TIMEOUT_SECONDS=90`，覆盖冷启动；热请求通常远短于该上限。若服务端在加载期间超时，后端只把 Qwen 分支标记为 `failed` 并继续确定性报告，不会把未返回的模型结果写成成功。

图像预处理与训练/评估保持一致：原图通过解码像素上限保护后直接交给 processor，由 processor 按 `MODEL_RUNTIME_IMAGE_PIXELS` 和模型图像处理策略缩放，不再在服务端额外执行一次缩略图。

预处理修正后使用一张 CNV 训练图复测，返回 HTTP 200，热请求 `3.363 秒`，峰值保留 `3.355469 GiB`。模型返回 DRUSEN、置信度 0、impression 为空；这证明链路和结构化契约可用，但不能当作准确率或置信度可信度证据。当前运行输出必须由医生复核。

可用环境变量控制运行边界：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `MODEL_RUNTIME_MODEL_DIR` | 训练目录内的 Qwen3.5-4B | 基座目录 |
| `MODEL_RUNTIME_ADAPTER_DIR` | 第 20 步 `best_adapter` | 只读 adapter |
| `MODEL_RUNTIME_IMAGE_ROOT` | 训练数据目录 | 额外允许读取的图像根目录 |
| `MODEL_RUNTIME_UPLOAD_ROOT` | 空 | 病例上传根目录；应指向精确上传目录 |
| `MODEL_RUNTIME_INTERNAL_TOKEN` | 空 | 非空时要求 `X-Internal-Service-Token` |
| `MODEL_RUNTIME_IMAGE_PIXELS` | `65536` | 单图输入像素预算 |
| `MODEL_RUNTIME_MAX_NEW_TOKENS` | `32` | 生成 token 上限 |
| `MODEL_RUNTIME_MAX_IMAGES` | `4` | 单请求图像上限 |
| `MODEL_RUNTIME_INFERENCE_WAIT_SECONDS` | `35` | 串行推理锁的最长等待秒数 |

图像路径必须位于配置的允许根目录内；服务拒绝越界路径、不支持格式、超大文件、超大解码尺寸和未知任务。响应固定带 `requires_human_review=true` 与 `research_use_only=true`。

## 本地评估

```powershell
.\model\runtime\scripts\run_local_4060_eval.ps1 `
  -AdapterDir 'model\training\assets\qwen3.5-4b\local-4060-oct-focus-cont-20261025-01\best_adapter' `
  -OutputDir 'model\training\assets\qwen3.5-4b\eval-oct-step20-runtime-smoke-20261026-01' `
  -Tasks 'oct_aux_4class' -SamplesPerClass 4
```

`-SamplesPerClass N` 会为每个 `task + label` 固定取前 N 条，适合四类均衡的受控 smoke；`-MaxSamples N` 仍保留为按排序取前 N 条，两者互斥。抽样模式、可用类别数和实际选择数会写入 `eval_manifest.json`、`eval_metrics.json` 和 `eval_summary.json`。

评估会读取 `model/training/datasets/training/manifest.csv` 和冻结测试图像，不参与训练或 checkpoint 选择。没有 `-Overwrite` 时会从已有部分预测续跑。
