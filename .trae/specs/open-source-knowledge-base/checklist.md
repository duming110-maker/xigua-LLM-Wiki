# Checklist

## 抖音功能移除

- [x] `url_parser.py` 中不再有 `Platform.DOUYIN` 枚举值和 douyin.com 域名识别逻辑
- [x] `collector.py` 中 `_VIDEO_PLATFORMS` 不含 "douyin"，`_PLATFORM_LABELS` 不含 "douyin" 条目
- [x] `video_processor.py` 中不再有任何 `_download_douyin*` 方法、cookie 解析方法、RENDER_DATA 解析方法
- [x] `video_processor.py` 的 `__init__` 不再接收 douyin_cookie/cookie_file/skill_dir/douyin_backend 等参数
- [x] `video_processor.py` 的 `_download` 方法不再有 douyin 分支
- [x] `cdp_downloader.py` 文件已删除
- [x] `.cookies/` 目录已删除（douyin.txt + README.md）
- [x] `config.yaml` 中不再有 `douyin` 段和 `cdp` 段
- [x] `SKILL.md` 中不再出现抖音、douyin、DOUYIN_COOKIE 等字样
- [x] `supported_platforms.md` 中不再有抖音段落
- [x] 全项目 grep `douyin|DOUYIN|Douyin|抖音` 在 .trae/skills/ 代码与文档中无命中（wiki/ 历史内容除外）

## .claude/ 目录删除

- [x] `.claude/` 目录已完全删除
- [x] 项目中无对 `.claude/skills/` 的路径引用

## web-access 清理

- [x] `web-access/SKILL.md` 中不再有抖音相关引用
- [x] `web-access/references/cdp-api.md` 中不再有抖音示例
- [x] `web-access/scripts/cdp-proxy.mjs` 中不再有抖音专用逻辑

## CLAUDE.md 重写

- [x] 项目定位为「通用 AI 辅助知识库」，不出现「内容创作项目」
- [x] 请求路由表只含 material-collector、llm-wiki、web-access 三条
- [x] 不出现 imitation-writer、writing-workflow、guizang-ppt-skill、screencast-script、douyin-writer、news-writer 等不存在的 skill
- [x] 「写作规范」段落已删除
- [x] 「硬约束」中关于 writing-workflow/imitation-writer 的内容已删除
- [x] 「代码开发规则」和「编码行为准则」段落保留

## 开源文件

- [x] 根目录存在 `LICENSE` 文件，采用 MIT 协议
- [x] 根目录存在 `README.md`，包含项目简介、核心能力、目录结构、快速上手、依赖安装
- [x] README.md 不含个人路径或敏感信息

## 个人配置清理

- [x] `config.yaml` 中 `asr.whisper.download_root` 不再硬编码 `E:/Whisper`
- [x] `create_traeshort.ps1` 已删除
- [x] `.gitignore` 排除 .cookies/、.env、*.local.yaml 等敏感文件
