"""
ASR 客户端模块

职责：
- 提供统一的 ASR 转写接口
- 支持两种模式：
  - local（默认）：使用本地 Whisper 模型进行语音转文本
  - remote：调用阿里 DashScope qwen3-asr-flash 进行语音转文本

技术栈：
- whisper（本地模式）
- dashscope SDK（远程模式）
- asyncio（异步包装同步调用）

依赖范围：
    完全独立，不导入任何宿主项目代码（app.* 等）。
    远程模式需要同目录下的 audio_utils.py 提供分段能力。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WhisperConfig:
    """Whisper 本地模型配置。

    属性说明：
    - model: Whisper 模型名称（turbo/base/small/medium/large）
    - device: 推理设备（cuda/cpu）
    - language: 转写语言代码
    - download_root: 模型下载根目录，默认为 ~/.cache/whisper
    """
    model: str = "turbo"
    device: str = "cuda"
    language: str = "zh"
    download_root: str = ""


@dataclass(frozen=True)
class ASRConfig:
    """ASR 配置数据类。

    属性说明：
    - mode: 转写模式，"local" 使用 Whisper，"remote" 使用 DashScope
    - model_id: 远程模式 - 短音频转写模型 ID
    - filetrans_model_id: 远程模式 - 长音频转写模型 ID
    - max_attempts: 远程模式 - 最大重试次数
    - segment_seconds: 远程模式 - 长音频分段时长（秒）
    - whisper: Whisper 本地模型配置
    """
    mode: str = "local"
    model_id: str = "qwen3-asr-flash"
    filetrans_model_id: str = "qwen3-asr-flash-filetrans"
    max_attempts: int = 3
    segment_seconds: int = 240
    whisper: WhisperConfig = None

    def __post_init__(self):
        if self.whisper is None:
            object.__setattr__(self, "whisper", WhisperConfig())


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


async def transcribe(
    file_path: str,
    config: ASRConfig | None = None,
    duration_seconds: float | None = None,
) -> str:
    """
    使用 ASR 模型将本地音频文件转为文本

    参数说明：
    - file_path: 本地音频文件绝对路径
    - config: ASR 配置，为 None 时使用默认配置
    - duration_seconds: 音频时长（秒），为 None 时自动探测

    返回值：
    - 转写文本字符串

    异常：
    - FileNotFoundError: 音频文件不存在
    - ValueError: 配置错误
    - RuntimeError: ASR 调用失败
    """
    if config is None:
        config = ASRConfig()

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    if config.mode == "local":
        return await _transcribe_whisper(file_path, config.whisper)
    elif config.mode == "remote":
        return await _transcribe_remote(file_path, config, duration_seconds)
    else:
        raise ValueError(f"不支持的 ASR 模式: {config.mode}，可选值: local, remote")


def get_asr_model_name(config: ASRConfig | None = None) -> str:
    """获取当前 ASR 配置对应的模型名称标识。

    参数说明：
    - config: ASR 配置

    返回值：
    - 模型名称字符串
    """
    if config is None:
        config = ASRConfig()
    if config.mode == "local":
        return f"whisper-{config.whisper.model}"
    return config.model_id


# ---------------------------------------------------------------------------
# 本地模式：Whisper
# ---------------------------------------------------------------------------


def _format_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _transcribe_with_progress(model, file_path: str, language: str, fp16: bool, audio_duration: float) -> dict:
    import sys
    import time as _time

    start_time = _time.monotonic()
    segments_result = []
    current_pos = 0.0

    def on_segment(segment: dict):
        nonlocal current_pos
        current_pos = segment.get("end", 0.0)
        elapsed = _time.monotonic() - start_time
        if audio_duration > 0:
            pct = min(current_pos / audio_duration * 100, 100.0)
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "=" * filled + "-" * (bar_len - filled)
            sys.stderr.write(
                f"\r  [Whisper] [{bar}] {pct:5.1f}% | "
                f"{_format_elapsed(current_pos)}/{_format_elapsed(audio_duration)} | "
                f"elapsed {_format_elapsed(elapsed)}"
            )
            sys.stderr.flush()
        segments_result.append(segment)

    result_iter = model.transcribe(
        file_path,
        language=language,
        fp16=fp16,
        verbose=False,
    )

    for segment in result_iter.get("segments", []):
        on_segment(segment)

    elapsed = _time.monotonic() - start_time
    if audio_duration > 0:
        sys.stderr.write(
            f"\r  [Whisper] [{'=' * 30}] 100.0% | "
            f"{_format_elapsed(audio_duration)}/{_format_elapsed(audio_duration)} | "
            f"elapsed {_format_elapsed(elapsed)}\n"
        )
        sys.stderr.flush()
    else:
        sys.stderr.write(f"\r  [Whisper] done, elapsed {_format_elapsed(elapsed)}\n")
        sys.stderr.flush()

    return result_iter


async def _transcribe_whisper(
    file_path: str,
    whisper_config: WhisperConfig,
) -> str:
    """
    使用本地 Whisper 模型进行语音转文本

    参数说明：
    - file_path: 音频文件路径
    - whisper_config: Whisper 配置

    返回值：
    - 转写文本
    """
    try:
        import whisper
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "未安装 openai-whisper。请执行: pip install openai-whisper"
        ) from exc

    download_root: str = whisper_config.download_root
    if download_root:
        os.makedirs(download_root, exist_ok=True)

    device = whisper_config.device
    if device == "cuda" and not torch.cuda.is_available():
        print(f"  [Whisper] WARNING: CUDA 不可用, 回退为 CPU")
        device = "cpu"

    print(f"  [Whisper] loading model {whisper_config.model} on {device}...")

    model = await asyncio.to_thread(
        whisper.load_model,
        whisper_config.model,
        device=device,
        download_root=download_root if download_root else None,
    )

    audio_duration = await _probe_duration(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    dur_str = _format_elapsed(audio_duration) if audio_duration > 0 else "unknown"
    print(f"  [Whisper] audio: {file_size_mb:.1f}MB, duration: {dur_str}, transcribing on {device}...")

    result = await asyncio.to_thread(
        _transcribe_with_progress,
        model, file_path, whisper_config.language,
        fp16=(device != "cpu"),
        audio_duration=audio_duration,
    )

    text = result.get("text", "").strip()
    segments = result.get("segments", [])
    print(f"  [Whisper] done: {len(segments)} segments, {len(text)} chars")

    return text


# ---------------------------------------------------------------------------
# 远程模式：DashScope（原有逻辑）
# ---------------------------------------------------------------------------

_RETRY_MARKERS: tuple[str, ...] = (
    "SSLError",
    "SSL:",
    "UNEXPECTED_EOF_WHILE_READING",
    "Max retries exceeded",
    "Connection reset",
    "Connection aborted",
    "Read timed out",
    "timed out",
    "Temporary failure",
    "502",
    "503",
    "504",
)

_SHORT_AUDIO_THRESHOLD: float = 300.0


async def _transcribe_remote(
    file_path: str,
    config: ASRConfig,
    duration_seconds: float | None,
) -> str:
    """
    使用阿里 DashScope ASR 进行语音转文本

    参数说明：
    - file_path: 音频文件路径
    - config: ASR 配置
    - duration_seconds: 音频时长（秒）

    返回值：
    - 转写文本
    """
    import dashscope
    from dashscope import MultiModalConversation

    api_key: str | None = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "未配置 DASHSCOPE_API_KEY 环境变量。"
            "请在环境变量中设置阿里 DashScope API Key。"
        )
    dashscope.api_key = api_key

    if duration_seconds is None:
        duration_seconds = await _probe_duration(file_path)

    use_segmented: bool = duration_seconds >= _SHORT_AUDIO_THRESHOLD

    last_exc: Exception | None = None
    for attempt in range(config.max_attempts):
        try:
            if use_segmented:
                text: str = await _transcribe_segmented(file_path, config)
            else:
                text = await _transcribe_direct(file_path, config.model_id, MultiModalConversation)
            return text
        except Exception as exc:
            last_exc = exc
            if attempt < config.max_attempts - 1 and _should_retry(exc):
                wait_seconds: float = 1.0 * (2 ** attempt)
                await asyncio.sleep(wait_seconds)
                continue

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("ASR 转写失败，原因未知")


async def _transcribe_direct(file_path: str, model_id: str, MultiModalConversation) -> str:
    """
    短音频直接转写（使用 MultiModalConversation.call）

    参数说明：
    - file_path: 音频文件路径
    - model_id: 模型 ID
    - MultiModalConversation: dashscope MultiModalConversation 类

    返回值：
    - 转写文本
    """
    messages: list[dict] = [
        {
            "role": "system",
            "content": [{"text": "请返回带有时间戳的文本."}],
        },
        {
            "role": "user",
            "content": [{"audio": file_path}],
        },
    ]

    asr_options: dict[str, object] = {"enable_itn": False}

    response = await asyncio.to_thread(
        MultiModalConversation.call,
        model=model_id,
        messages=messages,
        result_format="message",
        asr_options=asr_options,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"DashScope ASR 错误: {response.code} - {response.message}"
        )

    if not response.output or not response.output.choices:
        return ""

    content = response.output.choices[0].message.content

    if isinstance(content, list):
        text_parts: list[str] = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and "text" in item
        ]
        return "".join(text_parts)

    if isinstance(content, str):
        return content

    return str(content)


async def _transcribe_segmented(file_path: str, config: ASRConfig) -> str:
    """
    长音频分段转写

    参数说明：
    - file_path: 音频文件路径
    - config: ASR 配置

    返回值：
    - 完整转写文本
    """
    from audio_utils import split_audio

    flash_model: str = config.filetrans_model_id.replace("-filetrans", "")

    segments: list[str] = await split_audio(
        file_path,
        segment_seconds=config.segment_seconds,
    )

    segment_dir: str = os.path.dirname(segments[0]) if segments else ""

    all_text: list[str] = []
    try:
        for i, seg_path in enumerate(segments):
            seg_size_mb: float = os.path.getsize(seg_path) / (1024 * 1024)
            print(f"  转写分段 {i + 1}/{len(segments)}: {os.path.basename(seg_path)} ({seg_size_mb:.1f}MB)")

            try:
                import dashscope
                from dashscope import MultiModalConversation
                seg_text: str = await _transcribe_direct(seg_path, flash_model, MultiModalConversation)
                all_text.append(seg_text)
            except Exception as exc:
                print(f"  警告: 分段 {i + 1} 转写失败: {exc}")
    finally:
        if segment_dir:
            if os.path.basename(segment_dir).startswith("audio_split_"):
                shutil.rmtree(segment_dir, ignore_errors=True)

    full_text: str = "".join(all_text)
    if not full_text:
        raise RuntimeError(f"所有分段转写均失败（共 {len(segments)} 段）")

    return full_text


async def _probe_duration(file_path: str) -> float:
    """
    使用 ffprobe 探测音频时长

    参数说明：
    - file_path: 音频文件路径

    返回值：
    - 时长（秒）
    """
    cmd: list[str] = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        file_path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=30)

    if process.returncode != 0:
        return 0.0

    output: str = stdout_bytes.decode("utf-8", errors="replace").strip()
    if not output:
        return 0.0

    try:
        return float(output)
    except ValueError:
        return 0.0


def _should_retry(error: Exception) -> bool:
    """
    判断异常是否可安全重试

    参数说明：
    - error: 捕获的异常

    返回值：
    - True 表示可重试
    """
    msg: str = str(error)
    return any(marker in msg for marker in _RETRY_MARKERS)
