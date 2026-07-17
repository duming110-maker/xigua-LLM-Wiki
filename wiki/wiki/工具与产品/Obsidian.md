# Obsidian

> 本地 Markdown 知识库工具，作为 LLM Wiki 的 IDE，提供 graph view、Web Clipper、Dataview 等插件

## 概述

Obsidian 是一款基于本地 Markdown 文件的知识库工具。在 LLM Wiki 模式中，Obsidian 充当 wiki 的**浏览器和 IDE**：用户在一侧打开 LLM agent，另一侧打开 Obsidian，LLM 根据对话编辑 wiki，用户在 Obsidian 中实时浏览结果——跟随链接、查看 graph view、阅读更新后的页面。

引用来源的类比："Obsidian 是 IDE，LLM 是程序员，wiki 是代码库。"

## 核心观点 / 关键事实

- **角色定位**：wiki 的 IDE/浏览器，用户实时浏览 LLM 维护的 wiki（→ [[LLM-Wiki模式]]）
- **Graph view**：观察 wiki 形态的最佳方式——什么连接到什么、哪些页面是枢纽、哪些是孤立页面
- **Web Clipper**：浏览器扩展，将网页文章转为 Markdown，便于快速将素材纳入原始素材层
- **图片本地化技巧**：在设置中将"附件文件夹路径"设为固定目录（如 `raw/assets/`），绑定"下载当前文件附件"快捷键（如 Ctrl+Shift+D），剪藏文章后一键下载所有图片到本地磁盘，让 LLM 直接引用而非依赖可能失效的 URL
- **Marp 插件**：基于 Markdown 的幻灯片格式插件，可直接从 wiki 内容生成演示文稿
- **Dataview 插件**：对页面 frontmatter 运行查询，若 LLM 在 wiki 页面添加 YAML frontmatter（标签、日期、来源数），Dataview 可生成动态表格和列表

## 相关页面

- [[LLM-Wiki模式]] — Obsidian 是该模式三层架构中 wiki 层的浏览/编辑前端
- [[LLM-Wiki来源摘要]] — 提及 Obsidian 技巧的来源素材

## 争议与数据空白

- 来源文档未涉及 Obsidian 的同步、协作、付费功能等非 LLM Wiki 场景的评估
- 未讨论 LLM 无法一次性读取含内联图片的 Markdown 的限制及其对 Obsidian 使用流程的具体影响（文档提及需先读文本再单独查看图片，略显繁琐）

## 来源

- [LLM Wiki — 用 LLM 构建个人知识库的模式](../sources/llm-wiki-pattern/001.md) — 2026-07-17
