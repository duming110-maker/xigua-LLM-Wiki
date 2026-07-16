---
name: material-collector
description: 多平台素材抓取器，把 URL 链接（公众号 mp.weixin.qq.com、GitHub github.com、B站 bilibili.com 等）批量抓取并转成 Markdown 文本，视频自动转文字（ASR）。当用户提供任意平台链接要求抓取/下载/转文字/提取内容时，必须调用此 Skill。触发词：抓取、下载链接、转文字、提取内容、采集素材、收集素材、抓网页、ASR。
---

> `{skill_dir}` = 本 SKILL.md 所在目录

# 素材抓取器（material-collector）

## 依赖自动安装

本 Skill 依赖多个 Python 包和外部工具。在首次使用或遇到 `ModuleNotFoundError` / `ImportError` 时，自动执行以下命令安装：

```bash
pip install -r {skill_dir}/requirements.txt
```

安装完成后重新执行原始命令即可。

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | 是 | 阿里 DashScope API Key（远程 ASR 模式） |

### 外部工具

- **ffmpeg** — 用于音频提取与 ASR 解码。自动探测可用 ffmpeg（验证含 aac 解码器，自动跳过 Trae 等工具注入的残废裁剪版），通常无需手动配置。也可设环境变量 `FFMPEG_BIN` 显式指定完整版 ffmpeg.exe。
- **web-access CDP Proxy** — 抓取 GitHub 等重度 SPA 平台时必需。通过 CDP 直连用户日常浏览器（携带登录态）。启动命令：`node <web-access skill>/scripts/check-deps.mjs`

## 执行流程

当用户提供一组链接要求收集素材时，按以下步骤执行：

### Step 1: 调用收集器脚本

使用 `collector.py` 处理用户提供的链接：

```bash
python {skill_dir}/scripts/collector.py --text "用户输入的包含多个链接的原始文本" --config {skill_dir}/config.yaml
```

支持的参数：
- `--url "链接"` — 指定单个链接（可多次使用）
- `--text "文本"` — 传入原始文本（自动提取 URL）
- `--file 文件路径` — 从文件读取 URL 列表
- `--name "名称"` — 自定义批次文件夹名称
- `--config 路径` — 指定配置文件路径
- `--output 路径` — 素材输出根目录（覆盖配置文件中的 output_dir）。llm-wiki 调用时使用 `--output wiki/sources` 将素材输出到知识库

### Step 2: 查看结果并告知用户

脚本依次处理每个链接，单个链接失败不会中断整个批次。视频处理较慢（下载+音频+ASR），单个视频约需 1-3 分钟，必要时提前告知用户。

处理完成后，素材保存在批次文件夹中：

```
material/
└── batch_20260428_143052/    ← 批次文件夹
    ├── 001.md                ← 第一个素材
    ├── 002.md                ← 第二个素材
    ├── 003.md                ← ...
    └── _index.md             ← 批次索引（素材清单）
```

读取批次 `_index.md`，将路径与素材清单告知用户，便于后续写作时引用。

## 平台识别规则

| 平台 | URL 特征 | 处理方式 |
|------|---------|---------|
| B站 | `bilibili.com/video/*` | yt-dlp 下载 → 音频提取 → ASR 转写 |
| GitHub | `github.com/*` | web-access CDP Proxy 真实浏览器渲染 → 提取 README 正文 → Markdown |
| 公众号 | `mp.weixin.qq.com/*` | httpx 抓取 → HTML 解析 → Markdown |
| 网页 | 其他 HTTP URL | httpx 抓取 → HTML 解析 → Markdown |

各平台详细链路、前置条件、已知限制见 `{skill_dir}/references/supported_platforms.md`。

### 不支持的平台

| 平台 | URL 特征 | 处理方式 |
|------|---------|---------|
| 抖音 | `douyin.com` / `iesdouyin.com` / `v.douyin.com` | **直接回复不支持抖音平台抓取**，不调用 collector |

## 输出格式

每个素材文件为统一格式的 Markdown：

```markdown
---
source_url: "原始链接"
platform: "平台标识"
title: "素材标题"
author: "作者"
publish_date: "发布日期"
collected_at: "采集时间"
content_type: "video_transcript|article|webpage"
duration_seconds: 120
asr_model: "qwen3-asr-flash"
---

# 标题

> 来源：平台名 | 作者：xxx | 发布日期：xxx
> 链接：https://xxx

正文内容...
```

## 异常处理

- **视频下载失败**: 跳过该链接，在索引文件中标注失败原因，继续处理下一个
- **ASR 转写失败**: 自动重试 3 次（指数退避），仍失败则跳过
- **文章被反爬**: 在索引文件中标注"被反爬拦截"，建议用户更换网络
- **ffmpeg 未安装**: 明确提示安装方法，终止视频处理（不影响文章抓取）
