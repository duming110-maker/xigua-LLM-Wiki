import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from asr_client import ASRConfig, WhisperConfig, transcribe

AUDIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_audio.mp3")


async def main():
    if not os.path.isfile(AUDIO_FILE):
        print(f"音频文件不存在: {AUDIO_FILE}")
        return

    config = ASRConfig(
        mode="local",
        whisper=WhisperConfig(
            model="turbo",
            device="cuda",
            language="zh",
            download_root="",
        ),
    )

    print(f"开始转写: {os.path.basename(AUDIO_FILE)}")
    text = await transcribe(AUDIO_FILE, config=config)
    print(f"\n{'='*60}")
    print("转写结果:")
    print(f"{'='*60}")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
