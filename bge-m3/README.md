# 向量模型服务

BGE-M3 向量模型统一在本目录作为独立 FastAPI 服务运行：backend 不再加载模型权重，只通过 HTTP 接口获取文本向量。zvec 向量库仍留在 backend 进程内，负责持久化与检索。

- `app/`：向量模型 API，默认监听 `8011`。
- `tests/`：接口契约测试（健康检查、内部令牌、输入校验、模型缺失降级）。
- `models/bge-m3/`：模型权重目录（已加入 `.gitignore`，不随代码提交）。

## 接口契约

- `GET /health`：返回服务状态、模型路径、维度与加载状态。权重目录缺少 `config.json` 时返回 `degraded`，服务本身仍可启动。
- `POST /v1/embeddings`：输入 `{"input": "文本"}`，返回 `{"embedding": [...], "dimension": 1024, "model": "BAAI/bge-m3", "latency_ms": ..., "generated_at": ...}`。响应同时兼容 OpenAI 风格调用方的 `data[0].embedding` 解析路径。
- 设置 `EMBEDDING_INTERNAL_TOKEN` 后，所有 `/v1/embeddings` 请求必须携带 `X-Internal-Service-Token`，与 Qwen 运行服务的内部令牌约定一致。

## 模型下载

权重通过 ModelScope 固定来源 `BAAI/bge-m3` 下载到本目录（约 2.3 GB，不进 Git）：

```powershell
.\backend\.venv\Scripts\python.exe -c "from modelscope.hub.snapshot_download import snapshot_download; snapshot_download('BAAI/bge-m3', local_dir='bge-m3/models/bge-m3')"
```

如果权重仍在旧位置 `backend/models/bge-m3/`，直接移动到 `bge-m3/models/bge-m3/` 即可，无需重新下载。

## 本地启动

```powershell
cd bge-m3
$env:EMBEDDING_INTERNAL_TOKEN = 'replace-with-shared-token'
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

首次向量化请求加载权重并常驻 CPU；`GET /health` 不触发加载。可用环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `EMBEDDING_MODEL_PATH` | 本目录 `models/bge-m3` | 权重目录 |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-m3` | 健康检查与响应中的模型名 |
| `EMBEDDING_DIMENSION` | `1024` | 校验输出向量维度 |
| `EMBEDDING_BATCH_SIZE` | `8` | 单次编码 batch 上限 |
| `EMBEDDING_MAX_LENGTH` | `1024` | 单条文本最大 token 长度 |
| `EMBEDDING_INTERNAL_TOKEN` | 空 | 非空时要求 `X-Internal-Service-Token` |

## 与 backend 对接

backend 通过 `APP_VECTOR_PROVIDER=remote` 与 `APP_RETRIEVAL_SERVICE_URL=http://127.0.0.1:8011` 使用本服务；`APP_INTERNAL_SERVICE_TOKEN` 非空时以内部令牌头调用。embedding 服务不可用时知识检索分支按既有约定跳过，不阻塞病例分析与医生复核。切换 provider 或向量空间后必须重建 zvec 索引，避免新旧向量混检。
