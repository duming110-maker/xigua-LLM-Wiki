# [变更记录]
# 日期: 2026-04-28
# 修改人: AI
# 修改内容: 新增视频处理模块（下载→音频→ASR完整链路）
# 日期: 2026-07-14
# 修改人: AI
# 修改内容: 新增 CDP Proxy cookie 获取——下载前从用户浏览器拿登录态 cookie 写为 Netscape 文件传给 yt-dlp，解决 B站 412 风控；CDP Proxy 不可用时不阻塞，降级为无 cookie 下载

"""
视频处理模块

职责：
- 根据平台类型下载视频（B站/YouTube）
- 从视频中提取音频
- 使用 ASR 将音频转为文本
- 自动清理临时文件

技术栈：
- yt-dlp（B站/YouTube 下载）
- httpx（视频文件下载 + CDP Proxy 调用）
- audio_utils（音频提取）
- asr_client（语音转文本）
- web-access CDP Proxy（外部依赖，用于获取浏览器登录态 cookie；不可用时降级为匿名下载）

依赖范围：
    完全独立，不导入任何宿主项目代码（app.* 等）。
    依赖同目录下的 audio_utils.py 和 asr_client.py。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class VideoProcessResult:
    """视频处理结果数据类。

    属性说明：
    - title: 视频标题
    - transcript: ASR 转写文本
    - duration_seconds: 视频时长（秒）
    - platform: 平台标识（bilibili/youtube）
    - video_url: 原始视频链接
    - asr_model: 使用的 ASR 模型名称
    - success: 处理是否成功
    - error_message: 失败时的错误信息
    """
    title: str = ""
    transcript: str = ""
    duration_seconds: float = 0.0
    platform: str = ""
    video_url: str = ""
    asr_model: str = ""
    success: bool = True
    error_message: str = ""


# ---------------------------------------------------------------------------
# 视频处理器
# ---------------------------------------------------------------------------


class VideoProcessor:
    """
    视频处理器：协调下载、音频提取和 ASR 转写的完整链路。

    参数说明：
    - ytdlp_format: yt-dlp 下载格式字符串
    - ytdlp_timeout: yt-dlp 超时秒数
    - temp_dir: 临时文件目录，空则使用系统临时目录
    - cleanup_temp: 处理完成后是否清理临时文件
    - asr_config: ASR 配置对象，为 None 时使用默认配置（local 模式）
    """

    def __init__(
        self,
        ytdlp_format: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        ytdlp_timeout: int = 120,
        temp_dir: str = "",
        cleanup_temp: bool = True,
        asr_config: Any = None,
    ) -> None:
        self._ytdlp_format: str = ytdlp_format
        self._ytdlp_timeout: int = ytdlp_timeout
        self._temp_dir: str = temp_dir or tempfile.gettempdir()
        self._cleanup_temp: bool = cleanup_temp
        self._asr_config: Any = asr_config
        self._temp_files: list[str] = []

    async def process(self, url: str, platform: str) -> VideoProcessResult:
        """
        完整视频处理链路：下载 → 音频提取 → ASR 转写

        参数说明：
        - url: 视频 URL
        - platform: 平台标识（bilibili/youtube）

        返回值：
        - VideoProcessResult 处理结果
        """
        video_path: str = ""
        audio_path: str = ""

        try:
            # 1. 下载视频
            print(f"  [{platform}] 正在下载视频: {url[:80]}...")
            video_path = await self._download(url, platform)
            self._temp_files.append(video_path)
            print(f"  [{platform}] 视频下载完成: {os.path.basename(video_path)}")

            # 2. 提取音频
            from audio_utils import extract_audio

            print(f"  [{platform}] 正在提取音频...")
            extraction = await extract_audio(video_path, output_dir=self._temp_dir)
            audio_path = extraction.audio_path
            duration_seconds: float = extraction.duration_seconds
            self._temp_files.append(audio_path)
            print(f"  [{platform}] 音频提取完成，时长: {duration_seconds:.1f}秒")

            # 3. ASR 转写
            from asr_client import transcribe, ASRConfig, get_asr_model_name

            print(f"  [{platform}] 正在进行语音转写...")
            config = self._asr_config or ASRConfig()
            transcript: str = await transcribe(audio_path, config, duration_seconds=duration_seconds)
            print(f"  [{platform}] 转写完成，文本长度: {len(transcript)}字符")

            # 4. 提取视频标题（从文件名中提取）
            title: str = os.path.splitext(os.path.basename(video_path))[0]

            return VideoProcessResult(
                title=title,
                transcript=transcript,
                duration_seconds=duration_seconds,
                platform=platform,
                video_url=url,
                asr_model=get_asr_model_name(config),
                success=True,
            )

        except Exception as exc:
            return VideoProcessResult(
                title="",
                transcript="",
                platform=platform,
                video_url=url,
                success=False,
                error_message=str(exc),
            )

        finally:
            # 清理临时文件
            if self._cleanup_temp:
                self._cleanup_temp_files()

    def _cleanup_temp_files(self) -> None:
        """安全删除所有临时文件"""
        for file_path in self._temp_files:
            self._cleanup_file(file_path)
        self._temp_files.clear()

    @staticmethod
    def _cleanup_file(file_path: str) -> None:
        """
        安全删除单个文件，忽略不存在的错误

        参数说明：
        - file_path: 待删除的文件路径
        """
        try:
            if file_path and os.path.isfile(file_path):
                os.remove(file_path)
        except OSError:
            pass

    async def _download(self, url: str, platform: str) -> str:
        """
        根据平台路由到对应的下载方法

        参数说明：
        - url: 视频 URL
        - platform: 平台标识

        返回值：
        - 下载后的视频文件路径
        """
        # 先尝试从 CDP Proxy 获取浏览器登录态 cookie（B站 412 风控必须）
        # 失败不阻塞——返回 None，降级为匿名下载
        cookie_file: Optional[str] = await self._prepare_cookie_file(platform)
        return await self._download_ytdlp(url, cookie_file=cookie_file)

    # ------------------------------------------------------------------
    # CDP Proxy cookie 获取
    # ------------------------------------------------------------------

    # 平台 → 站点域名映射（用于 CDP Proxy 抓取登录态 cookie）
    # 只列需要登录态才有意义下载的平台；其他平台不抓 cookie 走匿名
    _PLATFORM_DOMAINS: dict[str, str] = {
        "bilibili": "bilibili.com",
        "youtube": "youtube.com",
    }

    async def _prepare_cookie_file(self, platform: str) -> Optional[str]:
        """
        通过 web-access CDP Proxy 获取用户浏览器登录态 cookie，写为 Netscape 格式临时文件

        为什么需要：
        - B站新版风控对未登录请求返回 412 Precondition Failed，必须带登录 cookie
        - YouTube 部分视频需要登录才能下载

        为什么用 document.cookie 而非 CDP Proxy /cookies 端点：
        - CDP Proxy /cookies 调用 Network.getCookies 时未 attach 已加载页面的 session，
          浏览器不返回 cookie（实测返回空数组）
        - document.cookie 能拿到非 HttpOnly 的所有 cookie，对 yt-dlp 足够
          （SESSDATA、bili_jct、DedeUserID 等关键字段都不是 HttpOnly）

        处理流程：
        1. 检查 CDP Proxy 是否就绪（未启动或未连接 → 返回 None 降级匿名下载）
        2. 创建后台 tab 加载站点首页（等浏览器把 cookie 注入 document）
        3. POST /eval 取 document.cookie 字符串
        4. 转 Netscape 格式写临时文件
        5. 关闭 tab

        参数说明：
        - platform: 平台标识（bilibili/youtube）

        返回值：
        - Netscape cookie 文件路径；CDP Proxy 不可用或无 cookie 时返回 None
        """
        domain: str = self._PLATFORM_DOMAINS.get(platform, "")
        if not domain:
            return None

        # 1. 检查 CDP Proxy 就绪
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                resp = await client.get("http://127.0.0.1:3456/health")
                data = resp.json()
        except Exception:
            # CDP Proxy 未启动——不阻塞，降级匿名下载
            return None
        if data.get("status") != "ok" or not data.get("connected"):
            return None

        # 2. 创建 tab 加载站点首页
        site_url: str = f"https://www.{domain}/"
        target_id: str = ""
        try:
            async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                resp = await client.post("http://127.0.0.1:3456/new", content=site_url)
                new_data = resp.json()
            if "targetId" not in new_data:
                return None
            target_id = str(new_data["targetId"])

            # 3. 等 cookie 注入 + eval 取 document.cookie
            # tab 创建后 Proxy 自动等 load 完成，但部分 cookie 是 JS 运行时写入的，多等 1.5s
            await asyncio.sleep(1.5)
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                resp = await client.post(
                    f"http://127.0.0.1:3456/eval?target={target_id}",
                    content="document.cookie",
                )
                eval_data = resp.json()
            cookie_str: str = eval_data.get("value") or ""
            if not cookie_str:
                return None
        finally:
            # 5. 关闭 tab（吞掉异常）
            if target_id:
                try:
                    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                        await client.get(
                            f"http://127.0.0.1:3456/close?target={target_id}"
                        )
                except Exception:
                    pass

        # 4. 转 Netscape 格式临时文件
        # 格式：domain<TAB>flag<TAB>path<TAB>secure<TAB>expiration<TAB>name<TAB>value
        lines: list[str] = ["# Netscape HTTP Cookie File"]
        for kv in cookie_str.split("; "):
            if not kv.strip() or "=" not in kv:
                continue
            name, _, value = kv.partition("=")
            lines.append(
                f".{domain}\tTRUE\t/\tFALSE\t9999999999\t{name}\t{value}"
            )
        if len(lines) <= 1:
            return None

        cookie_file: str = os.path.join(self._temp_dir, f"{platform}_cookies.txt")
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self._temp_files.append(cookie_file)
        print(f"  [{platform}] 已从浏览器获取 {len(lines) - 1} 个 cookie")
        return cookie_file

    async def _download_ytdlp(self, url: str, cookie_file: Optional[str] = None) -> str:
        """
        使用 yt-dlp 下载视频（B站/YouTube）

        处理流程：
        1. 配置 yt-dlp 选项（格式、输出路径、cookie 文件）
        2. 使用 asyncio.to_thread 包装同步调用
        3. 返回下载后的文件路径

        参数说明：
        - url: 视频 URL
        - cookie_file: Netscape 格式 cookie 文件路径（可选，None 时匿名下载）

        返回值：
        - 视频文件路径
        """
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError(
                "未安装 yt-dlp。请执行: pip install yt-dlp"
            ) from exc

        output_template: str = os.path.join(
            self._temp_dir, "%(title).50s.%(ext)s"
        )

        ydl_opts: dict[str, Any] = {
            "format": self._ytdlp_format,
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        def _do_download() -> str:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info: dict[str, Any] = ydl.extract_info(url, download=True)
                filename: str = ydl.prepare_filename(info)
                # yt-dlp 可能改变扩展名
                if not os.path.isfile(filename):
                    base, _ = os.path.splitext(filename)
                    for ext in (".mp4", ".webm", ".mkv", ".avi"):
                        candidate: str = base + ext
                        if os.path.isfile(candidate):
                            return candidate
                return filename

        try:
            result_path: str = await asyncio.wait_for(
                asyncio.to_thread(_do_download),
                timeout=self._ytdlp_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"yt-dlp 下载超时（>{self._ytdlp_timeout}秒）: {url}")

        if not os.path.isfile(result_path):
            raise RuntimeError(f"yt-dlp 下载完成但文件不存在: {result_path}")

        return result_path

    async def _download_file(
        self,
        file_url: str,
        prefix: str = "video",
    ) -> str:
        """
        使用 httpx 下载文件到临时目录

        参数说明：
        - file_url: 文件下载 URL
        - prefix: 临时文件名前缀

        返回值：
        - 下载后的文件路径
        """
        suffix: str = ".mp4"
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=f"{prefix}_", dir=self._temp_dir)
        os.close(fd)

        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers=headers,
        ) as client:
            async with client.stream("GET", file_url) as response:
                response.raise_for_status()
                with open(temp_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

        # 校验文件大小（过小视为无效文件）
        file_size: int = os.path.getsize(temp_path)
        if file_size < 20480:  # 小于 20KB 视为无效
            self._cleanup_file(temp_path)
            raise RuntimeError(
                f"下载的视频文件过小（{file_size}字节），可能无效。"
            )

        return temp_path
