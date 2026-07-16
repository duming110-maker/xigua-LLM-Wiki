"""
Markdown 输出与批次管理模块
=====================================
职责：
    将采集到的素材数据（视频转录稿、文章、网页等）渲染为结构化 Markdown 文件，
    并以「批次」为单位进行文件夹组织与索引生成。

技术栈：
    - Python 3.11+（dataclass、pathlib、标准库）
    - pyyaml（YAML frontmatter 序列化）

依赖范围：
    **仅依赖标准库 + pyyaml**，不导入任何宿主项目代码（app.* 等）。

变更记录：
    - 2026-04-28 | AI | 新增 Markdown 输出与批次管理模块
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# 平台中文名映射表
PLATFORM_LABELS: dict[str, str] = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "wechat_mp": "微信公众号",
    "webpage": "网页",
}

# 素材文件名的数字编号正则：匹配 "001.md"、"099.md" 等文件
_FILE_INDEX_PATTERN: re.Pattern[str] = re.compile(r"^(\d{3})\.md$")

# 内容类型标签映射
CONTENT_TYPE_LABELS: dict[str, str] = {
    "video_transcript": "视频转录",
    "article": "文章",
    "webpage": "网页快照",
}


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class MaterialItem:
    """单条素材的完整数据模型。

    Attributes:
        source_url:      素材原始链接
        platform:        来源平台标识（bilibili/youtube/wechat_mp/webpage）
        title:           素材标题
        author:          作者 / UP主 / 公众号名
        publish_date:    发布日期字符串（如 "2026-04-20"）
        content_type:    内容类型（video_transcript/article/webpage）
        content:         Markdown 格式的正文内容
        duration_seconds: 视频时长（秒），仅视频转录稿需要
        asr_model:       语音识别模型名称，仅视频转录稿需要
        success:         本次采集是否成功
        error_message:   失败原因描述（success=False 时填写）
    """

    source_url: str
    platform: str
    title: str
    author: str = ""
    publish_date: str = ""
    content_type: str = "article"
    content: str = ""
    duration_seconds: float | None = None
    asr_model: str = ""
    success: bool = True
    error_message: str = ""


# ---------------------------------------------------------------------------
# Markdown 渲染辅助函数
# ---------------------------------------------------------------------------

def _render_material_markdown(item: MaterialItem) -> str:
    """将单条素材渲染为带 YAML frontmatter 的 Markdown 文本。

    模板结构：
        1. YAML frontmatter（元数据）
        2. 一级标题
        3. 引用块（来源、作者、日期、链接）
        4. 正文内容

    Args:
        item: 素材数据实例

    Returns:
        完整的 Markdown 字符串
    """
    # ---- 构建 frontmatter 字典 ----
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

    # 视频转录稿额外字段
    if item.content_type == "video_transcript":
        frontmatter["duration_seconds"] = item.duration_seconds
        frontmatter["asr_model"] = item.asr_model

    # ---- 序列化为 YAML ----
    yaml_block: str = yaml.dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()

    # ---- 引用块中的平台中文名 ----
    platform_label: str = PLATFORM_LABELS.get(item.platform, item.platform)

    # ---- 组装完整 Markdown ----
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


def _render_index_markdown(
    items: list[MaterialItem],
    batch_name: str,
) -> str:
    """渲染批次索引文件 _index.md 的 Markdown 内容。

    Args:
        items:      本批次全部素材列表（含成功与失败）
        batch_name: 批次名称，用于标题展示

    Returns:
        _index.md 的完整 Markdown 字符串
    """
    collected_at: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total: int = len(items)
    success_count: int = sum(1 for it in items if it.success)
    fail_count: int = total - success_count

    # ---- 平台分布统计 ----
    platform_stats: dict[str, int] = {}
    for it in items:
        label: str = PLATFORM_LABELS.get(it.platform, it.platform)
        platform_stats[label] = platform_stats.get(label, 0) + 1

    distribution: str = "、".join(
        f"{name} {cnt} 条" for name, cnt in platform_stats.items()
    )

    # ---- 构建素材清单表格行 ----
    table_rows: list[str] = []
    for idx, it in enumerate(items, start=1):
        file_name: str = f"{idx:03d}.md"
        platform_cn: str = PLATFORM_LABELS.get(it.platform, it.platform)
        status: str = "成功" if it.success else f"失败（{it.error_message}）"
        # 标题中如果包含竖线则转义，避免破坏表格格式
        safe_title: str = it.title.replace("|", "｜")
        table_rows.append(
            f"| {idx} | {file_name} | {platform_cn} | {safe_title} | {status} | {it.source_url} |"
        )

    # ---- 组装完整 Markdown ----
    lines: list[str] = [
        f"# 批次索引 — {batch_name}",
        "",
        f"- **采集时间**：{collected_at}",
        f"- **素材数量**：{total}",
        f"- **成功 / 失败**：{success_count} / {fail_count}",
        f"- **平台分布**：{distribution}",
        "",
        "## 素材清单",
        "",
        "| 序号 | 文件 | 平台 | 标题 | 状态 | 来源链接 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(table_rows)
    lines.append("")  # 末尾换行

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 批次管理 & 写入器
# ---------------------------------------------------------------------------

class BatchWriter:
    """素材批次文件夹管理器，负责创建批次目录、写入单条素材 Markdown 文件
    以及生成批次索引文件。

    典型用法::

        writer = BatchWriter(output_dir="material", batch_name="my_batch")
        writer.create_batch_dir()
        path = writer.write_material(item)
        writer.write_index([item1, item2, item3])

    文件夹结构示例::

        material/
        └── my_batch/
            ├── 001.md
            ├── 002.md
            └── _index.md

    Args:
        output_dir: 批次根目录（相对或绝对路径均可），默认 "material"
        batch_name: 自定义批次名。为 None 时自动生成 batch_{YYYYMMDD}_{HHMMSS}
    """

    def __init__(
        self,
        output_dir: str = "material",
        batch_name: str | None = None,
    ) -> None:
        self._output_dir: Path = Path(output_dir)

        # 批次名：未指定则按时间戳自动生成
        if batch_name is not None:
            self._batch_name: str = batch_name
        else:
            self._batch_name = datetime.now().strftime("batch_%Y%m%d_%H%M%S")

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def batch_dir(self) -> Path:
        """批次文件夹路径（由根目录 + 批次名拼接而成）。"""
        return self._output_dir / self._batch_name

    @property
    def batch_name(self) -> str:
        """当前批次名称。"""
        return self._batch_name

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def create_batch_dir(self) -> Path:
        """创建批次文件夹（含所有中间父目录）。

        如果文件夹已存在则不会报错（exist_ok=True）。

        Returns:
            批次文件夹的绝对路径
        """
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        return self.batch_dir.resolve()

    def get_next_index(self) -> int:
        """扫描批次文件夹中已有的 NNN.md 文件，返回下一个可用编号。

        扫描规则：
            - 仅匹配三位数字命名的 .md 文件（如 001.md、012.md）
            - 取已有最大编号 + 1；文件夹为空时返回 1

        Returns:
            下一个可用的整数编号（从 1 开始）
        """
        # 如果批次文件夹尚未创建，视为空目录
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

        处理流程：
            1. 确保批次文件夹存在
            2. 获取下一个可用编号
            3. 渲染 Markdown（YAML frontmatter + 标题 + 引用块 + 正文）
            4. 以 {NNN}.md 命名写入批次文件夹

        Args:
            item: 素材数据实例

        Returns:
            写入文件的绝对路径
        """
        # 确保批次目录存在
        self.create_batch_dir()

        # 获取编号并生成文件名
        next_idx: int = self.get_next_index()
        file_name: str = f"{next_idx:03d}.md"
        file_path: Path = self.batch_dir / file_name

        # 渲染并写入
        markdown_content: str = _render_material_markdown(item)
        file_path.write_text(markdown_content, encoding="utf-8")

        return file_path.resolve()

    def write_index(self, items: list[MaterialItem]) -> Path:
        """生成批次索引文件 _index.md。

        索引内容包括：
            - 采集时间、素材数量、成功/失败统计、平台分布
            - 素材清单表格（序号 | 文件 | 平台 | 标题 | 状态 | 来源链接）
            - 失败素材在状态列中标注失败原因

        Args:
            items: 本批次全部素材列表

        Returns:
            索引文件的绝对路径
        """
        # 确保批次目录存在
        self.create_batch_dir()

        # 渲染索引内容并写入
        index_content: str = _render_index_markdown(items, self._batch_name)
        index_path: Path = self.batch_dir / "_index.md"
        index_path.write_text(index_content, encoding="utf-8")

        return index_path.resolve()
