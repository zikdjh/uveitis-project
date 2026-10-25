# 葡萄膜炎智能体执行链路规划（2026-10-23）

目标：把诊断系统拆成一条可审计、可回滚、可扩展的智能体链路，而不是让一个大模型一次性完成所有任务。

## 1. 总体链路

```text
用户/医生输入
  -> IntakeAgent
  -> PreprocessAgent
  -> RouterAgent
  -> PerceptionAgent(Qwen3.5-4B)
  -> RetrievalAgent(BGE-M3)
  -> DecisionAgent(可选补充分支)
  -> SafetyAgent
  -> ReportAgent
  -> ReviewAgent
  -> LearningAgent
```

核心思想：

- 每个节点只做一件事。
- 每个节点都有明确的输入/输出 JSON。
- 所有结果都带 `case_id` 和 `trace_id`。
- 医生复核永远保留在链路里。

## 2. 节点职责

### 1. IntakeAgent

接收用户输入。

输入：

- 患者基本信息
- 主诉
- 病史
- 影像文件
- 已有检查结果

输出：

```json
{
  "case_id": "uuid",
  "patient": {
    "age": 41,
    "sex": "F"
  },
  "complaint": "眼红、视物模糊 3 天",
  "images": [
    {"type": "fundus", "path": "/cases/uuid/fundus_1.jpg"}
  ],
  "consent": true
}
```

### 2. PreprocessAgent

负责标准化和脱敏。

任务：

- 图像格式转换
- 去标识化
- 影像质量检查
- OCR 已有报告
- 生成统一 metadata

输出：

```json
{
  "quality": "pass",
  "images": [
    {"type": "fundus", "path": "/clean/uuid/fundus_1.jpg", "laterality": "OD"}
  ],
  "ocr_text": "...",
  "risk_flags": []
}
```

### 3. RouterAgent

决定使用哪条模态路径。

可路由到：

- fundus / UWF 路径
- OCT 路径
- anterior segment 路径
- text-only 路径

输出：

```json
{
  "route": ["fundus", "text"],
  "confidence": 0.94
}
```

### 4. PerceptionAgent

主力模型：Qwen3.5-4B。

任务：

- 影像理解
- 病灶描述
- 结构化发现
- 可疑诊断线索抽取

输出：

```json
{
  "findings": [
    {
      "finding": "vitreous opacity",
      "location": "posterior chamber",
      "confidence": 0.82
    }
  ],
  "impression": "suspected posterior uveitis",
  "report": "..."
}
```

### 5. RetrievalAgent

向量化模型：BGE-M3；向量数据库：zvec。

zvec 是嵌入式本地向量数据库，承担向量、标量字段和过滤条件的持久化检索，不另外部署独立向量服务。BGE-M3 只负责把文本转换为 DIM 维向量。

BGE-M3 从 ModelScope 的 `BAAI/bge-m3` 下载到项目本地，在 CPU 上以 FP32 运行，默认使用稠密向量。模型首次检索时惰性加载，不在 API 启动阶段占用内存。切换 embedding provider 后必须重建 zvec 索引。

本项目的集合为 `uveitis_knowledge`，默认维度 1024，使用 HNSW + COSINE。zvec 写入为单进程独占，一个集合不应由多个 API worker 同时打开；横向扩容时应改为独立检索服务或按分片拆分集合。

任务：

- 检索指南
- 检索相似病例
- 检索文献
- 提供可引用证据

输出：

```json
{
  "evidence": [
    {
      "id": "guideline_2026_014",
      "source": "RCOphth Uveitis dataset",
      "score": 0.87,
      "snippet": "..."
    }
  ]
}
```

### 6. DecisionAgent

状态：可选补充方案，默认关闭。是否启用由项目进度、真实决策标注质量和试点评测决定，不阻塞核心流程。

候选模型：Intern-Decision-4B；Kev-4B 作为对照，不默认常驻。

输入：

- PerceptionAgent 输出
- RetrievalAgent 证据
- 患者 metadata
- 临床主诉

输出：

```json
{
  "primary_class": "posterior_uveitis",
  "differential": [
    {"class": "toxoplasmosis", "score": 0.62},
    {"class": "VKH", "score": 0.24}
  ],
  "urgency": "medium",
  "recommended_action": [
    "fundus fluorescein angiography",
    "infectious workup"
  ],
  "evidence_ids": ["guideline_2026_014"],
  "confidence": 0.71
}
```

### 7. SafetyAgent

这是一个确定性校验节点，不是大模型。

检查：

- JSON schema 是否合法
- 是否缺少关键信息
- 是否给出高风险但无证据的结论
- 是否超出辅助诊断边界
- 是否需要转人工

失败时：

- 补充决策不可用时直接跳过该分支，不阻断检索、安全校验和医生复核
- 补充决策已启用但输出不合法时，返回 `noul` 或转医生人工判断
- 不把 Kev-4B 作为无条件的自动重试依赖

### 8. ReportAgent

生成医生端报告和患者友好说明。

输出：

- 医生报告
- 患者摘要
- 检查建议
- 证据引用

### 9. ReviewAgent

医生复核节点。

记录：

- 是否接受
- 修改后的诊断
- 不同意原因
- 是否允许入训练集

### 10. LearningAgent

后台节点，不在线上实时跑。

任务：

- 复核结果入库
- 构建微调样本
- 触发下一轮训练
- 记录模型版本

## 3. Modal 部署结构

| 服务 | 类型 | GPU | 说明 |
|---|---|---:|---|
| intake | API | 0 | 轻量 |
| preprocess | Worker | 0/1 | 可用 CPU 完成 |
| router | API | 0 | 小模型即可 |
| perception | Inference | L40S | Qwen3.5-4B |
| retrieval | Inference | L4/T4 | BGE-M3 |
| decision | Inference（按需） | L40S | 补充方案通过门槛后再启用 |
| safety | API | 0 | 确定性规则 |
| report | API | 0/1 | 文本生成 |
| review | API | 0 | 医生复核 |
| learning | Batch | L40S | 训练 |

## 4. 状态存储

| 存储 | 用途 |
|---|---|
| Volume: raw | 原始影像 |
| Volume: clean | 清洗后影像 |
| Volume: models | 模型和 adapter |
| Volume: index | 向量索引 |
| Volume: runs | 日志、评估、训练输出 |
| DB: cases | 病例状态 |
| DB: feedback | 医生复核 |

## 5. 失败与回退

| 失败点 | 处理 |
|---|---|
| 图像质量不合格 | 返回重拍/补图，不强行诊断 |
| Perception 超时 | 降级为 text-only |
| Retrieval 无高置信证据 | 保留证据缺口提示，不生成越界结论 |
| 补充决策未启用或不可用 | 跳过该分支，直接进入安全校验和人工复核 |
| Decision JSON 不合法 | 返回 `noul`，必要时转人工复核 |
| 置信度低于阈值 | 转 `noul` + 人工复核 |

## 6. 最小可用版本 MVP

第一阶段只需要保留：

```text
Intake -> Preprocess -> Perception -> Retrieval -> Safety -> Report -> Review
```

Decision 为补充分支；Learning 可以后补。补充决策必须通过标注和评测门槛后再插入链路。

这样能最快跑通，且不会牺牲安全边界。
