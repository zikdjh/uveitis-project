# Modal 已创建的训练存储

更新日期：2026-10-25

## Volume

| Volume | 用途 |
|---|---|
| `uveitis-data` | manifest、训练图像、标签和患者元数据 |
| `uveitis-models` | Qwen3.5-2B、Qwen3.5-4B、Intern-Decision-4B 基座权重 |
| `uveitis-runs` | adapter、checkpoint、评估结果和模型卡 |

## 数据卷中的路径

```text
/data/data/manifest.csv
/data/data/odir_metadata.csv
/data/data/rfmid_labels.csv
/data/data/summary.json
/data/data/data/01_uveitis_oct/
/data/data/data/02_toxofundus/
/data/data/data/03_eye_five_class/
/data/data/data/04_odir5k/
/data/data/data/06_rfmid2/
/data/data/data/13_zhanglab_oct/
```

训练 manifest 共 16,638 条，均为唯一图像路径；远端校验缺失文件数 0，数据卷约 1.59GB。

## 数据集实际使用量

| 数据集 | 可用图像 |
|---|---:|
| 01 葡萄膜炎 OCT | 75 |
| 02 ToxoFundus | 412 |
| 03 五分类眼病 | 2,297 |
| 04 ODIR 眼底泛化 | 2,000 |
| 06 RFMiD 2 | 854 |
| 13 ZhangLab OCT 辅助 | 11,000 |

ODIR 部分包含 1,000 个患者、左右眼各 1,000 张。03 仅用于原型训练，不作为最终临床测试集。

## 模型卷

```text
/models/qwen/Qwen3.5-2B/
/models/qwen/Qwen3.5-4B/
/models/internlm/Intern-Decision-4B/
```

模型卷中可见三款基座的权重、tokenizer、config、preprocessor 和许可文件。容量以 `modal volume ls` 或控制台统计为准；内部 Hugging Face 缓存可以保留以支持断点恢复。

## 训练产物卷

训练代码应写入：

```text
/runs/qwen3.5-2b/<run_id>/
/runs/qwen3.5-4b/<run_id>/
/runs/intern-decision-4b/<run_id>/
```

每个 run 至少保存 config、manifest 哈希、train metrics、eval metrics、最佳 checkpoint、最终 adapter 和 model card。训练后保存的是 adapter 与可恢复 checkpoint；只有部署需要单目录自包含模型时，才另存 merge 后的完整权重。

已完成的 4B run：

```text
/runs/qwen3.5-4b/qwen4b-diag-20261025-01/
/runs/qwen3.5-4b/qwen4b-cal-20261025-02/
/runs/qwen3.5-4b/qwen4b-pilot-20261025-01/
/runs/qwen3.5-4b/qwen4b-stage1-20261025-01/
```

标定 run 完成 20 个真实优化步，无跳过和 OOM。正式 run 完成 150 步，最佳验证损失在第 100 步；部署使用 SHA256 校验后的 `best_adapter/`，续训使用 `checkpoints/step-000100/training_state.pt`。正式 40 样本配对评估位于 `paired40/`，71 样本评估仍保留在 run 根目录。
