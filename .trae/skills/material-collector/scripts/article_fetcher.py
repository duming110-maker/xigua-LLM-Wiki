# [变更记录]
# 日期: 2026-04-28
# 修改人: AI
# 修改内容: 新增文章抓取模块（公众号+通用网页）
# 日期: 2026-05-09
# 修改人: AI
# 修改内容: 新增 GitHub 仓库页面抓取（通过 web-access CDP Proxy 真实浏览器渲染，解决 GitHub SPA 页面 httpx 无法获取 README 正文的问题）
# 日期: 2026-07-14
# 修改人: AI
# 修改内容: GitHub/X 抓取链路——调用 web-access skill 的 CDP Proxy HTTP API，复用用户日常浏览器登录态
# 日期: 2026-07-14
# 修改人: AI
# 修改内容: CDP Proxy 调用全部加 trust_env=False，避免 httpx 默认读系统 IE 代理（如 Clash 127.0.0.1:7892）把本地请求 127.0.0.1:3456 错误转发导致 502

"""
文章抓取模块

职责：
- 抓取微信公众号文章（HTML → 结构化数据 → Markdown）
- 抓取通用网页内容（HTML → Markdown）
- 抓取 GitHub / X(Twitter) 等重度 SPA 页面（通过 web-access CDP Proxy 真实浏览器渲染，携带登录态）
- 反爬检测与错误处理

技术栈：
- httpx（异步 HTTP 请求，同时用于调用本地 CDP Proxy API）
- beautifulsoup4（HTML 解析）
- html_to_md（HTML 转 Markdown，同目录模块）
- web-access CDP Proxy（外部依赖，需先 `node check-deps.mjs` 启动并连接用户浏览器）

依赖范围：
    完全独立，不导入任何宿主项目代码（app.* 等）。
    依赖同目录下的 html_to_md.py。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 微信公众号反爬拦截 URL 关键词
_WECHAT_BLOCK_MARKERS: tuple[str, ...] = (
    "weixin110",
    "security_check",
    "验证码",
    "环境异常",
)

# 微信公众号正文的视频号嵌入标记（需移除）
_WECHAT_NOOPENNER_PATTERN: re.Pattern[str] = re.compile(
    r'<mp-common-[^>]*>'
)

# web-access CDP Proxy 基址
# 启动方式：node <web-access skill>/scripts/check-deps.mjs
_CDP_PROXY_BASE: str = "http://127.0.0.1:3456"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class ArticleFetchResult:
    """文章抓取结果数据类。

    属性说明：
    - title: 文章标题
    - author: 作者/公众号名
    - publish_date: 发布日期字符串
    - content_markdown: 正文 Markdown 文本
    - source_url: 原始链接
    - platform: 平台标识（wechat_mp / webpage）
    - success: 抓取是否成功
    - error_message: 失败时的错误信息
    """
    title: str = ""
    author: str = ""
    publish_date: str = ""
    content_markdown: str = ""
    source_url: str = ""
    platform: str = "webpage"
    success: bool = True
    error_message: str = ""


# ---------------------------------------------------------------------------
# 文章抓取器
# ---------------------------------------------------------------------------


class ArticleFetcher:
    """
    文章抓取器：支持微信公众号文章和通用网页的抓取与解析。

    参数说明：
    - timeout: HTTP 请求超时秒数
    - user_agent: 请求头 User-Agent
    - max_retries: 最大重试次数
    """

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        max_retries: int = 3,
    ) -> None:
        self._timeout: int = timeout
        self._user_agent: str = user_agent
        self._max_retries: int = max_retries

    async def fetch(self, url: str, platform: str) -> ArticleFetchResult:
        """
        根据平台路由到对应的抓取方法

        参数说明：
        - url: 文章 URL
        - platform: 平台标识（wechat_mp / webpage / github / x_twitter）

        返回值：
        - ArticleFetchResult 抓取结果
        """
        if platform == "wechat_mp":
            return await self.fetch_wechat_mp(url)
        if platform == "github":
            return await self.fetch_github(url)
        if platform == "x_twitter":
            return await self.fetch_x_twitter(url)
        return await self.fetch_webpage(url)

    async def fetch_wechat_mp(self, url: str) -> ArticleFetchResult:
        """
        抓取微信公众号文章

        处理流程：
        1. 使用 httpx 抓取 HTML
        2. 检测反爬拦截（weixin110、验证码等）
        3. 使用 BeautifulSoup 解析标题、作者、发布日期、正文
        4. 将正文 HTML 转为 Markdown

        参数说明：
        - url: 公众号文章 URL

        返回值：
        - ArticleFetchResult 抓取结果
        """
        try:
            html: str = await self._fetch_html(url)
        except httpx.HTTPError as exc:
            return ArticleFetchResult(
                source_url=url,
                platform="wechat_mp",
                success=False,
                error_message=f"HTTP 请求失败: {exc}",
            )

        # 反爬检测
        if self._is_wechat_blocked(html, url):
            return ArticleFetchResult(
                source_url=url,
                platform="wechat_mp",
                success=False,
                error_message="公众号文章被反爬拦截（可能需要更换网络或稍后重试）",
            )

        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title: str = ""
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = str(og_title["content"]).strip()
        if not title:
            activity_name = soup.find("h1", id="activity-name")
            if activity_name:
                title = activity_name.get_text().strip()
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text().strip()
        if not title:
            title = url

        # 提取作者
        author: str = ""
        js_author = soup.find("span", id="js_author_name")
        if js_author:
            author = js_author.get_text().strip()
        if not author:
            js_name = soup.find("strong", id="js_name")
            if js_name:
                author = js_name.get_text().strip()

        # 提取发布日期
        publish_date: str = ""
        # 优先从 meta 标签获取
        publish_time_meta = soup.find("meta", attrs={"property": "article:published_time"})
        if publish_time_meta and publish_time_meta.get("content"):
            publish_date = str(publish_time_meta["content"]).strip()[:10]
        if not publish_date:
            publish_time_el = soup.find("em", id="publish_time")
            if publish_time_el:
                publish_date = publish_time_el.get_text().strip()

        # 提取正文
        content_html: str = ""
        js_content = soup.find("div", id="js_content")
        if js_content:
            # 移除视频号嵌入等非正文元素（mp-common-xxx 自定义标签）
            for tag in js_content.find_all(re.compile(r"^mp-common-")):
                tag.decompose()
            content_html = str(js_content)
        if not content_html:
            rich_media = soup.find("div", class_="rich_media_content")
            if rich_media:
                content_html = str(rich_media)

        # 转换为 Markdown
        content_markdown: str = ""
        if content_html:
            from html_to_md import html_to_markdown
            content_soup = BeautifulSoup(content_html, "html.parser")
            content_markdown = html_to_markdown(content_soup, base_url=url)
            # 清理多余空行
            content_markdown = re.sub(r"\n{3,}", "\n\n", content_markdown).strip()

        return ArticleFetchResult(
            title=title,
            author=author,
            publish_date=publish_date,
            content_markdown=content_markdown,
            source_url=url,
            platform="wechat_mp",
            success=True,
        )

    async def fetch_webpage(self, url: str) -> ArticleFetchResult:
        """
        抓取通用网页内容

        处理流程：
        1. 使用 httpx 抓取 HTML
        2. 使用 html_to_md.extract_main_content 提取标题和正文
        3. 返回结构化结果

        参数说明：
        - url: 网页 URL

        返回值：
        - ArticleFetchResult 抓取结果
        """
        try:
            html: str = await self._fetch_html(url)
        except httpx.HTTPError as exc:
            return ArticleFetchResult(
                source_url=url,
                platform="webpage",
                success=False,
                error_message=f"HTTP 请求失败: {exc}",
            )

        from html_to_md import extract_main_content

        title, content_markdown = extract_main_content(html, url=url)

        return ArticleFetchResult(
            title=title,
            author="",
            publish_date="",
            content_markdown=content_markdown,
            source_url=url,
            platform="webpage",
            success=True,
        )

    async def fetch_github(self, url: str) -> ArticleFetchResult:
        """
        使用 web-access CDP Proxy 抓取 GitHub 仓库页面 README 正文

        为什么需要 CDP Proxy：
        GitHub 是 React SPA，README 正文通过 JavaScript 动态渲染到
        <article class="markdown-body"> 中。httpx 拿到的静态 HTML
        只有导航栏空壳，无法获取实际内容。
        CDP Proxy 直连用户日常浏览器（携带 GitHub 登录态），渲染稳定，
        且无需在脚本侧维护独立的 Chromium 进程。

        处理流程：
        1. 检查 CDP Proxy 就绪（未就绪返回明确启动指引）
        2. POST /new 创建后台 tab，由 Proxy 自动等待页面加载完成
        3. POST /eval 提取 <article class="markdown-body"> 的 innerHTML
           找不到 README 容器时回退到整个 body
        4. POST /eval 提取页面 title
        5. GET /close 关闭自己创建的 tab（保留用户原有 tab 不受影响）
        6. HTML → Markdown 转换

        参数说明：
        - url: GitHub 仓库页面 URL

        返回值：
        - ArticleFetchResult 抓取结果（含 README Markdown 正文）
        """
        try:
            await self._ensure_cdp_ready()
            target_id: str = await self._cdp_new_tab(url)
        except RuntimeError as exc:
            return ArticleFetchResult(
                source_url=url,
                platform="github",
                success=False,
                error_message=str(exc),
            )

        try:
            # 提取 GitHub README 正文容器
            # GitHub 用 <article class="markdown-body"> 包裹 README 内容
            # 找不到时回退到整个 body（部分 GitHub 页面如组织首页结构不同）
            html: str = await self._cdp_eval(
                target_id,
                """(() => {
                    const el = document.querySelector('article.markdown-body');
                    if (el) return el.innerHTML;
                    const body = document.body;
                    return body ? body.innerHTML : '';
                })()""",
            ) or ""
            # 提取页面标题
            title: str = await self._cdp_eval(target_id, "document.title") or url
        finally:
            await self._cdp_close_tab(target_id)

        if not html:
            return ArticleFetchResult(
                source_url=url,
                platform="github",
                success=False,
                error_message="GitHub 页面未找到正文容器 article.markdown-body",
            )

        # HTML → Markdown 转换
        from html_to_md import html_to_markdown
        content_soup = BeautifulSoup(html, "html.parser")
        content_md: str = html_to_markdown(content_soup, base_url=url)
        # 清理多余空行
        content_md = re.sub(r"\n{3,}", "\n\n", content_md).strip()

        return ArticleFetchResult(
            title=title,
            author="",
            publish_date="",
            content_markdown=content_md,
            source_url=url,
            platform="github",
            success=True,
        )

    async def fetch_x_twitter(self, url: str) -> ArticleFetchResult:
        """
        使用 web-access CDP Proxy 抓取 X/Twitter 推文正文

        为什么需要 CDP Proxy：
        X/Twitter 是重度 JS SPA，推文正文通过 JavaScript 动态渲染。
        httpx 拿到的静态 HTML 只有登录页空壳，无法获取实际内容。
        CDP Proxy 直连用户日常浏览器，天然携带 X 登录态，能稳定获取
        推文元数据和 X Article 长文正文。

        处理流程：
        1. 检查 CDP Proxy 就绪
        2. POST /new 创建后台 tab 加载 URL（Proxy 自动等 load 完成）
        3. 轮询等待 <article> 元素出现（推文容器），最多等 15 秒
        4. 额外等 3 秒让 X Article 长文内容完全渲染
        5. POST /eval 提取 body.innerText（同时覆盖推文元数据 + 文章正文）
        6. POST /eval 提取推文首段作为标题
        7. GET /close 关闭 tab
        8. 清洗底部导航噪音 → 简易 Markdown 分段

        参数说明：
        - url: X/Twitter 推文 URL（https://x.com/... 或 https://twitter.com/...）

        返回值：
        - ArticleFetchResult 抓取结果（含推文 Markdown 正文）
        """
        try:
            await self._ensure_cdp_ready()
            target_id: str = await self._cdp_new_tab(url)
        except RuntimeError as exc:
            return ArticleFetchResult(
                source_url=url,
                platform="x_twitter",
                success=False,
                error_message=str(exc),
            )

        try:
            # 等待 <article> 元素出现（推文容器），最多 15 秒
            # X/Twitter 在 load 事件后还需 JS 渲染推文内容
            found = await self._cdp_wait_for_selector(target_id, "article", timeout=15)
            if not found:
                return ArticleFetchResult(
                    source_url=url,
                    platform="x_twitter",
                    success=False,
                    error_message="X/Twitter 页面 15 秒内未渲染出 article 元素（可能未登录或被反爬拦截）",
                )
            # 额外等 3 秒让 X Article 长文内容完全渲染
            await asyncio.sleep(3)

            # 提取正文：直接获取 body 纯文本
            # <article> 标签只含推文元数据，X Article 长文正文渲染在页面其他区域
            # body.innerText 可以同时捕获推文元数据和文章正文
            body_text: str = await self._cdp_eval(
                target_id, "document.body.innerText"
            ) or ""
            # 清洗：去掉 X 页面底部的导航噪音
            for cutoff_marker in (
                "\nTrending now\n",
                "\nTerms of Service\n",
                "\nDon't miss what's happening\n",
            ):
                idx = body_text.find(cutoff_marker)
                if idx > 500:  # 确保截断点不在文章开头
                    body_text = body_text[:idx].strip()
                    break

            # 提取标题：优先用推文第一段有意义文字
            title: str = await self._cdp_eval(
                target_id,
                """(() => {
                    const el = document.querySelector('article [data-testid="tweetText"]');
                    if (el) return el.innerText.split('\\n')[0].slice(0, 100);
                    return '';
                })()""",
            ) or ""
            if not title:
                title = await self._cdp_eval(target_id, "document.title") or ""
            if not title or ("X" in title and "/" not in title and len(title) < 30):
                title = body_text.split("\n")[0][:100] if body_text else url
        finally:
            await self._cdp_close_tab(target_id)

        # 将纯文本转为简易 Markdown（用双换行分段，去除连续空行）
        lines = body_text.strip().split("\n")
        md_lines: list[str] = []
        prev_empty = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not prev_empty:
                    md_lines.append("")
                prev_empty = True
            else:
                md_lines.append(stripped)
                prev_empty = False
        content_md = "\n".join(md_lines)

        return ArticleFetchResult(
            title=title,
            author="",
            publish_date="",
            content_markdown=content_md,
            source_url=url,
            platform="x_twitter",
            success=True,
        )

    # ------------------------------------------------------------------
    # web-access CDP Proxy 辅助方法
    # ------------------------------------------------------------------

    async def _ensure_cdp_ready(self) -> None:
        """
        检查 web-access CDP Proxy 是否就绪

        检查项：
        - GET /health 能访问（Proxy 进程已启动）
        - status == "ok" 且 connected == true（已连上用户浏览器）

        异常：
        - RuntimeError: Proxy 未启动或未连接浏览器，错误信息中给出启动指引
        """
        try:
            # trust_env=False：不读系统代理设置，避免本地 127.0.0.1:3456 请求被 Clash 等代理错误转发
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                resp = await client.get(f"{_CDP_PROXY_BASE}/health")
                data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"web-access CDP Proxy 未就绪（{exc}）。"
                f"请先启动：node <web-access skill>/scripts/check-deps.mjs"
            ) from exc

        if data.get("status") != "ok" or not data.get("connected"):
            raise RuntimeError(
                "web-access CDP Proxy 已启动但未连接浏览器。"
                "请在你的浏览器（Chrome/Edge）地址栏访问 chrome://inspect/#remote-debugging，"
                "勾选 Allow remote debugging，然后重新运行 check-deps.mjs。"
            )

    async def _cdp_new_tab(self, url: str) -> str:
        """
        通过 CDP Proxy 创建后台 tab 并加载 URL

        参数说明：
        - url: 目标 URL（原样作为 POST body 传入，不进行 URL-encode）

        返回值：
        - targetId 字符串

        异常：
        - RuntimeError: 创建失败
        """
        # trust_env=False：见 _ensure_cdp_ready 注释
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(f"{_CDP_PROXY_BASE}/new", content=url)
            data = resp.json()
        if resp.status_code != 200 or "targetId" not in data:
            raise RuntimeError(
                f"CDP /new 创建 tab 失败: {data.get('error', resp.text)}"
            )
        return str(data["targetId"])

    async def _cdp_eval(self, target_id: str, js: str) -> Any:
        """
        在指定 tab 中执行 JavaScript 表达式

        参数说明：
        - target_id: 目标 tab ID
        - js: JavaScript 表达式（returnByValue=true，awaitPromise=true）

        返回值：
        - JS 表达式的返回值（已序列化为 Python 对象）

        异常：
        - RuntimeError: JS 执行失败
        """
        # trust_env=False：见 _ensure_cdp_ready 注释
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(
                f"{_CDP_PROXY_BASE}/eval?target={target_id}",
                content=js,
            )
            data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(
                f"CDP /eval 执行失败: {data.get('error', resp.text)}"
            )
        return data.get("value")

    async def _cdp_wait_for_selector(
        self, target_id: str, selector: str, timeout: int = 15
    ) -> bool:
        """
        轮询等待 CSS 选择器在页面中出现

        为什么不用 page.wait_for_selector：
        CDP Proxy /eval 端点是单次执行，不内建等待。在 Python 侧轮询更直观，
        也便于在 SPA 渲染较慢时调整节奏。

        参数说明：
        - target_id: 目标 tab ID
        - selector: CSS 选择器
        - timeout: 最大等待秒数（默认 15）

        返回值：
        - True 表示选择器已出现；False 表示超时
        """
        js = f"!!document.querySelector({json.dumps(selector)})"
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await self._cdp_eval(target_id, js):
                    return True
            except RuntimeError:
                # eval 失败可能是页面正在跳转，吞掉继续轮询
                pass
            await asyncio.sleep(0.5)
        return False

    async def _cdp_close_tab(self, target_id: str) -> None:
        """
        关闭指定 tab（吞掉异常，确保不影响主流程）

        参数说明：
        - target_id: 目标 tab ID
        """
        try:
            # trust_env=False：见 _ensure_cdp_ready 注释
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                await client.get(f"{_CDP_PROXY_BASE}/close?target={target_id}")
        except Exception:
            pass

    async def _fetch_html(self, url: str) -> str:
        """
        通用 HTTP 抓取，带重试和超时

        参数说明：
        - url: 目标 URL

        返回值：
        - HTML 文本字符串

        异常：
        - httpx.HTTPError: HTTP 请求失败
        - RuntimeError: 响应为空或状态码异常
        """
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self._user_agent},
                ) as client:
                    response: httpx.Response = await client.get(url)
                    response.raise_for_status()
                    html: str = response.text

                    if not html or not html.strip():
                        raise RuntimeError("响应内容为空")

                    return html

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue

        if last_exc:
            raise last_exc
        raise RuntimeError("HTTP 请求失败，原因未知")

    @staticmethod
    def _is_wechat_blocked(html: str, url: str) -> bool:
        """
        检测微信公众号是否被反爬拦截

        检测条件：
        - 重定向后的 URL 包含 weixin110
        - HTML 内容中包含验证码、环境异常等关键词

        参数说明：
        - html: 页面 HTML 内容
        - url: 最终 URL

        返回值：
        - True 表示被拦截
        """
        if "weixin110" in url:
            return True
        for marker in _WECHAT_BLOCK_MARKERS:
            if marker in html:
                return True
        return False
