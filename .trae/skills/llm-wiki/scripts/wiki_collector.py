# [变更记录]
# 2026-05-09 | AI | 新建：llm-wiki 素材采集脚本（自包含，不依赖外部 skill 路径）

"""
Wiki 素材采集器
=====================================
职责：
    将粘贴文本或本地文件（含 HTML 自动转换）采集为结构化 Markdown 文件，
    以「批次」为单位组织目录结构并生成索引。

模块组成：
    1. 数据模型   — MaterialItem + frontmatter 渲染 + 平台标签
    2. 批次管理   — BatchWriter 目录/文件/索引管理
    3. HTML 转换  — html_to_markdown / extract_main_content
    4. 采集主类   — WikiCollector（文本/文件统一入口）
    5. CLI 入口   — argparse 命令行参数解析

依赖：
    - pyyaml
    - beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup, NavigableString, Tag


# ============================================================================
# 模块 1：数据模型
# ============================================================================

# 平台中文名映射表
PLATFORM_LABELS: dict[str, str] = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "wechat_mp": "微信公众号",
    "webpage": "网页",
    "local": "本地输入",
}

# 素材文件名数字编号正则：匹配 "001.md"、"099.md" 等
_FILE_INDEX_PATTERN: re.Pattern[str] = re.compile(r"^(\d{3})\.md$")


@dataclass
class MaterialItem:
    """单条素材的完整数据模型。

    Attributes:
        source_url:      素材原始链接或来源说明
        platform:        来源平台标识
        title:           素材标题
        author:          作者 / UP主 / 公众号名
        publish_date:    发布日期字符串（如 "2026-04-20"）
        content_type:    内容类型（article / webpage）
        content:         Markdown 格式的正文内容
        success:         本次采集是否成功
        error_message:   失败原因描述
    """

    source_url: str
    platform: str
    title: str
    author: str = ""
    publish_date: str = ""
    content_type: str = "article"
    content: str = ""
    success: bool = True
    error_message: str = ""


def _render_material_markdown(item: MaterialItem) -> str:
    """将单条素材渲染为带 YAML frontmatter 的 Markdown 文本。

    Args:
        item: 素材数据实例

    Returns:
        完整的 Markdown 字符串
    """
    collected_at: str = datetime.now().isoformat(timespec="seconds")
    frontmatter: dict[str, object] = {
        "source_url": item.source_url,
        "platform": item.platform,
        "title": item.title,
        "author": item.author,
        "publish_date": item.publish_date,
        "collected_at": collected_at,
        "content_type": item.content_type,
    }

    yaml_block: str = yaml.dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()

    platform_label: str = PLATFORM_LABELS.get(item.platform, item.platform)

    lines: list[str] = [
        "---",
        yaml_block,
        "---",
        "",
        f"# {item.title}",
        "",
        f"> 来源：{platform_label} | 作者：{item.author} | 发布日期：{item.publish_date}",
        f"> 链接：{item.source_url}",
        "",
        item.content,
        "",
    ]
    return "\n".join(lines)


# ============================================================================
# 模块 2：批次管理
# ============================================================================

class BatchWriter:
    """素材批次文件夹管理器。

    典型用法::

        writer = BatchWriter(output_dir="wiki/sources", batch_name="my_batch")
        writer.create_batch_dir()
        writer.write_material(item)
        writer.write_index([item1, item2])

    文件夹结构::

        wiki/sources/
        └── my_batch/
            ├── 001.md
            ├── 002.md
            └── _index.md

    Args:
        output_dir: 批次根目录（相对或绝对路径均可）
        batch_name: 自定义批次名，为 None 时自动生成 batch_{YYYYMMDD}_{HHMMSS}
    """

    def __init__(
        self,
        output_dir: str = "wiki/sources",
        batch_name: str | None = None,
    ) -> None:
        self._output_dir: Path = Path(output_dir)

        if batch_name is not None:
            self._batch_name: str = batch_name
        else:
            self._batch_name = datetime.now().strftime("batch_%Y%m%d_%H%M%S")

    @property
    def batch_dir(self) -> Path:
        """批次文件夹路径。"""
        return self._output_dir / self._batch_name

    @property
    def batch_name(self) -> str:
        """当前批次名称。"""
        return self._batch_name

    def create_batch_dir(self) -> Path:
        """创建批次文件夹（含所有中间父目录）。

        Returns:
            批次文件夹的绝对路径
        """
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        return self.batch_dir.resolve()

    def get_next_index(self) -> int:
        """扫描批次文件夹中已有的 NNN.md 文件，返回下一个可用编号。

        Returns:
            下一个可用的整数编号（从 1 开始）
        """
        if not self.batch_dir.exists():
            return 1

        max_index: int = 0
        for file_path in self.batch_dir.iterdir():
            if not file_path.is_file():
                continue
            match: re.Match[str] | None = _FILE_INDEX_PATTERN.match(file_path.name)
            if match is not None:
                file_index: int = int(match.group(1))
                if file_index > max_index:
                    max_index = file_index

        return max_index + 1

    def write_material(self, item: MaterialItem) -> Path:
        """将单条素材写入 Markdown 文件。

        Args:
            item: 素材数据实例

        Returns:
            写入文件的绝对路径
        """
        self.create_batch_dir()

        next_idx: int = self.get_next_index()
        file_name: str = f"{next_idx:03d}.md"
        file_path: Path = self.batch_dir / file_name

        markdown_content: str = _render_material_markdown(item)
        file_path.write_text(markdown_content, encoding="utf-8")

        return file_path.resolve()

    def write_index(self, items: list[MaterialItem]) -> Path:
        """生成批次索引文件 _index.md。

        Args:
            items: 本批次全部素材列表

        Returns:
            索引文件的绝对路径
        """
        self.create_batch_dir()

        collected_at: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total: int = len(items)
        success_count: int = sum(1 for it in items if it.success)
        fail_count: int = total - success_count

        # 平台分布统计
        platform_stats: dict[str, int] = {}
        for it in items:
            label: str = PLATFORM_LABELS.get(it.platform, it.platform)
            platform_stats[label] = platform_stats.get(label, 0) + 1

        distribution: str = "、".join(
            f"{name} {cnt} 条" for name, cnt in platform_stats.items()
        )

        # 素材清单表格行
        table_rows: list[str] = []
        for idx, it in enumerate(items, start=1):
            file_name: str = f"{idx:03d}.md"
            platform_cn: str = PLATFORM_LABELS.get(it.platform, it.platform)
            status: str = "成功" if it.success else f"失败（{it.error_message}）"
            safe_title: str = it.title.replace("|", "｜")
            table_rows.append(
                f"| {idx} | {file_name} | {platform_cn} | {safe_title} | {status} | {it.source_url} |"
            )

        index_lines: list[str] = [
            f"# 批次索引 — {self._batch_name}",
            "",
            f"- **采集时间**：{collected_at}",
            f"- **素材数量**：{total}",
            f"- **成功 / 失败**：{success_count} / {fail_count}",
            f"- **平台分布**：{distribution}",
            f"- **处理状态**：未处理",
            "",
            "## 素材清单",
            "",
            "| 序号 | 文件 | 平台 | 标题 | 状态 | 来源链接 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        index_lines.extend(table_rows)
        index_lines.append("")

        index_path: Path = self.batch_dir / "_index.md"
        index_path.write_text("\n".join(index_lines), encoding="utf-8")

        return index_path.resolve()


# ============================================================================
# 模块 3：HTML → Markdown 转换
# ============================================================================

# 需要移除的 HTML 标签（脚本、导航、表单等）
_REMOVED_TAGS: frozenset[str] = frozenset({
    "script", "style", "noscript", "nav", "footer", "header", "aside",
    "iframe", "svg", "form", "button", "input", "select", "textarea",
})

# 噪音元素的 class/id 关键词模式（导航、面包屑、分享、侧边栏等）
_NOISE_CLASS_PATTERNS: tuple[str, ...] = (
    "breadcrumb", "nav-", "navbar", "navigation", "menu", "sidebar",
    "share", "social", "comment", "related", "recommend", "pagination",
    "cookie", "banner", "popup", "modal", "overlay", "toolbar",
    "widget", "footer-", "header-", "top-bar", "site-footer",
    "site-header", "post-tags", "tag-list", "author-info",
    "categor", "toc-", "w-dyn-", "w-nav", "back-to",
)

# 正文容器的常见 class 名模式
_CONTENT_CONTAINER_PATTERNS: tuple[str, ...] = (
    "blog-post-content", "post-content", "entry-content",
    "article-content", "content-body", "rich-text",
    "w-richtext", "post-body", "article-body",
)


def _escape_markdown(text: str) -> str:
    """转义 Markdown 表格竖线，避免破坏表格格式。"""
    return text.replace("|", "\\|")


def _collect_children(node: Tag, base_url: str, indent_level: int) -> str:
    """收集所有子节点的转换结果并拼接。"""
    parts: list[str] = []
    for child in node.children:
        parts.append(html_to_markdown(child, base_url, indent_level))
    return "".join(parts)


def _collect_list_items(
    node: Tag, base_url: str, indent_level: int, ordered: bool
) -> list[str]:
    """收集列表项并添加 Markdown 列表前缀。"""
    items: list[str] = []
    idx = 1
    indent = "  " * indent_level

    for child in node.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "li":
            inner = _collect_children(child, base_url, indent_level + 1).strip()
            if ordered:
                items.append(f"{indent}{idx}. {inner}\n")
                idx += 1
            else:
                items.append(f"{indent}- {inner}\n")
        elif child.name in ("ul", "ol"):
            nested = _collect_list_items(
                child, base_url, indent_level + 1, child.name == "ol"
            )
            items.extend(nested)

    return items


def _convert_table(table: Tag, base_url: str) -> str:
    """将 HTML 表格转换为 Markdown 表格。"""
    rows: list[list[str]] = []

    for tr in table.find_all("tr"):
        cells: list[str] = []
        for cell in tr.find_all(["td", "th"]):
            text = _collect_children(cell, base_url, 0).strip().replace("\n", " ")
            cells.append(text)
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    lines: list[str] = []
    for i, row in enumerate(rows):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if i == 0:
            sep = "| " + " | ".join(["---"] * max_cols) + " |"
            lines.append(sep)

    return "\n\n" + "\n".join(lines) + "\n\n"


def html_to_markdown(
    node: Tag | NavigableString,
    base_url: str = "",
    indent_level: int = 0,
) -> str:
    """递归将 BeautifulSoup 节点树转换为 Markdown 文本。

    支持的标签映射：
        h1-h6 → # 到 ######
        p → 前后双换行
        a → [text](href)
        img → ![alt](src)
        strong/b → **text**
        em/i → *text*
        ul/li → - item（支持嵌套缩进）
        ol/li → 1. item
        blockquote → > text
        code → `code`
        pre → ```\\ncode\\n```
        br → 换行
        table → Markdown 表格
        已移除标签 → 跳过

    Args:
        node: BeautifulSoup 的 Tag 或 NavigableString 节点
        base_url: 基准 URL，用于将相对链接转为绝对链接
        indent_level: 当前缩进层级（用于嵌套列表）

    Returns:
        转换后的 Markdown 文本
    """
    if isinstance(node, NavigableString):
        text = str(node)
        if node.parent and node.parent.name in ("code", "pre"):
            return text
        text = re.sub(r"\s+", " ", text)
        return _escape_markdown(text)

    if not isinstance(node, Tag):
        return ""

    tag_name = node.name.lower() if node.name else ""

    if tag_name in _REMOVED_TAGS:
        return ""

    indent = "  " * indent_level

    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag_name[1])
        prefix = "#" * level
        inner = _collect_children(node, base_url, 0).strip()
        return f"\n\n{prefix} {inner}\n\n"

    if tag_name == "p":
        inner = _collect_children(node, base_url, 0).strip()
        if not inner:
            return ""
        return f"\n\n{inner}\n\n"

    if tag_name == "a":
        href = node.get("href", "")
        if href and base_url:
            href = urljoin(base_url, href)
        inner = _collect_children(node, base_url, 0).strip()
        if not inner:
            return ""
        if href:
            return f"[{inner}]({href})"
        return inner

    if tag_name == "img":
        alt = node.get("alt", "") or ""
        src = node.get("src", "") or ""
        if not src:
            return ""
        if base_url:
            src = urljoin(base_url, src)
        return f"![{alt}]({src})"

    if tag_name in ("strong", "b"):
        inner = _collect_children(node, base_url, 0).strip()
        if not inner:
            return ""
        return f"**{inner}**"

    if tag_name in ("em", "i"):
        inner = _collect_children(node, base_url, 0).strip()
        if not inner:
            return ""
        return f"*{inner}*"

    if tag_name == "blockquote":
        inner = _collect_children(node, base_url, 0).strip()
        lines = inner.split("\n")
        quoted = "\n".join(f"> {line}" for line in lines if line.strip())
        return f"\n\n{quoted}\n\n"

    if tag_name == "pre":
        code_tag = node.find("code")
        if code_tag:
            lang = ""
            classes = code_tag.get("class", [])
            if isinstance(classes, list):
                for cls in classes:
                    if cls.startswith("language-") or cls.startswith("lang-"):
                        lang = cls.split("-", 1)[1]
                        break
            code_text = code_tag.get_text()
        else:
            code_text = node.get_text()
            lang = ""
        return f"\n\n```{lang}\n{code_text.strip()}\n```\n\n"

    if tag_name == "code":
        parent = node.parent
        if parent and parent.name == "pre":
            return node.get_text()
        inner = node.get_text()
        return f"`{inner}`"

    if tag_name == "br":
        return "\n"

    if tag_name == "hr":
        return "\n\n---\n\n"

    if tag_name == "ul":
        items = _collect_list_items(node, base_url, indent_level, ordered=False)
        return f"\n\n{''.join(items)}\n"

    if tag_name == "ol":
        items = _collect_list_items(node, base_url, indent_level, ordered=True)
        return f"\n\n{''.join(items)}\n"

    if tag_name == "li":
        return _collect_children(node, base_url, indent_level)

    if tag_name == "table":
        return _convert_table(node, base_url)

    return _collect_children(node, base_url, indent_level)


def extract_main_content(html: str, url: str = "") -> tuple[str, str]:
    """从 HTML 字符串中提取标题和正文 Markdown。

    提取规则：
        - 标题优先级：og:title → <title> → URL
        - 正文容器优先级：class 匹配 → <article> → <main> → <body>
        - 自动移除无关标签和噪音元素

    Args:
        html: HTML 字符串
        url: 页面 URL（用于生成绝对链接和兜底标题）

    Returns:
        (title, markdown_content) 元组
    """
    soup = BeautifulSoup(html, "html.parser")

    # 提取标题
    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text().strip()
    if not title:
        title = url

    # 移除无关标签
    for tag_name in _REMOVED_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 移除噪音元素（导航、面包屑、分享按钮等）
    noise_tags: list = []
    for tag in soup.find_all(True):
        classes = tag.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        tag_id = tag.get("id", "") or ""
        all_identifiers = " ".join(classes) + " " + tag_id
        all_identifiers_lower = all_identifiers.lower()
        for pattern in _NOISE_CLASS_PATTERNS:
            if pattern in all_identifiers_lower:
                noise_tags.append(tag)
                break
    for tag in noise_tags:
        if tag.parent is not None:
            tag.decompose()

    # 提取正文容器
    content_node = None
    for pattern in _CONTENT_CONTAINER_PATTERNS:
        found = soup.find(
            True,
            class_=lambda c: (
                c and pattern in " ".join(c) if isinstance(c, list)
                else pattern in (c or "")
            ),
        )
        if found:
            content_node = found
            break
    if not content_node:
        content_node = soup.find("article")
    if not content_node:
        content_node = soup.find("main")
    if not content_node:
        content_node = soup.find("body")
    if not content_node:
        content_node = soup

    markdown = html_to_markdown(content_node, base_url=url)

    # 清理多余空行
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return title, markdown


# ============================================================================
# 模块 4：WikiCollector 主类
# ============================================================================

class WikiCollector:
    """Wiki 素材采集主类，提供文本粘贴和文件导入的统一入口。

    Args:
        output_dir: 输出根目录，默认 "wiki/sources"
        batch_name: 自定义批次名，为 None 时自动生成时间戳名称
    """

    def __init__(
        self,
        output_dir: str = "wiki/sources",
        batch_name: str | None = None,
    ) -> None:
        self._writer = BatchWriter(output_dir=output_dir, batch_name=batch_name)
        self._items: list[MaterialItem] = []

    @property
    def batch_dir(self) -> Path:
        """当前批次文件夹路径。"""
        return self._writer.batch_dir

    @property
    def file_count(self) -> int:
        """当前批次已写入的文件数量。"""
        return len(self._items)

    def collect_text(
        self,
        text: str,
        title: str = "",
        source: str = "本地输入",
    ) -> Path:
        """处理粘贴文本并写入素材文件。

        Args:
            text:   粘贴的原始文本内容
            title:  自定义标题，为空时使用时间戳
            source: 来源说明，默认 "本地输入"

        Returns:
            写入文件的绝对路径

        Raises:
            ValueError: 文本内容为空时抛出
        """
        stripped = text.strip()
        if not stripped:
            raise ValueError("文本内容不能为空")

        # 标题兜底：使用当前时间戳
        if not title:
            title = datetime.now().strftime("文本素材_%Y%m%d_%H%M%S")

        # 发布日期使用当天
        today = datetime.now().strftime("%Y-%m-%d")

        item = MaterialItem(
            source_url=source,
            platform="local",
            title=title,
            publish_date=today,
            content_type="article",
            content=stripped,
        )

        file_path = self._writer.write_material(item)
        self._items.append(item)
        return file_path

    def collect_file(
        self,
        file_path: str,
        title: str = "",
        source: str = "本地输入",
    ) -> Path:
        """处理本地文件并写入素材文件。

        自动检测 HTML 文件并转换为 Markdown，其他文件按纯文本处理。

        Args:
            file_path: 本地文件路径
            title:     自定义标题，为空时自动提取（HTML）或使用文件名
            source:    来源说明，默认 "本地输入"

        Returns:
            写入文件的绝对路径

        Raises:
            FileNotFoundError: 文件不存在时抛出
            ValueError:        文件内容为空时抛出
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        if not path.is_file():
            raise ValueError(f"路径不是文件：{file_path}")

        raw_content = path.read_text(encoding="utf-8")
        if not raw_content.strip():
            raise ValueError(f"文件内容为空：{file_path}")

        # 检测是否为 HTML 文件（按扩展名或内容特征判断）
        is_html = path.suffix.lower() in (".html", ".htm") or (
            raw_content.strip().startswith("<!DOCTYPE") or raw_content.strip().startswith("<html")
        )

        if is_html:
            extracted_title, content = extract_main_content(raw_content)
            content_type = "webpage"
        else:
            extracted_title = ""
            content = raw_content.strip()
            content_type = "article"

        # 标题优先级：自定义 > 自动提取 > 文件名
        final_title = title or extracted_title or path.stem

        today = datetime.now().strftime("%Y-%m-%d")

        item = MaterialItem(
            source_url=source,
            platform="local",
            title=final_title,
            publish_date=today,
            content_type=content_type,
            content=content,
        )

        written_path = self._writer.write_material(item)
        self._items.append(item)
        return written_path

    def write_index(self) -> Path:
        """生成当前批次的索引文件。

        Returns:
            索引文件的绝对路径
        """
        return self._writer.write_index(self._items)


# ============================================================================
# 模块 5：CLI 入口
# ============================================================================

def main() -> None:
    """命令行入口，解析参数并执行采集，输出统一 JSON 结果。"""
    # Windows 终端 UTF-8 兼容
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        description="Wiki 素材采集器 — 将文本或文件采集为结构化 Markdown"
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="粘贴文本内容",
    )
    parser.add_argument(
        "--file",
        type=str,
        action="append",
        default=None,
        help="本地文件路径（可多次指定）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="wiki/sources",
        help="输出目录（默认 wiki/sources）",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="",
        help="自定义标题",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="本地输入",
        help="来源说明（默认 本地输入）",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="自定义批次名称",
    )

    args = parser.parse_args()

    # 至少需要一种输入源
    if not args.text and not args.file:
        result = {"status": "error", "error": "至少需要指定 --text 或 --file"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    try:
        collector = WikiCollector(
            output_dir=args.output,
            batch_name=args.name,
        )

        # 处理文本输入
        if args.text:
            collector.collect_text(
                text=args.text,
                title=args.title,
                source=args.source,
            )

        # 处理文件输入（可多个）
        if args.file:
            for file_path in args.file:
                collector.collect_file(
                    file_path=file_path,
                    title=args.title,
                    source=args.source,
                )

        # 生成批次索引
        collector.write_index()

        result = {
            "status": "completed",
            "batch_dir": str(collector.batch_dir.resolve()),
            "file_count": collector.file_count,
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
