# [变更记录]
# 日期: 2026-04-28
# 修改人: AI
# 修改内容: 新增素材收集器核心入口脚本（CLI + Python API）

"""
素材收集器核心入口脚本

职责：
- 解析用户输入（命令行参数/原始文本），提取所有 URL
- 自动识别每个 URL 的平台类型
- 根据平台路由到对应的处理链路（视频/文章/网页）
- 将处理结果以 Markdown 文件保存到批次文件夹
- 生成批次索引文件

调用方式：
    CLI:
        python collector.py --url "https://xxx" --url "https://yyy"
        python collector.py --text "参考这些素材：https://xxx https://yyy"
        python collector.py --file urls.txt
        python collector.py --url "https://xxx" --name "自定义批次名"

    Python API:
        collector = MaterialCollector(config_path="config.yaml")
        result = collector.collect(raw_text="包含链接的文本")
        print(result.batch_dir)

依赖范围：
    完全独立，不导入任何宿主项目代码（app.* 等）。
    依赖同目录下的 url_parser、video_processor、article_fetcher、markdown_writer 模块。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# 日志配置（Windows 下强制 UTF-8 避免中文乱码）
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 修复本地 Whisper 的 OpenMP 重复加载冲突（torch + whisper 共存时常见）：
# 不设会报 "Initializing libiomp5md.dll already initialized" 导致 ASR 直接崩溃。
# 必须在 whisper/torch 被 import 之前设置——本模块顶层最早，下游 asr_client 延迟 import 时已生效。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("material-collector")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class CollectItem:
    """单条素材的收集结果。

    属性说明：
    - url: 原始 URL
    - platform: 平台标识
    - success: 是否成功
    - title: 素材标题
    - error_message: 失败原因
    """
    url: str = ""
    platform: str = ""
    success: bool = True
    title: str = ""
    error_message: str = ""


@dataclass
class CollectResult:
    """批次收集结果。

    属性说明：
    - batch_dir: 批次文件夹路径
    - batch_name: 批次名称
    - success_count: 成功数量
    - fail_count: 失败数量
    - items: 各条素材的结果列表
    """
    batch_dir: str = ""
    batch_name: str = ""
    success_count: int = 0
    fail_count: int = 0
    items: list[CollectItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 视频平台标识集合
# ---------------------------------------------------------------------------

_VIDEO_PLATFORMS: frozenset[str] = frozenset({"bilibili", "youtube"})

_LOCAL_VIDEO_EXTS: frozenset[str] = frozenset({".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"})
_LOCAL_AUDIO_EXTS: frozenset[str] = frozenset({".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"})

_PLATFORM_LABELS: dict[str, str] = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "wechat_mp": "微信公众号",
    "github": "GitHub",
    "x_twitter": "X/Twitter",
    "webpage": "网页",
    "local_media": "本地媒体",
}


# ---------------------------------------------------------------------------
# 核心收集器
# ---------------------------------------------------------------------------


def _is_local_media(path: str) -> bool:
    """判断输入是否为本地视频/音频文件路径"""
    if path.startswith(("http://", "https://")):
        return False
    ext: str = os.path.splitext(path)[1].lower()
    return ext in _LOCAL_VIDEO_EXTS or ext in _LOCAL_AUDIO_EXTS


class MaterialCollector:
    """
    素材收集器核心类

    参数说明：
    - config_path: 配置文件路径（config.yaml）
    - output_dir: 素材输出根目录（覆盖配置文件中的值）
    """

    def __init__(
        self,
        config_path: str = "",
        output_dir: str = "",
    ) -> None:
        self._config: dict[str, Any] = {}
        self._output_dir: str = output_dir
        self._config_path: str = config_path

        # 加载配置
        if config_path and os.path.isfile(config_path):
            self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        """
        加载 YAML 配置文件

        参数说明：
        - config_path: config.yaml 文件路径
        """
        with open(config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        if not self._output_dir:
            self._output_dir = self._config.get("output_dir", "material")

        logger.info("配置文件加载完成: %s", config_path)

    def _get_video_processor(self) -> Any:
        """
        创建 VideoProcessor 实例（延迟导入，使用配置参数）

        返回值：
        - VideoProcessor 实例
        """
        from video_processor import VideoProcessor
        from asr_client import ASRConfig, WhisperConfig

        ytdlp_cfg: dict[str, Any] = self._config.get("ytdlp", {})
        temp_cfg: dict[str, Any] = self._config.get("temp", {})
        asr_cfg: dict[str, Any] = self._config.get("asr", {})

        whisper_cfg_data: dict[str, Any] = asr_cfg.get("whisper", {})
        whisper_config = WhisperConfig(
            model=whisper_cfg_data.get("model", "turbo"),
            device=whisper_cfg_data.get("device", "cuda"),
            language=whisper_cfg_data.get("language", "zh"),
            download_root=whisper_cfg_data.get("download_root", ""),
        )

        asr_config = ASRConfig(
            mode=asr_cfg.get("mode", "local"),
            model_id=asr_cfg.get("model_id", "qwen3-asr-flash"),
            filetrans_model_id=asr_cfg.get("filetrans_model_id", "qwen3-asr-flash-filetrans"),
            max_attempts=asr_cfg.get("max_attempts", 3),
            segment_seconds=asr_cfg.get("segment_seconds", 240),
            whisper=whisper_config,
        )

        return VideoProcessor(
            ytdlp_format=ytdlp_cfg.get("format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"),
            ytdlp_timeout=ytdlp_cfg.get("timeout", 120),
            temp_dir=temp_cfg.get("dir", ""),
            cleanup_temp=temp_cfg.get("cleanup", True),
            asr_config=asr_config,
        )

    def _get_article_fetcher(self) -> Any:
        """
        创建 ArticleFetcher 实例（延迟导入，使用配置参数）

        返回值：
        - ArticleFetcher 实例
        """
        from article_fetcher import ArticleFetcher

        fetcher_cfg: dict[str, Any] = self._config.get("fetcher", {})
        return ArticleFetcher(
            timeout=fetcher_cfg.get("timeout", 30),
            user_agent=fetcher_cfg.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ),
            max_retries=fetcher_cfg.get("max_retries", 3),
        )

    async def collect(
        self,
        raw_text: str = "",
        urls: list[str] | None = None,
        batch_name: str | None = None,
    ) -> CollectResult:
        """
        执行素材收集（Python API 主入口）

        参数说明：
        - raw_text: 用户输入的原始文本（自动提取 URL）
        - urls: URL 列表（与 raw_text 二选一）
        - batch_name: 自定义批次名称

        返回值：
        - CollectResult 批次收集结果
        """
        from url_parser import parse_urls_from_text, extract_urls, identify_platform, Platform
        from markdown_writer import BatchWriter, MaterialItem

        # 1. 从 urls 中分离本地文件和 URL
        local_files: list[str] = []
        url_list: list[str] = []

        if urls:
            for u in urls:
                if _is_local_media(u):
                    local_files.append(os.path.abspath(os.path.join(os.getcwd(), u)))
                else:
                    url_list.append(u)

        # 2. 从 raw_text 中提取 URL（raw_text 不支持本地文件路径）
        parsed_items = []
        if url_list:
            parsed_items.extend(
                type("ParsedURL", (), {"url": u, "platform": identify_platform(u)})()
                for u in url_list
            )
        if raw_text:
            parsed_items.extend(parse_urls_from_text(raw_text))

        if not parsed_items and not local_files:
            logger.error("未提供任何输入（raw_text 或 urls）")
            return CollectResult()

        total_count: int = len(parsed_items) + len(local_files)
        logger.info("共提取到 %d 个输入（URL: %d，本地文件: %d）", total_count, len(parsed_items), len(local_files))

        # 3. 创建批次文件夹
        writer = BatchWriter(
            output_dir=self._output_dir,
            batch_name=batch_name,
        )
        writer.create_batch_dir()
        logger.info("批次文件夹: %s", writer.batch_dir)

        # 4. 逐个处理
        result = CollectResult(
            batch_dir=str(writer.batch_dir.resolve()),
            batch_name=writer.batch_name,
        )

        material_items: list[MaterialItem] = []
        idx: int = 0

        # 4a. 处理 URL
        for parsed in parsed_items:
            idx += 1
            platform_str: str = parsed.platform.value if hasattr(parsed.platform, "value") else str(parsed.platform)
            platform_label: str = _PLATFORM_LABELS.get(platform_str, platform_str)
            logger.info("[%d/%d] 处理 %s 链接: %s", idx, total_count, platform_label, parsed.url[:80])

            try:
                if platform_str in _VIDEO_PLATFORMS:
                    item = await self._process_video(parsed.url, platform_str)
                else:
                    item = await self._process_article(parsed.url, platform_str)
            except Exception as exc:
                logger.error("[%d/%d] 处理失败: %s", idx, total_count, exc)
                item = MaterialItem(
                    source_url=parsed.url,
                    platform=platform_str,
                    title=f"处理失败: {parsed.url[:50]}",
                    content_type="webpage",
                    success=False,
                    error_message=str(exc),
                )

            file_path = writer.write_material(item)
            material_items.append(item)

            collect_item = CollectItem(
                url=parsed.url,
                platform=platform_str,
                success=item.success,
                title=item.title,
                error_message=item.error_message,
            )
            result.items.append(collect_item)

            if item.success:
                result.success_count += 1
                logger.info("[%d/%d] 完成: %s → %s", idx, total_count, item.title[:40], file_path.name)
            else:
                result.fail_count += 1
                logger.warning("[%d/%d] 失败: %s", idx, total_count, item.error_message)

        # 4b. 处理本地媒体文件
        for file_input in local_files:
            idx += 1
            file_name: str = os.path.basename(file_input)
            logger.info("[%d/%d] 处理本地媒体: %s", idx, total_count, file_name)

            try:
                item = await self._process_local_media(file_input)
            except Exception as exc:
                logger.error("[%d/%d] 处理失败: %s", idx, total_count, exc)
                item = MaterialItem(
                    source_url=file_input,
                    platform="local_media",
                    title=f"处理失败: {file_name}",
                    content_type="video_transcript",
                    success=False,
                    error_message=str(exc),
                )

            file_path = writer.write_material(item)
            material_items.append(item)

            collect_item = CollectItem(
                url=file_input,
                platform="local_media",
                success=item.success,
                title=item.title,
                error_message=item.error_message,
            )
            result.items.append(collect_item)

            if item.success:
                result.success_count += 1
                logger.info("[%d/%d] 完成: %s → %s", idx, total_count, item.title[:40], file_path.name)
            else:
                result.fail_count += 1
                logger.warning("[%d/%d] 失败: %s", idx, total_count, item.error_message)

        # 5. 生成批次索引
        index_path = writer.write_index(material_items)
        logger.info("批次索引已生成: %s", index_path)

        # 6. 输出总结
        logger.info("=" * 60)
        logger.info("素材收集完成！")
        logger.info("  批次文件夹: %s", writer.batch_dir.resolve())
        logger.info("  成功: %d / 失败: %d / 总计: %d", result.success_count, result.fail_count, len(result.items))
        logger.info("=" * 60)

        return result

    async def _process_video(self, url: str, platform: str) -> Any:
        """
        处理视频类链接（下载 → 音频 → ASR → MaterialItem）

        参数说明：
        - url: 视频 URL
        - platform: 平台标识

        返回值：
        - MaterialItem 素材数据
        """
        from markdown_writer import MaterialItem

        processor = self._get_video_processor()
        video_result = await processor.process(url, platform)

        return MaterialItem(
            source_url=url,
            platform=platform,
            title=video_result.title or f"视频: {url[:50]}",
            content_type="video_transcript",
            content=video_result.transcript,
            duration_seconds=video_result.duration_seconds,
            asr_model=video_result.asr_model,
            success=video_result.success,
            error_message=video_result.error_message,
        )

    async def _process_article(self, url: str, platform: str) -> Any:
        """
        处理文章类链接（抓取 → 解析 → MaterialItem）

        参数说明：
        - url: 文章 URL
        - platform: 平台标识

        返回值：
        - MaterialItem 素材数据
        """
        from markdown_writer import MaterialItem

        fetcher = self._get_article_fetcher()
        article_result = await fetcher.fetch(url, platform)

        content_type: str = "article" if platform == "wechat_mp" else "webpage"

        return MaterialItem(
            source_url=url,
            platform=platform,
            title=article_result.title or url,
            author=article_result.author,
            publish_date=article_result.publish_date,
            content_type=content_type,
            content=article_result.content_markdown,
            success=article_result.success,
            error_message=article_result.error_message,
        )

    async def _process_local_media(self, file_path: str) -> Any:
        """
        处理本地视频/音频文件（音频提取 → ASR 转写 → MaterialItem）

        参数说明：
        - file_path: 本地媒体文件的绝对路径

        返回值：
        - MaterialItem 素材数据
        """
        from markdown_writer import MaterialItem
        from audio_utils import extract_audio
        from asr_client import transcribe, ASRConfig, get_asr_model_name

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext: str = os.path.splitext(file_path)[1].lower()
        is_video: bool = ext in _LOCAL_VIDEO_EXTS
        title: str = os.path.splitext(os.path.basename(file_path))[0]

        # 音频文件直接转写；视频文件先提取音频
        if is_video:
            logger.info("  提取音频中: %s", os.path.basename(file_path))
            extraction = await extract_audio(file_path)
            audio_path: str = extraction.audio_path
            duration_seconds: float = extraction.duration_seconds
        else:
            audio_path = file_path
            from audio_utils import _probe_duration
            duration_seconds = await _probe_duration(file_path)

        logger.info("  ASR 转写中，时长: %.1f秒", duration_seconds)
        asr_config = self._get_asr_config()
        transcript: str = await transcribe(audio_path, asr_config, duration_seconds=duration_seconds)
        logger.info("  转写完成，文本长度: %d字符", len(transcript))

        # 清理临时音频文件（仅视频提取的）
        if is_video:
            try:
                os.remove(audio_path)
            except OSError:
                pass

        return MaterialItem(
            source_url=file_path,
            platform="local_media",
            title=title,
            content_type="video_transcript",
            content=transcript,
            duration_seconds=duration_seconds,
            asr_model=get_asr_model_name(asr_config),
            success=True,
        )

    def _get_asr_config(self) -> Any:
        """从配置文件创建 ASRConfig 实例"""
        from asr_client import ASRConfig, WhisperConfig

        asr_cfg: dict[str, Any] = self._config.get("asr", {})
        whisper_cfg_data: dict[str, Any] = asr_cfg.get("whisper", {})
        whisper_config = WhisperConfig(
            model=whisper_cfg_data.get("model", "turbo"),
            device=whisper_cfg_data.get("device", "cuda"),
            language=whisper_cfg_data.get("language", "zh"),
            download_root=whisper_cfg_data.get("download_root", ""),
        )

        return ASRConfig(
            mode=asr_cfg.get("mode", "local"),
            model_id=asr_cfg.get("model_id", "qwen3-asr-flash"),
            filetrans_model_id=asr_cfg.get("filetrans_model_id", "qwen3-asr-flash-filetrans"),
            max_attempts=asr_cfg.get("max_attempts", 3),
            segment_seconds=asr_cfg.get("segment_seconds", 240),
            whisper=whisper_config,
        )


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """
    解析命令行参数

    返回值：
    - argparse.Namespace 解析后的参数
    """
    parser = argparse.ArgumentParser(
        description="素材收集器 - 从多个平台批量收集写作素材",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python collector.py --url "https://mp.weixin.qq.com/s/xxx"
  python collector.py --url "https://www.bilibili.com/video/BVxxx" --url "https://www.youtube.com/watch?v=yyy"
  python collector.py --url "本地视频.mp4" --url "本地音频.mp3"
  python collector.py --text "参考这些素材：https://xxx https://yyy"
  python collector.py --file urls.txt --name "我的素材"
        """,
    )
    parser.add_argument("--url", action="append", dest="urls", help="视频/文章 URL（可多次指定）")
    parser.add_argument("--file", dest="file", help="包含 URL 列表的文本文件路径")
    parser.add_argument("--text", dest="text", help="包含 URL 的原始文本（自动提取 URL）")
    parser.add_argument("--name", dest="name", default=None, help="自定义批次名称")
    parser.add_argument("--config", dest="config", default="", help="配置文件路径（默认同目录 config.yaml）")
    parser.add_argument("--output", dest="output", default="", help="素材输出根目录（覆盖配置文件）")

    return parser.parse_args()


def _resolve_config_path(cli_config: str) -> str:
    """
    解析配置文件路径

    优先级：
    1. 命令行指定的路径
    2. 脚本同目录下的 config.yaml

    参数说明：
    - cli_config: 命令行指定的配置文件路径

    返回值：
    - 配置文件路径（可能为空字符串表示无配置）
    """
    if cli_config and os.path.isfile(cli_config):
        return cli_config

    # 尝试脚本同目录
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    default_config: str = os.path.join(script_dir, "config.yaml")
    if os.path.isfile(default_config):
        return default_config

    return ""


async def _main() -> None:
    """CLI 主入口函数"""
    args = _parse_args()

    # 收集 URL 列表
    urls: list[str] = list(args.urls or [])
    raw_text: str = args.text or ""

    # 从文件读取 URL
    if args.file:
        file_path: str = args.file
        if not os.path.isfile(file_path):
            logger.error("文件不存在: %s", file_path)
            sys.exit(1)
        with open(file_path, "r", encoding="utf-8") as f:
            file_content: str = f.read()
        raw_text = raw_text + "\n" + file_content if raw_text else file_content

    if not urls and not raw_text:
        logger.error("未提供任何输入。请使用 --url、--text 或 --file 参数。")
        sys.exit(1)

    # 解析配置文件路径
    config_path: str = _resolve_config_path(args.config)

    # 创建收集器并执行
    collector = MaterialCollector(
        config_path=config_path,
        output_dir=args.output,
    )

    result: CollectResult = await collector.collect(
        raw_text=raw_text,
        urls=urls if urls else None,
        batch_name=args.name,
    )

    # 非零退出码（所有素材都失败时）
    if result.fail_count > 0 and result.success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
