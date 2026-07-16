---
name: llm-wiki
description: 个人知识库（wiki/ 目录）管理器，所有 wiki 文档操作（新建/更新/补充/查询/整理/从素材摄入）的唯一入口。只要涉及 wiki/ 目录下文档的读写，都应走此 skill——素材摄入时调 material-collector 抓取，wiki 页面创建与维护由本 skill 完成。触发词：知识库、wiki、整理 wiki、更新知识库、查知识库、新建 wiki 页面、摄入素材。
---

> `{skill_dir}` = 本 SKILL.md 所在目录

# 个人知识库管理器

你是知识库管理者。你的工作是维护一套结构化、相互关联的 markdown 文件——每次用户添加来源或提问时，知识库都变得更丰富。编译式知识库：素材一次性写入 wiki/，后续操作只整合不重抓。

## 目录结构

```
wiki/
  sources/                    # Layer 1：原始素材（不可变，只读）
    batch_YYYYMMDD_HHMMSS/    # 按采集批次组织
      001.md                  # 素材文件
      _index.md               # 批次索引
  wiki/                       # Layer 2：知识页面（你完全拥有）
    index.md                  # 总目录（入口）
    log.md                    # 操作日志（追加写入）
    人物/                     # 实体：人物
    工具与产品/               # 实体：产品/项目
    概念/                     # 概念/对比/框架
```

## 操作路由

| 操作 | 触发场景 | 详细步骤 |
|------|---------|---------|
| **init** | `wiki/` 不存在 | → operations.md §1 |
| **ingest** | 用户提供新素材（URL/文件/文本） | → operations.md §2 |
| **process** | 处理已采集但未整合的素材 | → operations.md §3 |
| **query** | 用户对知识库提问 | → operations.md §4 |
| **lint** | 健康检查 | → operations.md §5 |
| **digest** | 知识库概览 | → operations.md §6 |

## 素材采集

素材采集不经过 LLM，按来源分工：

- **URL 素材**（B站/YouTube/公众号/GitHub/网页等）→ Agent 调用 `material-collector` skill
- **本地文件 / 粘贴文本** → 调用内部脚本：

```bash
python {skill_dir}/scripts/wiki_collector.py --text "文本" --output wiki/sources
python {skill_dir}/scripts/wiki_collector.py --file "路径" --output wiki/sources
```

## Wiki 页面创建

创建或更新 wiki 页面时，**必须读取并遵循** `{skill_dir}/references/page-templates.md` 中的 **Wiki 页面创建 Prompt 模板**。核心规则：中文文件名、按类型放入对应子目录、5 个必需章节、至少 2 个交叉引用、一句话摘要 ≤ 60 字。

## 核心原则

- **来源即真相。** `sources/` 不可变，你拥有 `wiki/`
- **积累而非重复。** 每次操作与已有页面整合
- **充分链接。** 交叉引用是知识库增值的关键
- **暴露矛盾。** 标记矛盾，不静默覆盖
- **索引是入口。** 每次查询从 `index.md` 开始
- **好的回答属于 wiki。** 不让洞察消失在聊天历史中
- **单点真相。** 每个知识点只存在于一个页面中。其他页面需要引用时只放 `[[链接]]` + 一句话说明（≤30 字），不重复展开详细内容。ingest 时先检查已有页面，发现重复知识点只建链接。

## 参考文件

执行操作时按需读取：
- `{skill_dir}/references/operations.md` — 各操作详细步骤
- `{skill_dir}/references/page-templates.md` — 页面格式 + Wiki 创建 Prompt 模板
