# [变更记录]
# 日期: 2026-04-28
# 修改人: AI
# 修改内容: 新增 URL 解析与平台识别模块

"""
URL 解析与平台识别模块

职责：
- 从用户原始输入文本中提取所有 HTTP/HTTPS URL
- 根据域名和路径自动识别平台类型（B站/YouTube/公众号/通用网页）
- URL 清洗（去除末尾标点、中文标点包裹）

技术栈：
- 仅依赖标准库（re、urllib.parse、dataclasses、enum）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class Platform(Enum):
    """平台类型枚举"""
    BILIBILI = "bilibili"
    YOUTUBE = "youtube"
    WECHAT_MP = "wechat_mp"
    GITHUB = "github"
    X_TWITTER = "x_twitter"
    WEBPAGE = "webpage"


# URL 匹配正则：匹配 http:// 或 https:// 开头的链接，排除常见中文右标点和空白
_URL_PATTERN: re.Pattern[str] = re.compile(
    r'https?://[^\s<>）】\u3002\uff1b\uff0c\u201d\u300b]+'
)

# URL 末尾需要清除的标点字符集合（中英文标点）
_URL_TRIM_CHARS: str = ")]>.,;，。；、：:！!？?\"'”'》】»"


@dataclass(frozen=True)
class ParsedURL:
    """
    解析后的 URL 数据结构

    属性说明：
    - url: 清洗后的 URL 字符串
    - platform: 识别到的平台类型
    - original_text: 原始匹配到的 URL 文本（清洗前）
    """
    url: str
    platform: Platform
    original_text: str


def _clean_url(raw_url: str) -> str:
    """
    清洗 URL：去除末尾标点符号

    处理逻辑：
    - 逐字符从末尾检查，如果是标点则去除
    - 直到遇到非标点字符为止

    参数说明：
    - raw_url: 原始 URL 文本

    返回值：
    - 清洗后的 URL 字符串
    """
    url = raw_url.rstrip()
    while url and url[-1] in _URL_TRIM_CHARS:
        url = url[:-1]
    return url


def extract_urls(text: str) -> list[str]:
    """
    从文本中提取所有 HTTP/HTTPS URL

    处理逻辑：
    - 使用正则匹配所有 https?:// 开头的 URL
    - 对每个匹配结果进行末尾标点清洗
    - 去重并保持原始出现顺序

    参数说明：
    - text: 用户输入的原始文本

    返回值：
    - 清洗后的 URL 列表（去重保序）

    示例：
    >>> extract_urls("参考 https://mp.weixin.qq.com/s/xxx 和 https://www.langchain.com/yyy")
    ["https://mp.weixin.qq.com/s/xxx", "https://www.langchain.com/yyy"]
    """
    if not text:
        return []

    raw_matches = _URL_PATTERN.findall(text)
    cleaned: list[str] = []
    seen: set[str] = set()

    for raw in raw_matches:
        url = _clean_url(raw)
        if url and url not in seen:
            seen.add(url)
            cleaned.append(url)

    return cleaned


def identify_platform(url: str) -> Platform:
    """
    根据 URL 域名和路径识别平台类型

    识别规则：
    - bilibili.com/video/ → BILIBILI
    - youtube.com/watch 或 youtube.com/shorts/ → YOUTUBE
    - mp.weixin.qq.com → WECHAT_MP
    - 其他 HTTP URL → WEBPAGE

    参数说明：
    - url: 待识别的 URL 字符串

    返回值：
    - Platform 枚举值
    """
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return Platform.WEBPAGE

    netloc = parsed.netloc.lower()
    path = parsed.path.lower()

    # B站：bilibili.com/video/
    if netloc.endswith("bilibili.com") and "/video/" in path:
        return Platform.BILIBILI

    # YouTube：watch 或 shorts
    if netloc.endswith("youtube.com"):
        if path == "/watch" or path.startswith("/shorts/"):
            return Platform.YOUTUBE
        return Platform.YOUTUBE

    # 微信公众号
    if netloc.endswith("mp.weixin.qq.com"):
        return Platform.WECHAT_MP

    # GitHub 仓库（github.com）
    if netloc.endswith("github.com"):
        return Platform.GITHUB

    # X/Twitter：x.com 或 twitter.com
    if netloc.endswith("x.com") or netloc.endswith("twitter.com"):
        return Platform.X_TWITTER

    return Platform.WEBPAGE


def parse_urls_from_text(text: str) -> list[ParsedURL]:
    """
    从原始文本中提取 URL 并识别平台类型（组合函数）

    处理流程：
    1. 调用 extract_urls 提取所有 URL
    2. 对每个 URL 调用 identify_platform 识别平台
    3. 返回 ParsedURL 列表

    参数说明：
    - text: 用户输入的原始文本（可能包含中英文混杂的描述和多个链接）

    返回值：
    - ParsedURL 列表，保持 URL 出现顺序

    示例：
    >>> items = parse_urls_from_text('''
    ... 参考这些素材：
    ... https://mp.weixin.qq.com/s/xxx
    ... https://www.langchain.com/yyy
    ... https://www.langchain.com/blog/zzz
    ... ''')
    >>> [i.platform for i in items]
    [Platform.WECHAT_MP, Platform.WEBPAGE, Platform.WEBPAGE]
    """
    urls = extract_urls(text)
    results: list[ParsedURL] = []

    for url in urls:
        platform = identify_platform(url)
        results.append(ParsedURL(url=url, platform=platform, original_text=url))

    return results
