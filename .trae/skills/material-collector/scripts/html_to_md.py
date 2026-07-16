# [变更记录]
# 日期: 2026-04-28
# 修改人: AI
# 修改内容: 新增 HTML 转 Markdown 转换器

"""
HTML 转 Markdown 转换器

职责：
- 将 HTML DOM 节点递归转换为 Markdown 文本
- 从完整 HTML 中提取标题和正文内容
- 支持常见 HTML 标签到 Markdown 语法的映射

技术栈：
- 标准库 + beautifulsoup4
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag


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

# 正文容器的常见 class 名模式（优先于 <article>/<main> 使用）
_CONTENT_CONTAINER_PATTERNS: tuple[str, ...] = (
    "blog-post-content", "post-content", "entry-content",
    "article-content", "content-body", "rich-text",
    "w-richtext", "post-body", "article-body",
)


def _escape_markdown(text: str) -> str:
    """
    转义 Markdown 特殊字符中的星号（避免加粗/斜体误触发）

    参数说明：
    - text: 原始文本

    返回值：
    - 转义后的文本
    """
    return text.replace("|", "\\|")


def html_to_markdown(node: Tag | NavigableString, base_url: str = "", indent_level: int = 0) -> str:
    """
    递归将 BeautifulSoup 节点树转换为 Markdown 文本

    转换规则：
    - h1-h6 → # 到 ######
    - p → 前后双换行
    - a → [text](href)
    - img → ![alt](src)
    - strong/b → **text**
    - em/i → *text*
    - ul/li → - item（支持嵌套缩进）
    - ol/li → 1. item
    - blockquote → > text
    - code → `code`
    - pre → ```\\ncode\\n```
    - br → 换行
    - table → Markdown 表格（| 分隔）
    - 已移除标签（script/style/nav 等）→ 跳过

    参数说明：
    - node: BeautifulSoup 的 Tag 或 NavigableString 节点
    - base_url: 基准 URL，用于将相对链接转为绝对链接
    - indent_level: 当前缩进层级（用于嵌套列表）

    返回值：
    - 转换后的 Markdown 文本
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
        # 跳过无有效 src 的图片（避免输出 ![]() 等空标签）
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

    if tag_name in ("div", "section", "article", "main", "span", "figure", "figcaption", "details", "summary"):
        return _collect_children(node, base_url, indent_level)

    return _collect_children(node, base_url, indent_level)


def _collect_children(node: Tag, base_url: str, indent_level: int) -> str:
    """
    收集所有子节点的转换结果并拼接

    参数说明：
    - node: 父节点
    - base_url: 基准 URL
    - indent_level: 缩进层级

    返回值：
    - 拼接后的 Markdown 文本
    """
    parts: list[str] = []
    for child in node.children:
        parts.append(html_to_markdown(child, base_url, indent_level))
    return "".join(parts)


def _collect_list_items(node: Tag, base_url: str, indent_level: int, ordered: bool) -> list[str]:
    """
    收集列表项并添加 Markdown 列表前缀

    参数说明：
    - node: ul/ol 标签节点
    - base_url: 基准 URL
    - indent_level: 当前缩进层级
    - ordered: 是否为有序列表

    返回值：
    - 列表项 Markdown 文本列表
    """
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
            nested = _collect_list_items(child, base_url, indent_level + 1, child.name == "ol")
            items.extend(nested)

    return items


def _convert_table(table: Tag, base_url: str) -> str:
    """
    将 HTML 表格转换为 Markdown 表格

    参数说明：
    - table: table 标签节点
    - base_url: 基准 URL

    返回值：
    - Markdown 表格文本
    """
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


def extract_main_content(html: str, url: str = "") -> tuple[str, str]:
    """
    从 HTML 字符串中提取标题和正文 Markdown

    提取规则：
    - 标题优先级：og:title → <title> → URL
    - 正文容器优先级：<article> → <main> → <body>
    - 自动移除无关标签（script/style/nav/footer/header/aside）

    参数说明：
    - html: HTML 字符串
    - url: 页面 URL（用于生成绝对链接和兜底标题）

    返回值：
    - (title, markdown_content) 元组
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

    # 基于 class/id 移除噪音元素（导航、面包屑、分享按钮等）
    # 先收集需要移除的元素，再统一删除，避免遍历时修改树结构导致异常
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
    # 优先级：基于 class 的内容容器 → <article> → <main> → <body>
    content_node = None
    for pattern in _CONTENT_CONTAINER_PATTERNS:
        found = soup.find(True, class_=lambda c: c and pattern in " ".join(c) if isinstance(c, list) else pattern in (c or ""))
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

    # 清理多余空行（连续 3 个以上换行压缩为 2 个）
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return title, markdown
