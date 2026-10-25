#!/usr/bin/env python3
"""Build the offline documentation site in docs/ from project-owned files."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
SOURCE_CACHE = ROOT / "scripts/docs/.html-source"
ICON = (
    Path(os.environ["CODEX_HOME"]) / "visualizations"
    if os.environ.get("CODEX_HOME")
    else Path.home() / ".codex" / "visualizations"
)


@dataclass(frozen=True)
class Page:
    source: Path
    output: str
    title: str
    category: str
    summary: str
    date: str
    kind: str = "markdown"


PAGES = (
    Page(Path("README.md"), "2026-10-25-project-overview.html", "项目总览", "项目", "系统范围、目录、当前状态与启动方式", "2026-10-25"),
    Page(Path("PROJECT_LAYOUT.md"), "2026-10-25-project-layout.html", "项目目录索引", "项目", "目录作用、占用、清理边界与验证状态", "2026-10-25"),
    Page(Path("model-training/README.md"), "2026-10-25-model-training-management.html", "模型训练管理", "训练", "训练代码、脚本、数据和产物的统一入口", "2026-10-25"),
    Page(Path("model-training/STATUS.md"), "2026-10-25-model-training-status.html", "训练状态", "训练", "当前模型、数据、checkpoint、预算和训练前后检查", "2026-10-25"),
    Page(Path("artifacts/README.md"), "2026-10-25-artifacts-index.html", "训练产物与本地快照", "训练", "Qwen3.5-4B 的运行快照、评估和权重保存约定", "2026-10-25"),
    Page(Path("outputs/README.md"), "2026-10-25-outputs-guide.html", "运行输出说明", "项目", "临时输出与长期训练证据的归档边界", "2026-10-25"),
    Page(Path("docs/agent-execution-chain-20261023.md"), "2026-10-23-agent-execution-chain.html", "智能体执行链路规划", "系统设计", "病例接入、影像感知、检索、决策和安全复核链路", "2026-10-23"),
    Page(Path("model-training/docs/training-plan-modal-l40s-20261023.md"), "2026-10-23-training-plan-modal-l40s.html", "Modal L40S 训练规划", "训练", "Qwen 主模型、补充决策模型和 Modal 资源阶段", "2026-10-23"),
    Page(Path("model-training/docs/training-cost-ledger-modal-20261025.md"), "2026-10-25-training-cost-ledger-modal.html", "Modal 训练消耗清单", "训练", "实际账单、资源消耗、训练结果和预算依据", "2026-10-25"),
    Page(Path("model-training/docs/training-budget-plan-modal-l40s-44usd-20261025.md"), "2026-10-25-training-budget-plan-modal-l40s.html", "Modal L40S 预算排期", "训练", "本月与下月预算、训练顺序和数据集安排", "2026-10-25"),
    Page(Path("datasets/extracted/README.md"), "2026-10-25-dataset-index.html", "数据集目录索引", "数据", "已解压数据集的规模、标签、目录和清理后的结构", "2026-10-25"),
    Page(Path("datasets/extracted/manifests/archive-cleanup.md"), "2026-10-25-redundant-archives.html", "压缩包清理记录", "数据", "已删除归档的校验结果、容量和后续暂存规则", "2026-10-25"),
    Page(Path("model-training/code/training/DATASET_TRAINING_MAP.md"), "2026-10-25-dataset-training-map.html", "数据集训练映射", "训练", "影像、检索和决策任务的样本构造与验收指标", "2026-10-25"),
    Page(Path("model-training/code/training/modal_training_storage.md"), "2026-10-25-modal-training-storage.html", "Modal 训练存储约定", "基础设施", "Volume 挂载、产物目录、checkpoint 与恢复方式", "2026-10-25"),
    Page(Path("model-training/code/training/modal_uploaded_artifacts.md"), "2026-10-25-modal-uploaded-artifacts.html", "Modal 已上传产物", "基础设施", "训练数据卷、模型卷和训练产物卷的实际内容", "2026-10-25"),
    Page(Path("docs/cn-eye-datasets-20261023.html"), "2026-10-23-cn-eye-datasets.html", "国内眼科数据集核验", "数据", "国内开源免费眼科数据集的许可、规模和可用性", "2026-10-23", "html"),
    Page(Path("docs/intl-eye-datasets-20261023.html"), "2026-10-23-intl-eye-datasets.html", "国外眼科数据集核验", "数据", "国外开源免费眼科数据集的许可、规模和申请方式", "2026-10-23", "html"),
    Page(Path("docs/manual-download-links-20261023.html"), "2026-10-23-manual-download-links.html", "手动下载清单", "数据", "数据集条目页、下载入口与人工下载状态", "2026-10-23", "html"),
    Page(Path("docs/recommended-datasets-20261023.html"), "2026-10-23-recommended-datasets.html", "推荐数据集清单", "数据", "P0/P1 数据集、体量、许可和获取渠道", "2026-10-23", "html"),
    Page(Path("docs/model-24gb-20261023.html"), "2026-10-23-model-24gb.html", "24GB 显卡模型选型", "模型", "24GB 显卡上的候选模型、资源与部署选型", "2026-10-23", "html"),
    Page(Path("docs/model-trio-24gb-20261023.html"), "2026-10-23-model-trio-24gb.html", "24GB 核心模型方案", "模型", "Qwen、补充决策模型与 BGE-M3 的三模型方案", "2026-10-23", "html"),
    Page(
        Path("artifacts/reference/24GB_GPU_Cloud_Price_List_2026-10-25.html"),
        "2026-10-25-gpu-cloud-price-list.html",
        "24GB 显存 GPU 云价格清单",
        "参考",
        "历史云 GPU 报价快照与预算筛选参考",
        "2026-10-25",
        "html",
    ),
)

HTML_RENAMES = {
    "cn-eye-datasets-20261023.html": "2026-10-23-cn-eye-datasets.html",
    "intl-eye-datasets-20261023.html": "2026-10-23-intl-eye-datasets.html",
    "manual-download-links-20261023.html": "2026-10-23-manual-download-links.html",
    "recommended-datasets-20261023.html": "2026-10-23-recommended-datasets.html",
    "model-24gb-20261023.html": "2026-10-23-model-24gb.html",
    "model-trio-24gb-20261023.html": "2026-10-23-model-trio-24gb.html",
}


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def capture_original_html_sources() -> None:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    legacy_cache = DOCS / ".html-source"
    if legacy_cache.exists():
        for legacy_file in legacy_cache.iterdir():
            destination = SOURCE_CACHE / legacy_file.name
            if not destination.exists():
                shutil.move(str(legacy_file), str(destination))
        legacy_cache.rmdir()
    for old_name, new_name in HTML_RENAMES.items():
        destination = SOURCE_CACHE / new_name
        if destination.exists():
            continue
        current = DOCS / new_name
        legacy = DOCS / old_name
        if current.exists():
            shutil.copy2(current, destination)
        elif legacy.exists():
            shutil.copy2(legacy, destination)
        else:
            raise FileNotFoundError(f"HTML source not found: {legacy}")


def copy_html_sources() -> None:
    for page in PAGES:
        if page.kind != "html":
            continue
        target = DOCS / page.output
        origin = page.source
        if origin.parent == Path("docs"):
            origin = SOURCE_CACHE / page.output
        if not origin.exists():
            raise FileNotFoundError(f"HTML source not found: {origin}")
        shutil.copy2(origin, target)


def normalize_navigation_href(href: str) -> str:
    if href in HTML_RENAMES:
        return HTML_RENAMES[href]
    return href


def add_navigation_and_repair_links(path: Path, current_page: Page, index: int) -> None:
    text = path.read_text(encoding="utf-8")
    missing_suffix = "dataset-plan-20261023/SIZE-ESTIMATE.md"
    if missing_suffix in text:
        text = re.sub(
            r'<a href="[^"]*dataset-plan-20261023/SIZE-ESTIMATE\.md">'
            r"体量估算 SIZE-ESTIMATE\.md</a>",
            "体量估算（原 SIZE-ESTIMATE.md 未随项目保留）",
            text,
        )

    def replace_href(match: re.Match[str]) -> str:
        prefix, href, suffix = match.groups()
        href = normalize_navigation_href(href)
        if href == current_page.output:
            href = "#"
        return f'{prefix}{html.escape(href, quote=True)}{suffix}'

    text = re.sub(
        r'(<a\b[^>]*\bhref=")([^"]+)("[^>]*>)',
        replace_href,
        text,
        flags=re.IGNORECASE,
    )
    def fix_link_attributes(match: re.Match[str]) -> str:
        tag = match.group(0)
        href_match = re.search(r'\bhref="([^"]*)"', tag, flags=re.IGNORECASE)
        if not href_match:
            return tag
        href_value = href_match.group(1)
        targets_external = href_value.startswith(("http://", "https://"))
        had_target = bool(re.search(r"\starget=", tag, flags=re.IGNORECASE))
        tag = re.sub(r'\s+target="[^"]*"', "", tag, flags=re.IGNORECASE)
        tag = re.sub(
            r'\s+rel="[^"]*"',
            "",
            tag,
            flags=re.IGNORECASE,
        )
        if targets_external and had_target:
            tag = tag[:-1] + ' target="_blank" rel="noopener noreferrer">'
        return tag

    text = re.sub(
        r"<a\b[^>]*>",
        fix_link_attributes,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<main\b(?![^>]*\bid=\"doc-content\")([^>]*)>(.*?)</main>",
        r"<div\1>\2</div>",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"</main>(\s*</body>)",
        r"</div>\1",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    previous = PAGES[index - 1] if index > 0 else PAGES[-1]
    following = PAGES[index + 1] if index + 1 < len(PAGES) else PAGES[0]
    nav = f"""
<a class="doc-skip" href="#doc-content">跳到正文</a>
<header class="doc-nav">
  <a class="doc-brand" href="2026-10-25-project-overview.html">葡萄膜炎项目文档</a>
  <nav aria-label="文档导航">
    <a href="2026-10-25-document-catalog.html">文档索引</a>
    <a href="2026-10-25-document-catalog.html">文档索引</a>
    <a href="{previous.output}">上一份</a>
    <a href="{following.output}">下一份</a>
  </nav>
</header>
<main id="doc-content">
"""
    footer = f"""
</main>
<footer class="doc-footer">
  <span>{html.escape(current_page.title)} · {current_page.date}</span>
  <span><a href="2026-10-25-document-catalog.html">返回文档索引</a></span>
</footer>
"""
    body_match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if not body_match:
        raise ValueError(f"Missing <body> in {path}")
    text = text[: body_match.end()] + nav + text[body_match.end() :]
    text = text.replace("</body>", footer + "\n</body>", 1)

    head_end = re.search(r"</head>", text, flags=re.IGNORECASE)
    if not head_end:
        raise ValueError(f"Missing </head> in {path}")
    assets = (
        '<link rel="stylesheet" href="assets/docs.css">\n'
        '<link rel="stylesheet" href="assets/document-shell.css">\n'
        '</head>'
    )
    text = text[: head_end.start()] + assets + text[head_end.end() :]
    path.write_text(text, encoding="utf-8")


def strip_leading_heading(markdown_text: str) -> str:
    return re.sub(r"\A\s*# [^\n]+\n+", "", markdown_text, count=1)


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.lower()).strip("-")
    return slug or "section"


def add_heading_ids(rendered: str) -> str:
    ids: dict[str, int] = {}
    heading_re = re.compile(r"<h([2-6])>(.*?)</h\1>", flags=re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        level, inner = match.groups()
        base = slugify(inner)
        count = ids.get(base, 0) + 1
        ids[base] = count
        ident = base if count == 1 else f"{base}-{count}"
        return f'<h{level} id="{ident}">{inner}</h{level}>'

    return heading_re.sub(repl, rendered)


def repair_markdown_links(markdown_text: str, page: Page) -> str:
    mapping = {page.output: page.output for page in PAGES}
    mapping["docs/index.html"] = "index.html"
    mapping["index.html"] = page.output if page.output != "index.html" else "index.html"

    def replace(match: re.Match[str]) -> str:
        label, target = match.groups()
        destination = mapping.get(target, target)
        return f"[{label}]({destination})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace, markdown_text)


def build_markdown_page(page: Page, index: int) -> str:
    source = ROOT / page.source
    markdown_text = repair_markdown_links(source.read_text(encoding="utf-8-sig"), page)
    parser = MarkdownIt(
        "commonmark",
        {"html": False, "typographer": False, "linkify": False},
    )
    parser.enable("table")
    parser.enable("table")
    rendered = add_heading_ids(parser.render(strip_leading_heading(markdown_text)))
    previous = PAGES[index - 1] if index > 0 else PAGES[-1]
    following = PAGES[index + 1] if index + 1 < len(PAGES) else PAGES[0]
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
  <a class="doc-brand" href="2026-10-25-project-overview.html">葡萄膜炎项目文档</a>
  <nav aria-label="文档导航">
    <a href="2026-10-25-document-catalog.html">文档索引</a>
    <a href="2026-10-25-document-catalog.html">文档索引</a>
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
  <p class="doc-source">Markdown 源文件：<code>{html.escape(rel(ROOT, source))}</code></p>
  <article class="markdown-body">
{rendered}
  </article>
</main>
<footer class="doc-footer">
  <span>{html.escape(page.title)} · {page.date}</span>
  <span><a href="2026-10-25-document-catalog.html">返回文档索引</a></span>
</footer>
</body>
</html>
"""


def build_catalog() -> str:
    groups = ("项目", "系统设计", "训练", "数据", "模型", "基础设施", "参考")
    grouped = {group: [page for page in PAGES if page.category == group] for group in groups}
    cards = []
    for group in groups:
        pages = grouped[group]
        if not pages:
            continue
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
        cards.append(
            f"""  <section class="doc-group" id="{slugify(group)}">
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
  <a class="doc-brand" href="2026-10-25-project-overview.html">葡萄膜炎项目文档</a>
  <nav aria-label="文档导航">
    <a href="2026-10-25-project-overview.html">项目总览</a>
    <a href="#catalog">全部文档</a>
  </nav>
</header>
<main id="catalog" class="doc-page doc-catalog">
  <div class="doc-kicker">
    <span>文档</span>
    <span>{len(PAGES)} 份</span>
  </div>
  <h1>项目文档索引</h1>
  <p class="doc-summary">项目设计、数据集、Modal 训练记录与模型选型的统一入口。全部页面可离线打开，Markdown 源文件保留在原位置。</p>
  <div class="doc-catalog-head">
    <h2>文档目录</h2>
    <p>命名格式：<code>YYYY-MM-DD-kebab-case.html</code>；文档总索引使用固定的 <code>index.html</code>。</p>
  </div>
{chr(10).join(cards)}
</main>
<footer class="doc-footer">
  <span>葡萄膜炎辅助诊断智能系统 · 13 份 Markdown 转换文档</span>
  <span>非商用科研原型，内容不构成医疗建议</span>
</footer>
</body>
</html>
"""


def validate_outputs() -> None:
    expected = {page.output for page in PAGES} | {
        "index.html",
        "2026-10-25-document-catalog.html",
    }
    found = {path.name for path in DOCS.glob("*.html")}
    missing = expected - found
    unexpected = found - expected
    if missing:
        raise RuntimeError(f"Missing generated pages: {sorted(missing)}")
    if unexpected:
        raise RuntimeError(f"Unexpected HTML pages: {sorted(unexpected)}")

    if (DOCS / ".html-source").exists():
        raise RuntimeError("HTML source cache must live under scripts/docs, not docs")

    for source_page in PAGES:
        path = DOCS / source_page.output
        text = path.read_text(encoding="utf-8")
        if "\ufffd" in text:
            raise RuntimeError(f"Encoding damage in {path.name}")
        for href in re.findall(r'\bhref="([^"]+)"', text):
            parts = urlsplit(href)
            if (
                parts.scheme
                or parts.netloc
                or href.startswith(("#", "mailto:", "${"))
            ):
                continue
            target = (path.parent / parts.path).resolve()
            if not target.exists():
                raise RuntimeError(f"Broken local link in {path.name}: {href}")

    catalog = (DOCS / "index.html").read_text(encoding="utf-8")
    for page in PAGES:
        if f'href="{page.output}"' not in catalog:
            raise RuntimeError(f"Catalog is missing {page.output}")

    markdown_pages = [page for page in PAGES if page.kind == "markdown"]
    expected_sources = {
        "README.md",
        "PROJECT_LAYOUT.md",
        "model-training/README.md",
        "model-training/STATUS.md",
        "artifacts/README.md",
        "outputs/README.md",
        "docs/agent-execution-chain-20261023.md",
        "model-training/docs/training-plan-modal-l40s-20261023.md",
        "model-training/docs/training-cost-ledger-modal-20261025.md",
        "model-training/docs/training-budget-plan-modal-l40s-44usd-20261025.md",
        "datasets/extracted/manifests/archive-cleanup.md",
        "datasets/extracted/README.md",
        "model-training/code/training/DATASET_TRAINING_MAP.md",
        "model-training/code/training/modal_training_storage.md",
        "model-training/code/training/modal_uploaded_artifacts.md",
    }
    if {page.source.as_posix() for page in markdown_pages} != expected_sources:
        raise RuntimeError("The Markdown document coverage list is out of date")

    for page in markdown_pages:
        source = (ROOT / page.source).read_text(encoding="utf-8-sig")
        build = (DOCS / page.output).read_text(encoding="utf-8")
        for heading in re.findall(r"^#{2,3} (.+)$", source, flags=re.MULTILINE):
            heading = re.sub(r"[`*_]", "", heading).strip()
            candidates = {
                heading,
                html.escape(heading),
                json.dumps(heading, ensure_ascii=False)[1:-1],
            }
            if not any(candidate in build for candidate in candidates):
                raise RuntimeError(f"Markdown heading missing in {page.output}: {heading}")

    print(f"Built {len(PAGES)} content pages plus index.html in {DOCS}")
    print(f"Converted {len(markdown_pages)} Markdown sources and normalized 7 existing HTML documents.")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    capture_original_html_sources()
    for old_name, new_name in HTML_RENAMES.items():
        old = DOCS / old_name
        new = DOCS / new_name
        if old.exists() and old != new:
            old.unlink()
    copy_html_sources()
    for index, page in enumerate(PAGES):
        output = DOCS / page.output
        if page.kind == "markdown":
            output.write_text(build_markdown_page(page, index), encoding="utf-8")
        else:
            add_navigation_and_repair_links(output, page, index)
    (DOCS / "2026-10-25-document-catalog.html").write_text(build_catalog(), encoding="utf-8")
    shutil.copy2(DOCS / "2026-10-25-document-catalog.html", DOCS / "index.html")
    validate_outputs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
