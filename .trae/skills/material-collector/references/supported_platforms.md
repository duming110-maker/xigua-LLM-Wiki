# 支持平台与 URL 格式说明

环境变量与外部工具的权威定义见 SKILL.md，本文件只描述各平台的链路与已知限制。

## 视频平台

### 哔哩哔哩 (Bilibili)

- **标准链接**: `https://www.bilibili.com/video/BV1xx411c7mD`
- **处理链路**: yt-dlp 下载视频 → ffmpeg 提取音频 → DashScope ASR 转写
- **前置条件**:
  - 需要安装 `yt-dlp`
  - 需要系统安装 `ffmpeg`

## 文章平台

### 微信公众号

- **链接格式**: `https://mp.weixin.qq.com/s/xxxxxxxxxx`
- **处理链路**: httpx 抓取 HTML → BeautifulSoup 解析标题/作者/日期/正文 → HTML 转 Markdown
- **已知限制**:
  - 频繁访问可能触发反爬（验证码、IP 封禁）
  - 部分文章可能有访问限制
  - 视频号嵌入内容无法提取

### GitHub

- **链接格式**: `https://github.com/*`
- **处理链路**: web-access CDP Proxy 真实浏览器渲染（复用用户日常浏览器登录态）→ 提取 README 正文 → Markdown
- **前置条件**:
  - 需先启动 web-access CDP Proxy：`node <web-access skill>/scripts/check-deps.mjs`
  - 代码内自动通过 `http://127.0.0.1:3456` 调用
- **已知限制**:
  - 重度 JS SPA，httpx 直接抓取拿不到渲染后内容，必须走 CDP Proxy
  - 私有仓库需用户浏览器已登录 GitHub

### 通用网页

- **链接格式**: 任何 `https?://` 开头的非上述平台 URL
- **处理链路**: httpx 抓取 HTML → BeautifulSoup 解析标题/正文 → HTML 转 Markdown
- **已知限制**:
  - JavaScript 渲染的页面可能无法获取完整内容（SPA 应用）
  - 需要登录的页面无法访问
  - 反爬严格的网站可能被封禁
  - 如果内容是 JS 驱动加载的（如推文、动态列表），httpx 可能只拿到骨架 HTML，正文全空。此时应怀疑是 SPA 页面，需用浏览器工具兜底

## 不支持的平台

### 抖音 (Douyin)

- **链接特征**: `douyin.com` / `iesdouyin.com` / `v.douyin.com`（含短链）
- **处理方式**: **直接回复不支持抖音平台抓取**，不调用 collector
- **不支持原因**: 平台合规性限制，不提供抖音内容抓取能力
