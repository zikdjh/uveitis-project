#!/usr/bin/env python3
"""Build and validate the offline documentation site.

README.md is the standard Markdown entry point for a directory. Other project
documents use HTML as their final source.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
SOURCE_CACHE = ROOT / "scripts/docs/.html-source"


@dataclass(frozen=True)
class Page:
    source: Path
    output: str
    title: str
    category: str
    summary: str
    date: str
    kind: str


PAGES = (
    Page(Path("README.md"), "2026-10-26-project-overview.html", "项目总览", "项目", "系统边界、训练与运行目录、当前状态和启动方式", "2026-10-26", "markdown"),
    Page(Path("model-training/README.md"), "2026-10-26-model-training-management.html", "模型训练管理", "训练", "训练代码、环境、数据、计划和产物的统一入口", "2026-10-26", "markdown"),
    Page(Path("model-runtime/README.md"), "2026-10-26-model-runtime.html", "模型运行服务", "运行", "运行 API、评估入口、资产读取边界和健康检查", "2026-10-26", "markdown"),
    Page(Path("model-training/assets/README.md"), "2026-10-26-training-assets-index.html", "训练产物索引", "训练", "当前 adapter、训练指标、冻结评估结果和保存约定", "2026-10-26", "markdown"),
    Page(Path("scripts/docs/.html-source/2026-10-26-project-layout.html"), "2026-10-26-project-layout.html", "项目目录索引", "项目", "训练、运行、数据、业务代码和证据目录的边界", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-project-development-progress.html"), "2026-10-26-project-development-progress.html", "项目开发进度与 11.10 收口计划", "项目", "三端开发、鉴权、数据集、模型运行集成的阶段状态和验收排期", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-progress-tracking.html"), "2026-10-26-progress-tracking.html", "项目进度与模型训练进度跟踪", "项目", "项目、训练、验收、风险和决策记录的滚动跟踪看板", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-model-training-status.html"), "2026-10-26-model-training-status.html", "训练状态", "训练", "当前模型、数据、checkpoint、预算和硬件状态", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-model-training-progress.html"), "2026-10-26-model-training-progress.html", "模型训练进度与 11.10 收口计划", "训练", "Qwen3.5-4B 本地训练、冻结评估、选型门槛和后续排期", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-qwen3.5-4b-progress-stop.html"), "2026-10-26-qwen3.5-4b-progress-stop.html", "Qwen3.5-4B 训练进度与停止点", "训练", "本地训练、内部验证、冻结测试进度与恢复方式", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-qwen3.5-4b-training-review.html"), "2026-10-26-qwen3.5-4b-training-review.html", "Qwen3.5-4B 训练审核", "训练", "分组续训、数据审计、验证结果与后续判断", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-training-plan-modal-l40s.html"), "2026-10-23-training-plan-modal-l40s.html", "Modal L40S 训练规划", "训练", "Qwen 主模型、补充决策模型和 Modal 资源阶段", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-25-training-cost-ledger-modal.html"), "2026-10-25-training-cost-ledger-modal.html", "Modal 训练消耗清单", "训练", "实际账单、资源消耗、训练结果和预算依据", "2026-10-25", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-25-training-budget-plan-modal-l40s.html"), "2026-10-25-training-budget-plan-modal-l40s.html", "Modal L40S 预算排期", "训练", "本月与下月预算、训练顺序和数据集安排", "2026-10-25", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-dataset-training-map.html"), "2026-10-26-dataset-training-map.html", "数据集训练映射", "数据", "影像、检索和决策任务的样本构造与验收指标", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-27-uveitis-open-data-audit.html"), "2026-10-27-uveitis-open-data-audit.html", "葡萄膜炎开放数据审计", "数据", "在用数据集许可、访问方式、患者级隔离能力与外部候选数据的核验结论", "2026-10-27", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-27-uveitis-focus-training.html"), "2026-10-27-uveitis-focus-training.html", "毒浆体病辅助训练与冻结评估", "训练", "ToxoFundus 与 Open UWF 训练行、一次性冻结评估和晋级边界", "2026-10-27", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-modal-training-storage.html"), "2026-10-26-modal-training-storage.html", "Modal 训练存储约定", "基础设施", "Volume 挂载、产物目录、checkpoint 与恢复方式", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-modal-uploaded-artifacts.html"), "2026-10-26-modal-uploaded-artifacts.html", "Modal 已上传产物", "基础设施", "训练数据卷、模型卷和训练产物卷的实际内容", "2026-10-26", "html"),
    Page(Path("model-training/datasets/extracted/README.md"), "2026-10-26-dataset-index.html", "数据集目录索引", "数据", "已解压数据集的规模、标签、目录和清理后的结构", "2026-10-26", "markdown"),
    Page(Path("scripts/docs/.html-source/2026-10-25-redundant-archives.html"), "2026-10-25-redundant-archives.html", "压缩包清理记录", "数据", "已删除归档的校验结果、容量和后续暂存规则", "2026-10-25", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-agent-execution-chain.html"), "2026-10-23-agent-execution-chain.html", "智能体执行链路规划", "系统设计", "病例接入、影像感知、检索、决策和安全复核链路", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-auth-access-control.html"), "2026-10-26-auth-access-control.html", "系统鉴权与权限体系", "系统设计", "双令牌无感刷新、角色权限、CSRF、账号管理和审计边界", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-cn-eye-datasets.html"), "2026-10-23-cn-eye-datasets.html", "国内眼科数据集核验", "数据", "国内开源免费眼科数据集的许可、规模和可用性", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-intl-eye-datasets.html"), "2026-10-23-intl-eye-datasets.html", "国外眼科数据集核验", "数据", "国外开源免费眼科数据集的许可、规模和申请方式", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-manual-download-links.html"), "2026-10-23-manual-download-links.html", "手动下载清单", "数据", "数据集条目页、下载入口与人工下载状态", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-recommended-datasets.html"), "2026-10-23-recommended-datasets.html", "推荐数据集清单", "数据", "P0/P1 数据集、体量、许可和获取渠道", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-model-24gb.html"), "2026-10-23-model-24gb.html", "24GB 显卡模型选型", "模型", "24GB 显卡上的候选模型、资源与部署选型", "2026-10-23", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-23-model-trio-24gb.html"), "2026-10-23-model-trio-24gb.html", "24GB 核心模型方案", "模型", "Qwen、补充决策模型与 BGE-M3 的三模型方案", "2026-10-23", "html"),
    Page(Path("model-training/assets/reference/24GB_GPU_Cloud_Price_List_2026-10-25.html"), "2026-10-25-gpu-cloud-price-list.html", "24GB 显存 GPU 云价格清单", "参考", "历史云 GPU 报价快照与预算筛选参考", "2026-10-25", "html"),
    Page(Path("model-runtime/assets/README.md"), "2026-10-26-model-runtime-assets.html", "模型运行资产索引", "运行", "运行 adapter、冻结评估结果和路径读取约定", "2026-10-26", "markdown"),
    Page(Path("scripts/docs/.html-source/2026-10-26-model-runtime-evaluation.html"), "2026-10-26-model-runtime-evaluation.html", "模型评估与推理说明", "运行", "本地评估、冻结测试、显存限制与推理边界", "2026-10-26", "html"),
    Page(Path("scripts/docs/.html-source/2026-10-26-outputs-guide.html"), "2026-10-26-outputs-guide.html", "运行输出说明", "项目", "临时输出与长期训练证据的归档边界", "2026-10-26", "html"),
)

LEGACY = {
    "2026-10-25-artifacts-index.html": "2026-10-26-training-assets-index.html",
    "2026-10-25-dataset-index.html": "2026-10-26-dataset-index.html",
    "2026-10-25-dataset-training-map.html": "2026-10-26-dataset-training-map.html",
    "2026-10-25-document-catalog.html": "2026-10-26-document-catalog.html",
    "2026-10-25-modal-training-storage.html": "2026-10-26-modal-training-storage.html",
    "2026-10-25-modal-uploaded-artifacts.html": "2026-10-26-modal-uploaded-artifacts.html",
    "2026-10-25-model-training-management.html": "2026-10-26-model-training-management.html",
    "2026-10-25-model-training-status.html": "2026-10-26-model-training-status.html",
    "2026-10-25-outputs-guide.html": "2026-10-26-outputs-guide.html",
    "2026-10-25-project-layout.html": "2026-10-26-project-layout.html",
    "2026-10-25-project-overview.html": "2026-10-26-project-overview.html",
    "2026-10-25-qwen3.5-4b-progress-stop.html": "2026-10-26-qwen3.5-4b-progress-stop.html",
    "cn-eye-datasets-20261023.html": "2026-10-23-cn-eye-datasets.html",
    "intl-eye-datasets-20261023.html": "2026-10-23-intl-eye-datasets.html",
    "manual-download-links-20261023.html": "2026-10-23-manual-download-links.html",
    "recommended-datasets-20261023.html": "2026-10-23-recommended-datasets.html",
    "model-24gb-20261023.html": "2026-10-23-model-24gb.html",
    "model-trio-24gb-20261023.html": "2026-10-23-model-trio-24gb.html",
}

README_SOURCES = {
    Path("README.md"),
    Path("model-training/README.md"),
    Path("model-runtime/README.md"),
    Path("model-training/assets/README.md"),
    Path("outputs/README.md"),
    Path("model-training/datasets/extracted/README.md"),
    Path("model-runtime/assets/README.md"),
}

README_MAP = {
    Path("README.md"): "2026-10-26-project-overview.html",
    Path("model-training/README.md"): "2026-10-26-model-training-management.html",
    Path("model-runtime/README.md"): "2026-10-26-model-runtime.html",
    Path("model-training/assets/README.md"): "2026-10-26-training-assets-index.html",
    Path("outputs/README.md"): "2026-10-26-outputs-guide.html",
    Path("model-training/datasets/extracted/README.md"): "2026-10-26-dataset-index.html",
    Path("model-runtime/assets/README.md"): "2026-10-26-model-runtime-assets.html",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def normalize_href(href: str) -> str:
    if href.startswith(("http://", "https://", "mailto:", "#", "${")):
        return href
    path, separator, suffix = href.partition("?")
    path = LEGACY.get(path, path)
    if path.startswith("docs/"):
        path = path.removeprefix("docs/")
    if path.startswith("./docs/"):
        path = path.removeprefix("./docs/")
    if path.endswith("dataset-plan-20261023/SIZE-ESTIMATE.md"):
        return "2026-10-23-recommended-datasets.html"
    normalized = Path(path).as_posix()
    if normalized in {key.as_posix() for key in README_SOURCES}:
        path = README_MAP[Path(normalized)]
    elif normalized in {"PROJECT_LAYOUT.md", "./PROJECT_LAYOUT.md"}:
        path = "2026-10-26-project-layout.html"
    elif normalized in {"model-training/STATUS.md", "STATUS.md"}:
        path = "2026-10-26-model-training-status.html"
    elif normalized.endswith("qwen3.5-4B-progress-20261025-stop.md"):
        path = "2026-10-26-qwen3.5-4b-progress-stop.html"
    elif normalized.endswith("qwen3.5-4B-grouped-cont-training-review-20261025.md"):
        path = "2026-10-26-qwen3.5-4b-training-review.html"
    elif normalized.endswith("DATASET_TRAINING_MAP.md"):
        path = "2026-10-26-dataset-training-map.html"
    elif normalized.endswith("modal_training_storage.md"):
        path = "2026-10-26-modal-training-storage.html"
    elif normalized.endswith("modal_uploaded_artifacts.md"):
        path = "2026-10-26-modal-uploaded-artifacts.html"
    elif normalized.endswith("qwen4b-eval-guide.md"):
        path = "2026-10-26-model-runtime-evaluation.html"
    elif normalized.startswith("model-training/docs/training-"):
        if "budget" in normalized:
            path = "2026-10-25-training-budget-plan-modal-l40s.html"
        elif "cost" in normalized:
            path = "2026-10-25-training-cost-ledger-modal.html"
        else:
            path = "2026-10-23-training-plan-modal-l40s.html"
    elif normalized.endswith(".md"):
        stem = Path(normalized).stem
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9.-]+", stem):
            path = f"{stem}.html"
    return f"{path}?{suffix}" if separator else path


def repair_links(text: str) -> str:
    def markdown_link(match: re.Match[str]) -> str:
        label, target = match.groups()
        return f"[{label}]({normalize_href(target)})"

    def html_link(match: re.Match[str]) -> str:
        prefix, target, suffix = match.groups()
        return f"{prefix}{html.escape(normalize_href(target), quote=True)}{suffix}"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", markdown_link, text)
    return re.sub(
        r'(<a\b[^>]*\bhref=")([^"]+)("[^>]*>)',
        html_link,
        text,
        flags=re.IGNORECASE,
    )


def normalize_project_paths(text: str) -> str:
    text = re.sub(r"(?:model-training/){2,}", "model-training/", text)
    text = text.replace("model-training/assets/qwen3.5-4b/", "model-training/assets/qwen3.5-4b/")
    text = text.replace("docs/2026-10-25-training-budget-plan-modal-l40s.html", "2026-10-25-training-budget-plan-modal-l40s.html")
    text = text.replace("docs/2026-10-25-training-cost-ledger-modal.html", "2026-10-25-training-cost-ledger-modal.html")
    text = text.replace("reports/qwen3.5-4B-progress-20261025-stop.md", "2026-10-26-qwen3.5-4b-progress-stop.html")
    text = text.replace("model-training/docs/training-cost-ledger-modal-20261025.md", "2026-10-25-training-cost-ledger-modal.html")
    replacements = (
        ("docs/2026-10-25-project-overview.html", "docs/2026-10-26-project-overview.html"),
        ("docs/2026-10-25-project-layout.html", "docs/2026-10-26-project-layout.html"),
        ("docs/2026-10-25-model-training-status.html", "docs/2026-10-26-model-training-status.html"),
        ("docs/2026-10-25-dataset-index.html", "docs/2026-10-26-dataset-index.html"),
        ("docs/2026-10-25-dataset-training-map.html", "docs/2026-10-26-dataset-training-map.html"),
        ("docs/2026-10-25-model-training-management.html", "docs/2026-10-26-model-training-management.html"),
        ("docs/2026-10-25-artifacts-index.html", "docs/2026-10-26-training-assets-index.html"),
        ("docs/2026-10-25-outputs-guide.html", "docs/2026-10-26-outputs-guide.html"),
        (".\\.venv-modal\\", ".\\model-training\\.venv-modal\\"),
        ("./.venv-modal/", "./model-training/.venv-modal/"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def neighbors(index: int) -> tuple[Page, Page]:
    return (
        PAGES[index - 1] if index > 0 else PAGES[-1],
        PAGES[index + 1] if index + 1 < len(PAGES) else PAGES[0],
    )


def shell(page: Page, index: int, source_label: str, source: str, content: str) -> str:
    previous, following = neighbors(index)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page.title)} · 葡萄膜炎辅助诊断项目</title>
  <link rel="stylesheet" href="assets/docs.css">
  <link rel="stylesheet" href="assets/document-shell.css">
</head>
<body>
<a class="doc-skip" href="#doc-content">跳到正文</a>
<header class="doc-nav">
  <a class="doc-brand" href="2026-10-26-project-overview.html">葡萄膜炎项目文档</a>
  <nav aria-label="文档导航">
    <a href="2026-10-26-document-catalog.html">文档索引</a>
    <a href="{previous.output}">上一份</a>
    <a href="{following.output}">下一份</a>
  </nav>
</header>
<main id="doc-content" class="doc-page">
  <div class="doc-kicker">
    <span>{html.escape(page.category)}</span>
    <span>{page.date}</span>
  </div>
  <h1>{html.escape(page.title)}</h1>
  <p class="doc-summary">{html.escape(page.summary)}</p>
  <p class="doc-source">{source_label}：<code>{html.escape(source)}</code></p>
  <article class="html-body">
{content}
  </article>
</main>
<footer class="doc-footer">
  <span>{html.escape(page.title)} · {page.date}</span>
  <span><a href="2026-10-26-document-catalog.html">返回文档索引</a></span>
</footer>
</body>
</html>
"""


def markdown_page(page: Page, index: int) -> str:
    text = repair_links(normalize_project_paths(read_text(ROOT / page.source)))
    text = re.sub(r"\A\s*# [^\n]+\n+", "", text, count=1)
    parser = MarkdownIt("commonmark", {"html": False, "typographer": False})
    parser.enable("table")
    return shell(
        page,
        index,
        "规范入口",
        page.source.as_posix(),
        parser.render(text),
    )


def html_fragment(text: str) -> str:
    body = re.search(r"<body\b[^>]*>(.*)</body>", text, flags=re.IGNORECASE | re.DOTALL)
    if not body:
        raise ValueError("HTML document has no body")
    main = re.search(r"<main\b[^>]*>(.*)</main>", body.group(1), flags=re.IGNORECASE | re.DOTALL)
    if not main:
        raise ValueError("HTML document has no main content")
    content = main.group(1)
    content = re.sub(r'<div class="doc-kicker".*?</div>', "", content, count=1, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<h1>.*?</h1>', "", content, count=1, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<p class="doc-summary">.*?</p>', "", content, count=1, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<p class="doc-source">.*?</p>', "", content, count=1, flags=re.IGNORECASE | re.DOTALL)
    opening = re.search(r'<article\b[^>]*\bclass="html-body"[^>]*>', content, flags=re.IGNORECASE)
    if opening:
        content = content[:opening.start()] + content[opening.end():]
        closing = content.rfind("</article>")
        if closing == -1:
            raise ValueError("Outer html-body article has no closing tag")
        content = content[:closing] + content[closing + len("</article>"):]
    return content.strip()


def html_page(page: Page, index: int, source: Path | None = None) -> str:
    source = source or ROOT / page.source
    return shell(
        page,
        index,
        "HTML 源文件",
        source.relative_to(ROOT).as_posix(),
        html_fragment(repair_links(normalize_project_paths(read_text(source)))),
    )


def cached_source(page: Page) -> Path | None:
    path = SOURCE_CACHE / page.output
    if not path.is_file():
        return None
    text = read_text(path)
    return path


def captured_html_source(page: Page) -> Path | None:
    path = SOURCE_CACHE / page.output
    return path if path.is_file() else None


def render_page(page: Page, index: int) -> str:
    source = ROOT / page.source
    if page.kind == "markdown":
        cached = None
    else:
        cached = source if page.source.as_posix().startswith("scripts/docs/.html-source/") else cached_source(page)
    if cached is not None:
        return re.sub(r"[ \t]+$", "", html_page(page, index, cached), flags=re.MULTILINE)
    if source.is_file():
        rendered = markdown_page(page, index) if page.kind == "markdown" else html_page(page, index)
        return re.sub(r"[ \t]+$", "", rendered, flags=re.MULTILINE)
    raise FileNotFoundError(f"Missing source and cached HTML for {page.output}")


def catalog() -> str:
    groups = ("项目", "运行", "训练", "系统设计", "数据", "模型", "基础设施", "参考")
    sections = []
    for group in groups:
        pages = [page for page in PAGES if page.category == group]
        items = "\n".join(
            f"""      <li class="doc-card">
        <a href="{page.output}">
          <span class="doc-card-meta">{page.date} · {html.escape(page.category)}</span>
          <strong>{html.escape(page.title)}</strong>
          <span>{html.escape(page.summary)}</span>
          <code>{page.output}</code>
        </a>
      </li>"""
            for page in pages
        )
        sections.append(
            f"""  <section class="doc-group" id="{group}">
    <h2>{html.escape(group)}</h2>
    <ul class="doc-grid">
{items}
    </ul>
  </section>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>项目文档索引 · 葡萄膜炎辅助诊断智能系统</title>
  <link rel="stylesheet" href="assets/docs.css">
</head>
<body>
<a class="doc-skip" href="#catalog">跳到文档目录</a>
<header class="doc-nav">
  <a class="doc-brand" href="2026-10-26-project-overview.html">葡萄膜炎项目文档</a>
  <nav aria-label="文档导航">
    <a href="2026-10-26-project-overview.html">项目总览</a>
    <a href="#catalog">全部文档</a>
  </nav>
</header>
<main id="catalog" class="doc-page doc-catalog">
  <div class="doc-kicker">
    <span>文档</span>
    <span>{len(PAGES)} 份</span>
  </div>
  <h1>项目文档索引</h1>
  <p class="doc-summary">训练、模型运行、系统设计、数据集和项目状态的离线入口。专题文档以 HTML 为最终源，目录级 README 保留为 Markdown 规范入口。</p>
  <div class="doc-catalog-head">
    <h2>文档目录</h2>
    <p>命名格式：<code>YYYY-MM-DD-kebab-case.html</code>；总索引固定为 <code>index.html</code>。</p>
  </div>
{chr(10).join(sections)}
</main>
<footer class="doc-footer">
  <span>葡萄膜炎辅助诊断智能系统 · {len(PAGES)} 份内容页</span>
  <span>非商用科研原型，内容不构成医疗建议</span>
</footer>
</body>
</html>
"""


def check_links() -> None:
    catalog_text = read_text(DOCS / "index.html")
    for page in PAGES:
        path = DOCS / page.output
        text = read_text(path)
        if "\ufffd" in text:
            raise RuntimeError(f"Encoding damage in {page.output}")
        for tag in ("html", "body", "main"):
            opening = re.findall(rf"<{tag}\b", text, flags=re.IGNORECASE)
            if len(opening) != 1:
                raise RuntimeError(f"Unexpected <{tag}> count in {page.output}: {len(opening)}")
        if len(re.findall(r"<!doctype\b", text, flags=re.IGNORECASE)) != 1:
            raise RuntimeError(f"Unexpected doctype count in {page.output}")
        for href in re.findall(r'\bhref="([^"]+)"', text):
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or href.startswith(("#", "mailto:", "${")):
                continue
            if not (path.parent / parts.path).resolve().exists():
                raise RuntimeError(f"Broken local link in {page.output}: {href}")
        if page.output not in catalog_text:
            raise RuntimeError(f"Catalog missing {page.output}")


def check_layout() -> None:
    training = [
        path for path in (ROOT / "model-training").rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".toml", ".txt"}
    ]
    runtime = [
        path for path in (ROOT / "model-runtime").rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".toml"}
    ]
    if not training or not runtime:
        raise RuntimeError("Training or runtime implementation directory is empty")
    extra = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.md")
        if "node_modules" not in path.parts
        and ".venv" not in path.as_posix()
        and ".uv-cache-local" not in path.parts
        and not path.relative_to(ROOT).as_posix().startswith(
            "model-training/datasets/extracted/"
        )
        and path.name.lower() not in {"readme.md", "license.md"}
        and path.relative_to(ROOT) not in {page.source for page in PAGES}
    }
    if extra:
        raise RuntimeError("Non-README Markdown remains: " + ", ".join(sorted(extra)))
    for parent, names in (
        (ROOT / "model-training", ("models", "datasets", "assets", "environment", "code", "scripts")),
        (ROOT / "model-runtime", ("app", "code", "scripts", "assets")),
    ):
        for name in names:
            if not (parent / name).exists():
                raise RuntimeError(f"Missing {parent.name}/{name}")
    print(f"Layout check: {len(training)} training files, {len(runtime)} runtime files")
    print(f"Markdown entry points: {len(README_SOURCES)}")


def build() -> None:
    missing = [
        page.source.as_posix()
        for page in PAGES
        if not (ROOT / page.source).is_file() and captured_html_source(page) is None
    ]
    if missing:
        raise RuntimeError("Missing documentation sources: " + ", ".join(missing))
    for index, page in enumerate(PAGES):
        output = DOCS / page.output
        output.write_text(render_page(page, index), encoding="utf-8")
        if cached_source(page) is None:
            SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output, SOURCE_CACHE / page.output)
    content = catalog()
    (DOCS / "2026-10-26-document-catalog.html").write_text(content, encoding="utf-8")
    (DOCS / "index.html").write_text(content, encoding="utf-8")
    expected = {page.output for page in PAGES} | {"2026-10-26-document-catalog.html", "index.html"}
    stale = {path.name for path in DOCS.glob("*.html")} - expected
    for name in sorted(stale):
        (DOCS / name).unlink()
    check_links()
    check_layout()
    print(f"Built {len(PAGES)} pages plus index.html in {DOCS}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_links()
        check_layout()
    else:
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
