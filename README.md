# xigua-llm

> 📌 **代码仓库**：[GitHub](https://github.com/duming110-maker/xigua-LLM-Wiki) · [Gitee](https://gitee.com/xiguadan/xigua-LLM-Wiki)
> （网络无法访问 GitHub 时，可使用 Gitee 镜像）

一个通用 AI 辅助的个人知识库：把多平台素材抓取、结构化知识管理和浏览器访问能力整合到一套 skill 体系中，帮助用户持续积累、交叉引用、按需检索自己的知识库。

## 核心能力

- **多平台素材抓取** — 把某众号、某站、GitHub、通用网页的 URL 批量抓取为 Markdown；视频自动 ASR 转写为文字。
- **知识库管理** — 维护 `wiki/` 下的结构化 markdown 页面，按实体（人物、工具与产品、概念）分类，支持素材摄入、查询、整理、健康检查。
- **浏览器访问** — 通过 CDP proxy 直连用户日常浏览器（Chrome / Edge），天然携带登录态，处理搜索、登录后操作、动态渲染页面、社交媒体抓取等任务。

## 项目定位

**是什么**：通用 AI 辅助知识库，通过多平台素材抓取和结构化知识管理，帮助用户搭建自己的个人知识库。

**不是什么**：
- 不产出原创文章/视频脚本（那是其他项目的事）
- 不做抖音平台抓取（合规红线，遇到抖音链接直接回复不支持）
- 不做数据库/Web 服务开发（无后端工程）

## 目录结构

```
xigua-llm/
├── .trae/
│   └── skills/
│       ├── material-collector/   # 多平台素材抓取器
│       │   ├── scripts/          # collector、asr、article_fetcher 等脚本
│       │   ├── references/       # 支持平台说明
│       │   ├── config.yaml       # ASR / 抓取配置
│       │   └── requirements.txt
│       ├── llm-wiki/             # 知识库管理器
│       │   ├── scripts/          # wiki_collector.py
│       │   └── references/       # 操作步骤、页面模板
│       └── web-access/           # 浏览器访问 skill（Node.js，第三方）
│           ├── scripts/          # CDP proxy、依赖检查等 .mjs 脚本
│           └── references/       # CDP API、站点经验
├── wiki/
│   ├── sources/                  # Layer 1：原始素材（按批次组织，只读）
│   └── wiki/                     # Layer 2：知识页面（index.md 为入口）
├── CLAUDE.md                     # AI 上下文与请求路由配置
├── LICENSE
└── README.md
```

## 快速上手

### 环境要求

- **Python 3.10+**（material-collector、llm-wiki 使用）
- **Node.js 22+**（web-access 使用，原生 WebSocket）
- **ffmpeg**（视频音频提取与 ASR 解码，需含 aac 解码器）
- **Chrome 或 Edge**（web-access CDP 模式必需，需开启远程调试）
- **yt-dlp**（某站视频下载）

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | 视使用模式 | 阿里 DashScope API Key，启用 remote ASR 模式时必需，local 模式不需要 |
| `FFMPEG_BIN` | 否 | 显式指定完整版 ffmpeg.exe 路径，未设置时自动探测 |
| `WEB_ACCESS_BROWSER` | 否 | web-access 浏览器偏好（`chrome` / `edge`），留空则每次询问 |

### 依赖安装

```bash
# material-collector Python 依赖
pip install -r .trae/skills/material-collector/requirements.txt

# web-access 浏览器远程调试（CDP 模式前置）
# Chrome: 在地址栏打开 chrome://inspect/#remote-debugging，勾选 "Allow remote debugging for this browser instance"
# Edge:   在地址栏打开 edge://inspect/#remote-debugging，勾选 "Allow remote debugging for this browser instance"
```

### 基本用法

**采集素材**（链接文本会自动提取 URL，视频自动 ASR）：

```bash
python .trae/skills/material-collector/scripts/collector.py \
  --text "包含多个链接的原始文本" \
  --config .trae/skills/material-collector/config.yaml
```

可选参数：`--url` 指定单链接、`--file` 从文件读取 URL 列表、`--name` 自定义批次名、`--output` 指定输出根目录。素材默认输出到 `material/batch_YYYYMMDD_HHMMSS/`，每个批次含 `001.md`、`_index.md` 等。

**把素材摄入知识库**（由 llm-wiki 调度，将素材输出到 `wiki/sources`）：

```bash
python .trae/skills/material-collector/scripts/collector.py \
  --text "链接文本" \
  --output wiki/sources \
  --config .trae/skills/material-collector/config.yaml
```

**浏览器访问**（CDP 直连用户浏览器，前置检查并启动 proxy）：

```bash
node .trae/skills/web-access/scripts/check-deps.mjs
```

通过后即可用 `curl http://localhost:3456/...` 调用 proxy 的 `/new`、`/eval`、`/click`、`/scroll`、`/screenshot` 等接口操作页面。

### 适配其他 Agent

本项目默认面向 Trae（skills 目录为 `.trae/skills/`）。若使用其他 Agent，把目录改名即可：

- **Claude Code**：`.trae` → `.claude`
- **CodeX**：`.trae` → `.agent`

也可以直接把目录路径和下载的文件告诉正在使用的 Agent，让它自行处理项目所用的 skills，一般都会自动帮你完成迁移。

## Skill 说明

| Skill | 作用 | 触发方式 |
|-------|------|---------|
| `material-collector` | 多平台 URL 抓取，视频自动 ASR 转写，统一输出 Markdown 素材 | 用户提供 URL 要求抓取/下载/转文字/提取内容 |
| `llm-wiki` | 知识库（`wiki/` 目录）唯一入口：新建/更新/查询/整理/摄入素材 | 用户操作知识库、整理 wiki、新建 wiki 页面、摄入素材 |
| `web-access` | CDP proxy 连接真实浏览器，处理登录态、动态页面、社交媒体抓取 | 用户要求搜索、查看网页、登录后操作、抓取社交内容 |

请求路由优先级见 `CLAUDE.md`：用户指名 skill 优先；含 HTTP 链接走 `material-collector`；操作知识库走 `llm-wiki`；需要浏览器访问走 `web-access`。抖音链接（`douyin.com` / `iesdouyin.com` / `v.douyin.com`）不调用任何 skill，直接回复不支持。

## 平台支持

### 抓取支持的平台

| 平台 | URL 特征 | 处理方式 |
|------|---------|---------|
| 某站 | `某站视频地址` | yt-dlp 下载 → 音频提取 → ASR 转写 |
| GitHub | `github.com/*` | web-access CDP Proxy 真实浏览器渲染 → 提取 README 正文 → Markdown |
| 微信某众号 | `微信某众号链接` | httpx 抓取 → HTML 解析 → Markdown |
| 通用网页 | 其他 HTTP URL | httpx 抓取 → HTML 解析 → Markdown |

### 不支持的平台

| 平台 | URL 特征 | 处理方式 |
|------|---------|---------|
| 抖音 | `douyin.com` / `iesdouyin.com` / `v.douyin.com` | **直接回复不支持抖音平台抓取**，不调用 collector |

各平台详细链路、前置条件、已知限制见 [supported_platforms.md](.trae/skills/material-collector/references/supported_platforms.md)。

## ASR 配置

视频素材的语音转写支持两种模式，在 `.trae/skills/material-collector/config.yaml` 的 `asr.mode` 字段切换：

- **`local`**（默认）— 本地 Whisper 模型转写。配置项：`asr.whisper.model`（如 `turbo`）、`device`（如 `cuda`）、`language`（如 `zh`）。无需 API Key，但需要 GPU 较快。
- **`remote`** — 阿里 DashScope 远程 ASR。使用 `qwen3-asr-flash` 模型，需设置环境变量 `DASHSCOPE_API_KEY`。无 GPU 依赖，适合长视频批量转写。

## 致谢

本项目的知识库实现思路源自 Andrej Karpathy 的 LLM Wiki 模式（开源思路文件见 [source/llm-wiki.md](source/llm-wiki.md)）：三层架构（原始素材 / 知识页面 / Schema 配置）、ingest / query / lint 三类操作、index.md 与 log.md 双索引、交叉引用与矛盾暴露等核心规则均源自该思路。

本项目的 `web-access` skill 来自第三方开源项目 [eze-is/web-access](https://github.com/eze-is/web-access)，作者是 [一泽 Eze](https://github.com/eze-is)，遵循 MIT 协议。该 skill 提供了完整的 CDP proxy 联网能力与站点经验积累机制，感谢作者的出色工作。

## 许可证

本项目采用 MIT 协议，详见 [LICENSE](LICENSE)。
