# Modal + L40S 训练规划（2026-10-23）

目标：把 P0/P1 数据集和模型挂载到 Modal，用 L40S 优先训练出可评估的 Qwen3.5-4B 葡萄膜炎辅助诊断原型。Qwen3.5-2B 只作资源或效果对照，Intern-Decision-4B 默认关闭。预算受限时以 [Modal L40S 预算排期](2026-10-25-training-budget-plan-modal-l40s.html) 为准。

## 1. 基本判断

- Modal L40S 是 48GB 显存，不需要再按 24GB 保守规划。
- 4B 级模型用 LoRA / QLoRA 足够，不建议一开始就做全参微调。
- 数据先用 P0 跑通闭环，P1 后续叠加做增强。
- 核心模型与补充决策模型分开评估；补充决策不阻塞第一阶段闭环。

## 2. Modal 资源结构

建议用三个 Volume：

| Volume | 挂载点 | 内容 |
|---|---|---|
| `uveitis-data` | `/data` | P0/P1 数据集、manifest、缓存 |
| `uveitis-models` | `/models` | 基座模型、LoRA adapter、合并后模型 |
| `uveitis-runs` | `/runs` | checkpoint、日志、评估结果 |

建议 Modal 镜像里预装：

- `torch`
- `transformers`
- `peft`
- `accelerate`
- `bitsandbytes`
- `datasets`
- `sentence-transformers`
- `zvec`
- `wandb`

GPU 一律先用 `L40S`，单卡起步。不要多卡并行，先把 pipeline 跑通。

## 3. 训练阶段

### 阶段 0：数据准备

- 统一图像格式为 `jpg/png`。
- 建立统一 manifest：`patient_id`、`image_path`、`label`、`caption`、`metadata`。
- 按患者切分 train/val/test，避免同患者跨集泄漏。
- P0 数据先做最小闭环；五分类 v2 只做原型验证，不进最终指标。
- 生成缓存：tokenized dataset、image tensor cache。

### 阶段 1：零样本基线

先用现成模型跑一次基线，不训练：

- Qwen3.5-4B 做影像分类和结构化输出。
- Intern-Decision-4B 只在决策数据门槛通过后作为补充基线。
- BGE-M3 生成向量，zvec 建立并持久化本地检索索引。

记录指标，方便判断训练是否真的有提升。

### 阶段 2：多模态模型微调

模型：Qwen3.5-4B

策略：

- 4-bit NF4 QLoRA，`bf16` 计算。
- LoRA 微调语言层；图像编码器默认冻结。
- `gradient_checkpointing`
- 第一阶段 `max_seq_len = 1024`、`max_pixels = 448 x 448`
- micro-batch 1，grad accum 8-16
- 从 train 行固定验证集，early stop，不碰冻结 test

任务：

- 影像描述
- 病种分类
- 病灶定位描述
- 结构化报告生成

### 阶段 3：补充决策模型微调（条件执行）

候选：Intern-Decision-4B；Kev-4B 作为对照。是否执行由项目进度、真实决策标注和评测结果决定。

策略：

- LoRA / QLoRA
- 输入：病例摘要、影像描述、检索证据
- 输出：typed decision JSON
- 目标是稳定输出 `choice`、`score`、`noul`

没有足够的医生确认决策标签时，本阶段直接跳过，把预算用于影像模型测试和错误分析。

### 阶段 4：向量检索

模型：BAAI/bge-m3

第一阶段不微调，只做：

- 指南 / 文献 / 病例摘要 embedding
- zvec HNSW 索引（嵌入式本地数据库，无需额外向量服务）
- 检索测试集评测

第二阶段如果需要，再做 LoRA 对比学习。

### 阶段 5：联调与评估

评估维度：

- 分类 accuracy / macro-F1 / AUC
- 检索 recall@k
- 决策 JSON 合法率
- 决策与医生标注一致率
- 幻觉率

输出：

- 核心模型单独成绩
- 补充决策启用前后的对照成绩
- 与零样本基线对比

## 4. 执行顺序

1. 数据清洗和 manifest。
2. Modal 训练脚本跑通 smoke test。
3. 零样本基线。
4. Qwen3.5-4B QLoRA。
5. BGE-M3 向量化并写入 zvec 索引。
6. 核心链路评估与医生复核闭环。
7. 决策数据过关后，再执行补充决策模型实验。
8. 输出评估报告。

## 5. 风险

- 小样本数据容易过拟合，用 early stop 和冻结层控制。
- 临床数据要严格按患者切分。
- 补充决策模型必须通过数据门槛、JSON schema 校验和独立测试集评测。
- 不要直接把非商用数据进入生产。
- 医疗输出必须保留人工复核。
