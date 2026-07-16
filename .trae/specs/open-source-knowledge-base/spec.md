# 通用知识库开源改造 Spec

## Why

当前项目是从内容创作项目复制而来，包含大量个人内容创作相关的 skill 路由和非合规的抖音下载功能。需要将其改造为一个通用的、可开源的知识库项目，让任何人都能基于此搭建自己的 AI 辅助知识库。

## What Changes

- **移除抖音下载功能**：抖音下载不合规，需从代码、配置、文档中彻底清除（含 cookie 机制、playwright/cdp 双后端、cdp_downloader 模块）
- **删除 `.claude/` 重复目录**：只保留 `.trae/skills/`，避免两份 skill 维护负担
- **重写 CLAUDE.md**：移除不存在的内容创作 skill 路由（imitation-writer、writing-workflow、guizang-ppt-skill、screencast-script、douyin-writer 等），重新定位为通用知识库
- **清理 web-access skill 中的抖音引用**：CDP proxy 文档和脚本中涉及抖音的部分
- **新增开源必备文件**：LICENSE（MIT）、README.md（项目说明与快速上手）
- **清理个人配置数据**：config.yaml 中的个人路径（E:/Whisper）、create_traeshort.ps1 等个人脚本
- **保留现有能力**：微信公众号、B站、YouTube、X/Twitter、GitHub、通用网页抓取；本地 Whisper + 线上 DashScope ASR；wiki 知识库管理

## Impact

- Affected specs: material-collector、llm-wiki、web-access
- Affected code:
  - [.trae/skills/material-collector/scripts/video_processor.py](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/scripts/video_processor.py) — 移除全部抖音下载逻辑
  - [.trae/skills/material-collector/scripts/url_parser.py](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/scripts/url_parser.py) — 移除 DOUYIN 枚举与识别
  - [.trae/skills/material-collector/scripts/collector.py](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/scripts/collector.py) — 移除 douyin 平台标识与配置
  - [.trae/skills/material-collector/scripts/cdp_downloader.py](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/scripts/cdp_downloader.py) — 删除整个文件
  - [.trae/skills/material-collector/config.yaml](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/config.yaml) — 移除 douyin/cdp 段
  - [.trae/skills/material-collector/SKILL.md](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/SKILL.md) — 移除抖音相关文档
  - [.trae/skills/material-collector/references/supported_platforms.md](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/references/supported_platforms.md) — 移除抖音平台说明
  - [.trae/skills/material-collector/.cookies/](file:///d:/test-pro/xigua-llm/.trae/skills/material-collector/.cookies/) — 删除整个目录
  - [.trae/skills/web-access/](file:///d:/test-pro/xigua-llm/.trae/skills/web-access/) — 清理抖音引用
  - [CLAUDE.md](file:///d:/test-pro/xigua-llm/CLAUDE.md) — 全面重写
  - [.gitignore](file:///d:/test-pro/xigua-llm/.gitignore) — 补充敏感文件排除
  - `.claude/` — 删除整个目录

## ADDED Requirements

### Requirement: 开源项目基础文件

项目 SHALL 包含开源所需的基础文件，使任何人能理解并合法使用本项目。

#### Scenario: 开发者首次接触项目
- **WHEN** 开发者克隆仓库
- **THEN** 根目录存在 LICENSE 文件（MIT 协议）
- **AND** 根目录存在 README.md，包含项目简介、核心能力、目录结构、快速上手、依赖安装说明

### Requirement: 通用知识库定位

项目 SHALL 定位为通用 AI 辅助知识库，不绑定特定个人或内容创作场景。

#### Scenario: 用户阅读项目说明
- **WHEN** 用户阅读 CLAUDE.md 和 README.md
- **THEN** 项目定位明确为「通用知识库」，不出现内容创作、仿写、口播等个人场景路由
- **AND** skill 路由只引用实际存在的 skill（material-collector、llm-wiki、web-access）

## MODIFIED Requirements

### Requirement: 素材抓取器（material-collector）

素材抓取器 SHALL 支持以下平台的 URL 抓取与转写，不再包含抖音：

| 平台 | URL 特征 | 处理方式 |
|------|---------|---------|
| B站 | `bilibili.com/video/*` | yt-dlp 下载 → 音频提取 → ASR 转写 |
| YouTube | `youtube.com/watch*` 或 `youtube.com/shorts/*` | yt-dlp 下载 → 音频提取 → ASR 转写 |
| DeepLearning.AI | `learn.deeplearning.ai/courses/*` | 页面解析 → 视频下载 → 音频提取 → ASR → LLM 翻译 |
| GitHub | `github.com/*` | Playwright 浏览器渲染 → 提取 README → Markdown |
| X/Twitter | `x.com/*` 或 `twitter.com/*` | Playwright 浏览器渲染 → 提取推文 → Markdown |
| 微信公众号 | `mp.weixin.qq.com/*` | httpx 抓取 → HTML 解析 → Markdown |
| 通用网页 | 其他 HTTP URL | httpx 抓取 → HTML 解析 → Markdown |

#### Scenario: 用户抓取抖音链接
- **WHEN** 用户提供 `v.douyin.com/*` 或 `douyin.com/video/*` 链接
- **THEN** 系统不识别为抖音平台，按通用网页处理（httpx 抓取）
- **AND** 不触发任何抖音专用下载逻辑

#### Scenario: ASR 语音转写
- **WHEN** 用户抓取视频类链接（B站/YouTube/DeepLearning.AI）
- **THEN** 系统支持本地 Whisper 和线上 DashScope 两种 ASR 模式
- **AND** 通过 config.yaml 的 `asr.mode` 切换

### Requirement: CLAUDE.md 项目路由

CLAUDE.md SHALL 只引用项目中实际存在的 skill，路由表精简为知识库相关操作。

#### Scenario: 用户操作知识库
- **WHEN** 用户想采集素材、管理 wiki、或访问网页
- **THEN** CLAUDE.md 路由表指向 material-collector、llm-wiki、web-access 三个实际存在的 skill
- **AND** 不出现 imitation-writer、writing-workflow、guizang-ppt-skill、screencast-script 等不存在的 skill

## REMOVED Requirements

### Requirement: 抖音视频下载

**Reason**: 抖音下载不合规，开源项目不应包含此功能。

**Migration**: 抖音链接将按通用网页处理（httpx 抓取 HTML），不再有视频下载与 ASR 转写能力。涉及移除的内容：
- `Platform.DOUYIN` 枚举值与 URL 识别逻辑
- `VideoProcessor` 中全部抖音下载方法（playwright 后端、cdp 后端、cookie 解析、RENDER_DATA 解析）
- `cdp_downloader.py` 整个文件（仅服务于抖音 cdp 后端）
- `.cookies/douyin.txt` 与 `.cookies/README.md`
- `config.yaml` 中 `douyin` 段与 `cdp` 段
- `DOUYIN_COOKIE` 环境变量支持
- SKILL.md 与 supported_platforms.md 中所有抖音相关文档段落

### Requirement: .claude/skills/ 目录

**Reason**: 与 `.trae/skills/` 完全重复，开源项目只需保留一份。

**Migration**: 删除 `.claude/` 整个目录，所有 skill 以 `.trae/skills/` 为准。

### Requirement: 内容创作 skill 路由

**Reason**: 项目重新定位为通用知识库，不再绑定内容创作场景。涉及的 skill（imitation-writer、writing-workflow、guizang-ppt-skill、screencast-script 及其子 skill）在本项目中不存在，属于原项目残留。

**Migration**: 从 CLAUDE.md 路由表移除所有不存在的 skill 引用，写作规范段落一并删除。
