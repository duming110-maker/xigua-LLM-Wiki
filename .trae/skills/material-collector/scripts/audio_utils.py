"""
音频工具模块 —— 封装 ffmpeg / ffprobe 命令行调用。

本模块完全独立，不导入任何宿主项目代码（如 app.*），仅依赖 Python 标准库。
提供以下能力：
  - 检查 ffmpeg 是否可用
  - 从视频文件中提取音频（wav 格式，PCM 16kHz 单声道）
  - 将长音频按指定时长分段

变更记录：
  - 2026-04-28 | AI | 新增音频工具模块
  - 2026-06-19 | AI | 音频提取 mp3(libmp3lame) → wav(pcm_s16le 16kHz mono)，不依赖 libmp3lame 编码器
  - 2026-06-19 | AI | check_ffmpeg 主动探测可用 ffmpeg（FFMPEG_BIN→常见路径→PATH，验证 aac 解码器），跳过 Trae 等注入的残废版（零音频解码器）；新增 check_ffprobe，_probe_duration 改用它
"""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# ffmpeg / ffprobe 子进程超时秒数
_DEFAULT_TIMEOUT: int = 120


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioExtraction:
    """音频提取结果。

    Attributes:
        audio_path: 提取后的音频文件绝对路径。
        duration_seconds: 音频总时长（秒），由 ffprobe 获取。
    """

    audio_path: str
    duration_seconds: float


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


# 模块级缓存：check_ffmpeg / check_ffprobe 探测一次就复用，避免每次都跑 ffmpeg -decoders
_CACHED_FFMPEG: str | None = None
_CACHED_FFPROBE: str | None = None


def _has_aac_decoder(ffmpeg_path: str) -> bool:
    """检查指定 ffmpeg 是否能解码 aac（提取视频音轨的刚需）。

    用途：Trae 等工具会注入用 --disable-everything 编译的残废 ffmpeg（零音频解码器），
    必须识别出来并跳过。完整版 ffmpeg 的 -decoders 输出含 aac 行，残废版完全没有。

    Args:
        ffmpeg_path: ffmpeg 可执行文件路径。

    Returns:
        bool: 能解码 aac 返回 True；查询失败/超时保守返回 False（视为不可用）。
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-decoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "aac" in result.stdout
    except Exception:
        return False


def _collect_ffmpeg_candidates() -> list[str]:
    """收集所有可能的 ffmpeg 候选路径（去重、保序、均已确认文件存在）。

    优先级（先排最可能可用的）：
      1. 环境变量 FFMPEG_BIN（显式指定，最高优先）；
      2. Windows 常见完整版安装路径（Program Files 下的 ffmpeg*，Trae 不会装这）；
      3. PATH 里的所有 ffmpeg（where 取全部，含 Trae 注入的——会被 aac 验证过滤掉）。
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(path: str | None) -> None:
        if not path:
            return
        path = path.strip().strip('"')
        if path and path not in seen and os.path.isfile(path):
            candidates.append(path)
            seen.add(path)

    # 1. 环境变量显式指定
    _add(os.environ.get("FFMPEG_BIN"))

    # 2. Windows 常见完整版安装路径（C/D/E 盘 Program Files 下的 ffmpeg*）
    if sys.platform == "win32":
        for pattern in (
            "/c/Program Files*/ffmpeg*/bin/ffmpeg.exe",
            "/d/Program Files*/ffmpeg*/bin/ffmpeg.exe",
            "/e/Program Files*/ffmpeg*/bin/ffmpeg.exe",
        ):
            for found in glob.glob(pattern):
                _add(found)

    # 3. PATH 里的所有 ffmpeg（shutil.which 只返回第一个，补 where 取全部）
    _add(shutil.which("ffmpeg"))
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["where", "ffmpeg"], capture_output=True, text=True, timeout=5
            )
            for line in res.stdout.splitlines():
                _add(line)
        except Exception:
            pass

    return candidates


def _ensure_ffmpeg_in_path(ffmpeg_path: str) -> None:
    """把完整版 ffmpeg 所在目录注入 PATH 最前。

    背景：material-collector 自己用 check_ffmpeg() 返回的绝对路径调 ffmpeg 没问题，
    但 whisper.load_audio 等第三方库内部用裸 'ffmpeg'（靠 PATH 解析）。若不注入，
    Trae 注入的残废 ffmpeg 会拦截这些第三方调用。把完整版目录前置到 PATH 即统一解决。

    幂等：PATH 最前已是该目录则不动。
    """
    ff_dir: str = os.path.dirname(ffmpeg_path)
    if not ff_dir:
        return
    path_parts: list[str] = os.environ.get("PATH", "").split(os.pathsep)
    if path_parts and os.path.normpath(path_parts[0]) == os.path.normpath(ff_dir):
        return
    os.environ["PATH"] = ff_dir + os.pathsep + os.environ.get("PATH", "")


def check_ffmpeg() -> str:
    """返回可用的完整版 ffmpeg 路径（能解码 aac），自动跳过 Trae 等残废版。

    解析顺序：
      1. 命中缓存直接返回；
      2. 遍历候选（FFMPEG_BIN → 常见安装路径 → PATH 全部），逐个验证 aac 解码器，
         用第一个能解 aac 的；
      3. 都不能解 aac → 抛错并列出已检查的候选。

    这样即便 Trae 把残废 ffmpeg 注入 PATH 最前面，也能自动找到系统完整版，
    对任何 agent / 环境透明、零配置。

    Returns:
        str: 可用的 ffmpeg 可执行文件绝对路径。

    Raises:
        RuntimeError: 找不到任何能解 aac 的 ffmpeg 时抛出。
    """
    global _CACHED_FFMPEG
    if _CACHED_FFMPEG:
        return _CACHED_FFMPEG

    candidates: list[str] = _collect_ffmpeg_candidates()
    for path in candidates:
        if _has_aac_decoder(path):
            _CACHED_FFMPEG = path
            _ensure_ffmpeg_in_path(path)  # 注入 PATH 最前，让 whisper 等第三方库内部调 ffmpeg 也命中完整版
            return path

    if not candidates:
        raise RuntimeError(
            "未找到 ffmpeg。请安装完整版 ffmpeg，或设环境变量 FFMPEG_BIN 指向 ffmpeg.exe。"
        )
    raise RuntimeError(
        "找到的 ffmpeg 都不能解码 aac 音频（可能是 Trae 等工具注入的裁剪版，"
        "用 --disable-everything 编译、零音频解码器）。\n"
        f"  已检查 {len(candidates)} 个候选：{candidates}\n"
        "  解决：安装完整版 ffmpeg（含 aac 解码器），或设环境变量 FFMPEG_BIN 指向完整版 ffmpeg.exe。"
    )


def check_ffprobe() -> str:
    """返回 ffprobe 路径，优先用与已选 ffmpeg 同目录的完整版（而非 Trae 的残废 ffprobe）。

    解析顺序：
      1. 命中缓存直接返回；
      2. 环境变量 FFPROBE_BIN；
      3. 已选 ffmpeg（check_ffmpeg()）同目录下的 ffprobe；
      4. PATH 里的 ffprobe。

    Raises:
        RuntimeError: 都找不到时抛出。
    """
    global _CACHED_FFPROBE
    if _CACHED_FFPROBE:
        return _CACHED_FFPROBE

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(path: str | None) -> None:
        if not path:
            return
        path = path.strip().strip('"')
        if path and path not in seen and os.path.isfile(path):
            candidates.append(path)
            seen.add(path)

    _add(os.environ.get("FFPROBE_BIN"))
    # 与已选 ffmpeg 同目录（确保 ffprobe 也是完整版，而非 Trae 的）
    try:
        ff_dir: str = os.path.dirname(check_ffmpeg())
        _add(os.path.join(ff_dir, "ffprobe.exe"))
        _add(os.path.join(ff_dir, "ffprobe"))
    except RuntimeError:
        pass
    _add(shutil.which("ffprobe"))

    if not candidates:
        raise RuntimeError(
            "未找到 ffprobe。请安装完整版 ffmpeg（含 ffprobe），或设 FFPROBE_BIN。"
        )
    _CACHED_FFPROBE = candidates[0]
    return candidates[0]


async def extract_audio(
    video_path: str,
    output_dir: str | None = None,
) -> AudioExtraction:
    """从视频文件中提取音频，输出为 wav（PCM 16kHz 单声道），并获取音频时长。

    为什么用 wav 而非 mp3：pcm_s16le 是 ffmpeg 内置编码器，任何 ffmpeg build
    （包括没编译 libmp3lame 的精简版）都能输出，避免「精简版 ffmpeg 提取 mp3 失败」。
    16kHz 单声道也是 Whisper 的推荐输入格式，省去下游重采样。

    调用链路：
      1. 使用 ffprobe 获取视频文件中的音频时长。
      2. 使用 ffmpeg 提取音频轨道，编码为 wav(pcm_s16le)。

    Args:
        video_path: 视频文件的绝对路径。
        output_dir:  音频输出目录，为 None 时使用视频文件所在目录。

    Returns:
        AudioExtraction: 包含音频文件路径和时长（秒）的数据对象。

    Raises:
        FileNotFoundError: 视频文件不存在时抛出。
        RuntimeError:       ffmpeg / ffprobe 执行失败或超时时抛出。
    """
    # ---- 参数校验 ----
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    # 确保 ffmpeg 可用
    check_ffmpeg()

    # 确定输出目录与输出文件名
    resolved_output_dir: str = output_dir if output_dir is not None else os.path.dirname(video_path)
    os.makedirs(resolved_output_dir, exist_ok=True)

    # 输出文件名：与视频同名，扩展名为 .wav（pcm，任何 ffmpeg 都能输出）
    video_basename: str = os.path.splitext(os.path.basename(video_path))[0]
    audio_output_path: str = os.path.join(resolved_output_dir, f"{video_basename}.wav")

    # ---- 1. 使用 ffprobe 获取音频时长 ----
    duration_seconds: float = await _probe_duration(video_path)

    # ---- 2. 使用 ffmpeg 提取音频 ----
    # 命令：ffmpeg -i input -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav -y
    # pcm_s16le 是 ffmpeg 内置编码器，精简版（无 libmp3lame）也能输出；
    # 16kHz 单声道是 Whisper 推荐输入，省下游重采样。
    ffmpeg_bin: str = check_ffmpeg()
    extract_cmd: list[str] = [
        ffmpeg_bin,
        "-i", video_path,
        "-vn",                    # 丢弃视频轨道
        "-acodec", "pcm_s16le",  # PCM 16bit（内置编码器，不依赖 libmp3lame）
        "-ar", "16000",          # 采样率 16kHz（Whisper 推荐）
        "-ac", "1",              # 单声道（语音识别足够，体积减半）
        audio_output_path,
        "-y",                    # 覆盖已存在的文件
    ]

    await _run_subprocess(extract_cmd, label="音频提取", timeout=_DEFAULT_TIMEOUT)

    # 二次确认输出文件存在
    if not os.path.isfile(audio_output_path):
        raise RuntimeError(f"音频提取完成但输出文件不存在: {audio_output_path}")

    return AudioExtraction(audio_path=audio_output_path, duration_seconds=duration_seconds)


async def split_audio(
    file_path: str,
    segment_seconds: int = 240,
    output_dir: str | None = None,
) -> list[str]:
    """将长音频按指定秒数分段。

    使用 ffmpeg 的 segment 分片功能，直接拷贝流（无需重编码），
    分段点可能略有不精确（取决于关键帧位置）。

    Args:
        file_path:       音频文件的绝对路径。
        segment_seconds: 每段时长（秒），默认 240 秒（4 分钟）。
        output_dir:      分段文件输出目录，为 None 时自动创建临时目录。

    Returns:
        list[str]: 分段后的文件绝对路径列表（按文件名排序）。

    Raises:
        FileNotFoundError: 音频文件不存在时抛出。
        RuntimeError:       ffmpeg 执行失败或超时时抛出。
    """
    # ---- 参数校验 ----
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    # 确保 ffmpeg 可用
    check_ffmpeg()

    # 确定输出目录
    resolved_output_dir: str
    if output_dir is not None:
        resolved_output_dir = output_dir
    else:
        resolved_output_dir = tempfile.mkdtemp(prefix="audio_split_")
    os.makedirs(resolved_output_dir, exist_ok=True)

    # 分段文件名模板：原文件名_段序号.原扩展名
    audio_basename: str = os.path.splitext(os.path.basename(file_path))[0]
    audio_ext: str = os.path.splitext(file_path)[1]  # 包含前导点号，如 ".mp3"
    segment_pattern: str = os.path.join(resolved_output_dir, f"{audio_basename}_%03d{audio_ext}")

    # 命令：ffmpeg -i input -f segment -segment_time N -c copy -reset_timestamps 1 -y output_pattern
    ffmpeg_bin: str = check_ffmpeg()
    split_cmd: list[str] = [
        ffmpeg_bin,
        "-i", file_path,
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-c", "copy",              # 流拷贝，不重编码
        "-reset_timestamps", "1",  # 每段时间戳从 0 开始
        "-y",
        segment_pattern,
    ]

    await _run_subprocess(split_cmd, label="音频分段", timeout=_DEFAULT_TIMEOUT)

    # 收集分段文件并排序
    segment_files: list[str] = sorted(
        os.path.join(resolved_output_dir, f_name)
        for f_name in os.listdir(resolved_output_dir)
        if f_name.startswith(audio_basename) and f_name.endswith(audio_ext)
    )

    if not segment_files:
        raise RuntimeError(f"音频分段完成但未生成任何分段文件，输出目录: {resolved_output_dir}")

    return segment_files


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


async def _probe_duration(file_path: str) -> float:
    """使用 ffprobe 获取媒体文件的时长。

    Args:
        file_path: 媒体文件绝对路径。

    Returns:
        float: 时长（秒）。

    Raises:
        RuntimeError: ffprobe 执行失败、超时或返回结果无法解析时抛出。
    """
    # 命令：ffprobe -v error -show_entries format=duration -of csv=p=0 input
    probe_cmd: list[str] = [
        check_ffprobe(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        file_path,
    ]

    stdout_data: str = await _run_subprocess(probe_cmd, label="时长探测", timeout=_DEFAULT_TIMEOUT)

    # 解析时长（ffprobe 输出可能包含尾部换行或空行）
    cleaned: str = stdout_data.strip()
    if not cleaned:
        raise RuntimeError(f"ffprobe 未返回时长信息，文件: {file_path}")

    try:
        return float(cleaned)
    except ValueError as exc:
        raise RuntimeError(
            f"无法解析 ffprobe 返回的时长: '{cleaned}'，文件: {file_path}"
        ) from exc


async def _run_subprocess(
    cmd: list[str],
    *,
    label: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """异步执行子进程并等待完成，捕获 stdout/stderr。

    Args:
        cmd:     命令与参数列表。
        label:   用于日志/错误提示的可读标签（如"音频提取"）。
        timeout: 超时秒数。

    Returns:
        str: 子进程的标准输出内容（已解码为 UTF-8）。

    Raises:
        RuntimeError: 子进程返回非零退出码或超时时抛出。
    """
    process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes: bytes
        stderr_bytes: bytes
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        # 超时后强制终止子进程
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"{label}超时（>{timeout}秒），命令: {' '.join(cmd)}"
        ) from None

    # 解码输出
    stdout_text: str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text: str = stderr_bytes.decode("utf-8", errors="replace")

    # 检查退出码
    if process.returncode != 0:
        raise RuntimeError(
            f"{label}失败（退出码={process.returncode}），命令: {' '.join(cmd)}"
            f"\n  stderr: {stderr_text[:2000]}"
        )

    return stdout_text
