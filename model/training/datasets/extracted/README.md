# 已解压数据集

整理时间：2026-10-25；公开数据补充：2026-10-26

当前结构：

```text
model/training/datasets/
├── raw/                        新的临时下载暂存区
├── extracted/                  本目录，统一解压后的完整数据集
│   ├── 01_uveitis_oct/
│   ├── ...
│   ├── 13_zhanglab/
│   ├── 14_open_uwf700/
│   ├── 15_zenodo_tb_uveitis_ifn/
│   ├── 16_zenodo_vitreous_classification/
│   ├── 17_zenodo_dm_anterior_uveitis/
│   ├── 18_figshare_anterior_uveitis_endothelium/
│   ├── 19_figshare_uveitis_clinical_tables/
│   ├── README.md               本说明
│   └── manifests/
│       ├── extracted-files.csv 逐文件清单
│       ├── public-downloads-2026-10-26.csv 本次公开数据逐文件清单
│       ├── public-download-sources-2026-10-27.json 2026-10-27 新增两份表格的来源登记
│       └── archive-cleanup-2026-10-25.csv 已删除压缩包的来源账本
└── training/                 Modal 训练用精简数据与标签
```

已移除 macOS `__MACOSX` 与 `.DS_Store` 元数据，并展开 RFMiD2 与 ZhangLabData 的嵌套压缩包。2026-10-25 已删除 14 个根目录下载 ZIP 和 4 个重复内层 ZIP；删除前，17 个归档的 182,754 个数据成员全部通过文件名、大小和 CRC 校验，未发现缺失或不一致。

数据集不再从根目录散放的 ZIP 直接使用。以后新下载的包先放 `model/training/datasets/raw/`，解压、核验并登记后再移入本目录；`raw/` 不应长期保存已经完整解压的包。

2026-10-26 通过本地代理新增 4 组公开数据。`14_open_uwf700` 的源 ZIP 为 9,018,811,972 字节，MD5 为 `ddee42dc99792545654a65413c0fdb6f`；解压后已删除源 ZIP 与断点状态文件。新增数据已登记到 `manifests/public-downloads-2026-10-26.csv`。

## 快速入口

| 编号 | 数据集 | 文件数 | 图像数 | 主要标签 / 元数据 | 用途 |
|---|---|---:|---:|---|---|
| 01 | 葡萄膜炎 OCT | 75 | 75 | 4 个类别目录 | 葡萄膜炎 OCT 原型 |
| 02 | ToxoFundus | 592 | 412 张眼底图 + 179 张掩膜 | `dataset_labels.csv`、`masks/` | 眼弓形虫病分类与分割 |
| 03 | 五分类眼病 | 2,300 | 2,298 | 5 个类别目录、2 个 notebook | 葡萄膜炎 / 结膜炎 / 白内障 / 眼睑病 / 正常 |
| 04 | ODIR-5K 预处理版 | 14,394 | 14,392 | `full_df.csv`、`ODIR-5K/ODIR-5K/data.xlsx` | 多病种眼底分类 |
| 05 | 眼底 1000 图 | 2,000 | 2,000 | 按类别编号分目录 | 眼底分类补充 |
| 06 | RFMiD 2.0 | 866 | 860 | 训练 / 验证 / 测试三套 CSV | 45 类长尾眼底病 |
| 07 | ADAM | 5,258 | 5,253 | 分类 GT、Fovea 坐标 XLSX | 眼底分类与视盘 / 黄斑定位 |
| 08 | AGE | 8,004 | 8,000 | 分类与检测参考 XLSX / CSV | 前节 OCT / 眼底 |
| 09 | GOALS | 900 | 897 | 训练 / 验证 / 测试 XLSX | 青光眼评估 |
| 10 | PALM | 4,876 | 4,873 | 分类与 Fovea 坐标 XLSX | 眼底分类与黄斑定位 |
| 11 | REFUGE 多标注 | 21,613 | 20,410 | 3 个 CSV、逐图 XLSX | 青光眼 / 视盘与多标注 |
| 12 | REFUGE2 | 4,407 | 4,400 | 分类 / Fovea CSV 与 XLSX | 青光眼评估 |
| 13 | ZhangLabData | 115,175 | 115,165 | 按类别目录 | 含 OCT 与胸部 X 光，不是单一葡萄膜炎集 |
| 14 | Open UWF 700 | 703 | 700 | 7 个类别各 100 张；人口学、真值、逐医生质量评分 XLSX | 超广角眼底多病种分类；其中葡萄膜炎 100 张 |
| 15 | 结核相关葡萄膜炎 IFN 数据 | 1 | 0 | 基因表达 XLSX | 结核阳性葡萄膜炎风险分层 |
| 16 | 玻璃体标本葡萄膜炎分类 | 1 | 0 | 临床实验室 XLSX | 玻璃体标本辅助分类 |
| 17 | 糖尿病合并前葡萄膜炎 | 2 | 0 | 回顾性横断面 XLSX 与原始数据 PDF | 真实病例临床特征补充 |
| 18 | 前葡萄膜炎角膜内皮 | 1 | 0 | 前节/内皮临床变量 XLSX | 前葡萄膜炎真实病例临床变量 |
| 19 | 葡萄膜炎临床与病因表 | 2 | 0 | 75 眼临床 CSV、28 例病因 CSV | 影像临床对照与医生确认病因标签 |

合计 181,167 个文件，其中 179,914 张图像。数量按文件扩展名统计，不对标签唯一性或患者切分作保证。

## 目录详情

### 01 葡萄膜炎 OCT

根目录：

`01_uveitis_oct/Optical Coherence Tomography (OCT) Images of Proliferative Vitreoretinopathy, Uveitis, and Normal Eyes/`

类别：`Intermediate+Posterior Uveitis`、`Normal`、`Panuveitis`、`RRD-PVR`。

这 75 张图像原本没有患者信息。2026-10-27 在 figshare `22632715` 找到逐类别计数完全一致的 75 眼临床对照表（`RRD-PVR` 19、`Intermediate+Posterior Uveitis` 12、`Panuveitis` 16、`Normal` 28），其中 28 例葡萄膜炎还带医生给出的病因标签（Toxoplasma 8、Sifilis 7、Tuberculosis 6、Idiopathic 3、Paraneoplastic syndrome 2、CMV 1、VKH 1）。图像到临床行的映射由类别内序号推断，记录在 `model/training/datasets/tasks/oct_uveitis_clinical/clinical-link.csv`，审计见同目录 `audit.json`；在用于患者级分组前必须先与数据作者确认该映射。

### 02 ToxoFundus

根目录：`02_toxofundus/`

文件：`dataset_labels.csv`、`images/`、`masks/`。CSV 字段为 `Image name,Label,Source`。

`images/` 实际有 412 张眼底图，`masks/` 有 179 张分割掩膜；掩膜不应当作独立分类图像。412 张图像均有分类标签，其中 144 张可匹配到掩膜，可用于分割辅助任务。

分类标签表与实际图像只有一处文件名差异：标签表为 `2809.jpg`，图像目录为 `2805.jpg`；两侧各自只差这一条，因此按唯一对应关系显式配对为 `2805.jpg ← 2809.jpg`（标签为 `active`），并在任务清单中记录，不做静默匹配。核对结果见 `model/training/datasets/tasks/fundus_toxo_binary/audit.json`：

- 源标签 412 条、源图像 412 张、暂存图像 412 张三方一致，图像内容重复 0 组。
- 原始标签分布为 healthy 132、inactive 187、active 34、active/inactive 57、active/active 1、inactive/inactive 1。
- 该数据集**没有患者 ID**，现有的 train 330 / test 82 切分按图像进行，只能做数据集内评估，不能宣称患者级外部验证。
- 训练任务为 `fundus_toxo_binary`（healthy 对 toxoplasmosis），运行清单是 `model/training/datasets/training/manifest.csv`。

### 03 五分类眼病

根目录：

`03_eye_five_class/Image Dataset on Eye Diseases Classification (Uveitis, Conjunctivitis, Cataract, Eyelid) with Symptoms and SMOTE Validation/`

类别：`Cataract`、`Conjunctivitis`、`Eyelid`、`Normal`、`Uveitis`。

另含 `Duplicate.ipynb` 和 `Eye_Diseases_Classifications_Pre_Processing_Dataset.ipynb`。原包不含独立 CSV 标签表，类别由目录名提供。

### 04 ODIR-5K 预处理版

根目录：`04_odir5k_preprocessed/`

主要文件：

- `full_df.csv`：患者年龄、性别、左右眼文件名、诊断关键词、8 个病种标签与预处理路径。
- `ODIR-5K/ODIR-5K/data.xlsx`：原始 ODIR 标注。
- `ODIR-5K/ODIR-5K/Training Images/`、`Testing Images/`：左右眼图像。
- `preprocessed_images/`：预处理图像副本。

### 05 眼底 1000 图

根目录：`05_fundus_1000/1000images/`

按类别编号和名称分目录，共 80 个子目录。

### 06 RFMiD 2.0

根目录：`06_rfmid2/`

- `Training_set/`：510 个文件，标签为 `RFMiD_2_Training_labels.csv`。
- `Validation_set/`：178 个文件，标签为 `RFMiD_2_Validation_labels.csv`。
- `Test_set/`：175 个文件，标签为 `RFMiD_2_Testing_labels.csv`。

三个子集各有独立图像目录和 CSV，适合直接按原划分训练。

### 07 ADAM

根目录：`07_adam/ADAM/`

包含 `Train/`、`Validation/`、`Test/`，每套含分类 GT 与 Fovea 坐标 XLSX。

### 08 AGE

根目录：`08_age/AGE/`

包含 `Train/`、`Validation/`、`Test/`。标签包括分类 XLSX 与检测参考 CSV。

### 09 GOALS

根目录：`09_goals/GOALS/`

包含 `Train/`、`Validation/`、`Test/`，各含 `*_GC_GT.xlsx` 标签。

### 10 PALM

根目录：`10_palm/PALM/`

包含 `Train/`、`Validation/`、`Test/`，标签包括分类和 Fovea 坐标 XLSX。

### 11 REFUGE 多标注

根目录：`11_refuge_multirater/REFUGE-Multi-rater Data/`

含 `REFUGE1Test.csv`、`REFUGE1Val.csv`、`REFUGETrain.csv`，以及逐图多标注 XLSX。目录结构较深，共 1,204 个子目录。

### 12 REFUGE2

根目录：`12_refuge2/REFUGE2/`

含 `Train/`、`Validation/`、`Test/`，标签分布在 CSV 与 XLSX 中。

### 13 ZhangLabData

根目录：`13_zhanglab/ZhangLabData/`

包含 `CellData/OCT/`、`CellData/chest_xray/`、`CellData/code/`。

`CellData/OCT/train/` 四类：CNV 37,205、DME 11,348、DRUSEN 8,616、NORMAL 51,140。`test/` 四类各 250 张。

这一套 OCT 的类别是 CNV / DME / DRUSEN / NORMAL，不应与葡萄膜炎 OCT 的类别直接合并。

### 14 Open UWF 700

根目录：`14_open_uwf700/`

来源：Figshare `10.6084/m9.figshare.26936446`，许可为 CC BY 4.0。

包含 `Original UWF Image/`、`Demographics of the participants.xlsx`、`Ground Truth.xlsx` 和 `Individual Quality Assessment.xlsx`。图像类别为 `AMD`、`DR`、`Healthy`、`PM`、`RD`、`RVO`、`Uveitis`，每类 100 张。

`Uveitis` 子集可用于超广角眼底的葡萄膜炎二分类和外部补充，但整个数据集是多病种分类集，不能把其他六类都当作葡萄膜炎亚型。人口学、真值和质量评分文件应按原始字段核对后再构建训练清单。

### 15 结核相关葡萄膜炎 IFN 数据

根目录：`15_zenodo_tb_uveitis_ifn/`

来源：Zenodo `10.5061/dryad.8jk03jd`，许可为 CC0。

文件：`tb_uveitis_ifn_gene_signature.xlsx`。内容是 QuantiFERON Gold 阳性葡萄膜炎患者的 I 型干扰素诱导基因表达数据，用于活动性结核高/低风险分层。它是临床实验室变量，不是眼底或 OCT 图像。

### 16 玻璃体标本葡萄膜炎分类

根目录：`16_zenodo_vitreous_classification/`

来源：Zenodo `10.5061/dryad.597ch`，许可为 CC0。

文件：`vitreous_uveitis_classification.xlsx`。该数据来自玻璃体标本的葡萄膜炎分类前瞻性多中心观察研究，可作为实验室变量和分类标签的补充来源。

### 17 糖尿病合并前葡萄膜炎

根目录：`17_zenodo_dm_anterior_uveitis/`

来源：Zenodo `10.5281/zenodo.21808930` 与 `10.5281/zenodo.23054920`，许可为 CC BY 4.0。

文件：`diabetes_anterior_uveitis.xlsx` 和 `diabetes_anterior_uveitis_raw_data.pdf`。内容为泰国患者糖尿病、血糖控制与非特异性前葡萄膜炎关系的回顾性横断面数据。样本规模和终点与主任务不同，只能作为真实病例特征补充。

### 18 前葡萄膜炎角膜内皮

根目录：`18_figshare_anterior_uveitis_endothelium/`

来源：Figshare `10.6084/m9.figshare.32054064`，许可为 CC BY 4.0，开放访问。

文件：`dataset_uveitis_endothelium.xlsx`，152 行。字段覆盖年龄、性别、诊断、眼别、视力、前节体征（结膜、角膜、细胞、KP、虹膜、瞳孔、晶体、角膜知觉）、眼压、杯盘比、房角、抗青光眼用药、激素使用、复发记录，以及患眼与对侧正常眼的内皮细胞计数、变异系数、六角形细胞比例和角膜厚度。属于患者级临床变量，可补充决策模型，不是影像数据。

### 19 葡萄膜炎临床与病因表

根目录：`19_figshare_uveitis_clinical_tables/`

来源：Figshare `10.6084/m9.figshare.22632715`，许可为 CC BY 4.0，开放访问。

文件：

- `characteristics_pvr_uveitis_normal.csv`：75 眼，字段为编号、诊断、年龄、性别、视力、VIT/RPE 相对强度。
- `characteristics_uveitis_patients.csv`：28 例葡萄膜炎，字段为编号、年龄、性别、视力、诊断、病因。

它与 `01_uveitis_oct` 的 75 张图像逐类别计数一致，是这批 OCT 的临床对照表，并给出医生确认的病因标签。图像到临床行的映射是推断的，登记在 `model/training/datasets/tasks/oct_uveitis_clinical/`。

## 使用注意

- 原始数据许可与使用范围仍以各数据集源站说明为准。
- `03_eye_five_class` 是 SMOTE 验证版本，类别目录可能包含合成或重复图像，不能直接当作独立患者样本。
- ODIR-5K 的左右眼来自同一患者，切分时必须按患者分组，避免同患者跨训练集与测试集泄漏。
- 多套数据之间存在相似或重复来源的可能，跨数据集合并前应做哈希或感知哈希去重。
- 当前索引只做目录与文件完整性整理，尚未统一标签命名、患者 ID 或生成训练 manifest。

机器可读的逐文件清单见 `manifests/extracted-files.csv`，当前登记 180,456 条记录，不包含已删除的 4 个重复 ZIP。2026-10-26 新增的 707 个文件登记在 `manifests/public-downloads-2026-10-26.csv`，来源、许可和校验值登记在 `manifests/public-download-sources-2026-10-26.json`。训练子集清单则在 `model/training/datasets/training/manifest.csv`，两者用途不同。
