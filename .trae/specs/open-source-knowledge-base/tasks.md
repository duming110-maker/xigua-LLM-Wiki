# Tasks

- [x] Task 1: 移除 material-collector 脚本中的抖音下载逻辑
  - [x] SubTask 1.1: 修改 `url_parser.py` — 删除 `Platform.DOUYIN` 枚举值，删除 `identify_platform` 中抖音域名识别逻辑（netloc douyin.com 判断），更新 docstring 中抖音相关示例
  - [x] SubTask 1.2: 修改 `collector.py` — 从 `_VIDEO_PLATFORMS` 移除 "douyin"，从 `_PLATFORM_LABELS` 移除 "douyin" 条目，从 `_get_video_processor` 移除 douyin_cfg/cdp_cfg 参数传递，移除 `DOUYIN_COOKIE` 环境变量引用
  - [x] SubTask 1.3: 修改 `video_processor.py` — 删除 `_download_douyin`、`_download_douyin_playwright`、`_download_douyin_cdp`、`_playwright_extract_video_url`、`_resolve_douyin_cookie`、`_load_cookie`、`_parse_cookies`、`_extract_video_url_from_render_data` 方法，删除 `_PLACEHOLDER_PATTERNS`、`_COOKIE_EXPIRED_HINT` 常量，从 `__init__` 移除 douyin_cookie/cookie_file/skill_dir/douyin_backend/douyin_retry/cdp_proxy_url/cdp_load_timeout 参数，从 `_download` 移除 douyin 分支，清理 `_download_file` 中的抖音 Referer 硬编码
  - [x] SubTask 1.4: 检查并清理 `audio_utils.py`、`test_asr.py`、`markdown_writer.py`、`wiki_collector.py` 中的抖音引用

- [x] Task 2: 删除抖音专用文件与目录
  - [x] SubTask 2.1: 删除 `.trae/skills/material-collector/scripts/cdp_downloader.py`
  - [x] SubTask 2.2: 删除 `.trae/skills/material-collector/.cookies/` 整个目录（douyin.txt + README.md）
  - [x] SubTask 2.3: 删除 `__pycache__/` 下的 cdp_downloader.pyc 等编译缓存

- [x] Task 3: 清理 material-collector 配置与文档中的抖音内容
  - [x] SubTask 3.1: 修改 `config.yaml` — 删除 `douyin` 段（backend/retry/cookie_file）、删除 `cdp` 段（proxy_url/load_timeout），清理注释中的抖音说明
  - [x] SubTask 3.2: 修改 `SKILL.md` — 从 frontmatter description 移除抖音，删除「抖音下载后端」「抖音 Cookie」段落，从平台识别规则表移除抖音行，从环境变量表移除 DOUYIN_COOKIE，从注意事项移除抖音相关条目
  - [x] SubTask 3.3: 修改 `references/supported_platforms.md` — 删除「抖音 (Douyin)」整个段落，从环境变量表移除 DOUYIN_COOKIE

- [x] Task 4: 清理 web-access skill 中的抖音引用
  - [x] SubTask 4.1: 检查并修改 `web-access/SKILL.md` — 移除抖音相关引用
  - [x] SubTask 4.2: 检查并修改 `web-access/references/cdp-api.md` — 移除抖音相关示例
  - [x] SubTask 4.3: 检查并修改 `web-access/scripts/cdp-proxy.mjs` — 移除抖音相关逻辑（如有）

- [x] Task 5: 删除 `.claude/` 整个目录
  - [x] SubTask 5.1: 删除 `.claude/skills/` 下所有内容（llm-wiki、material-collector、web-access）

- [x] Task 6: 重写 CLAUDE.md
  - [x] SubTask 6.1: 将项目定位从「内容创作项目」改为「通用 AI 辅助知识库」
  - [x] SubTask 6.2: 精简请求路由表，只保留 material-collector（URL 链接）、llm-wiki（知识库操作）、web-access（网页访问）三条路由，移除 imitation-writer、writing-workflow、guizang-ppt-skill、screencast-script 等不存在的 skill
  - [x] SubTask 6.3: 删除「写作规范」段落、「硬约束」中关于 writing-workflow/imitation-writer 的内容
  - [x] SubTask 6.4: 保留「代码开发规则」和「编码行为准则」段落（通用且有价值）

- [x] Task 7: 新增开源必备文件
  - [x] SubTask 7.1: 创建 `LICENSE` 文件（MIT 协议）
  - [x] SubTask 7.2: 创建 `README.md` — 包含项目简介、核心能力（多平台素材抓取、wiki 知识库管理、网页访问）、目录结构、快速上手（环境变量、依赖安装、基本用法）、skill 说明

- [x] Task 8: 清理个人配置数据
  - [x] SubTask 8.1: 修改 `config.yaml` — 将 `asr.whisper.download_root` 从 `E:/Whisper` 改为默认值或注释说明
  - [x] SubTask 8.2: 删除 `create_traeshort.ps1`（个人脚本，与开源项目无关）
  - [x] SubTask 8.3: 更新 `.gitignore` — 确保排除 .cookies/、.env、config.local.yaml 等敏感文件

# Task Dependencies

- Task 2 依赖 Task 1（先改代码再删文件，避免引用断裂）
- Task 3 可与 Task 1 并行（文档与代码独立）
- Task 4 可与 Task 1/3 并行（不同 skill 目录）
- Task 5 可与所有其他任务并行（独立删除操作）
- Task 6 可与 Task 1-5 并行（CLAUDE.md 独立）
- Task 7 依赖 Task 6（README 需参考最终 CLAUDE.md 定位）
- Task 8 可与 Task 1-7 并行（配置清理独立）
