# CDP Proxy API 参考

## 基础信息

- 地址：`http://localhost:3456`
- 启动：`node ~/.trae/skills/web-access/scripts/cdp-proxy.mjs &`
- 启动后持续运行，不建议主动停止（重启需 Chrome 重新授权）
- 强制停止：`pkill -f cdp-proxy.mjs`

## API 端点

### GET /health
健康检查，返回连接状态。
```bash
curl -s http://localhost:3456/health
```

### GET /cookies?domain=xxx
浏览器级取 cookie（底层 `Network.getCookies`，无需 sessionId）。**关键能力：能拿到 HttpOnly / Secure cookie，这是页面内 `document.cookie` 永远拿不到的。** 用途：cookie 失效时由本端点拿到完整登录态写回 `.cookies/`，避免明文 cookie 硬编码。

返回 `{ domain, cookies: [...] }`，每个 cookie 含 `name`、`value`、`domain`、`path`、`httpOnly`、`secure`、`sameSite`、`expires` 等字段（CDP 原样）。按 `cookie.domain` 包含请求 domain 过滤（去重子域噪音）。
```bash
curl -s "http://localhost:3456/cookies?domain=www.example.com"
```

### GET /targets
列出所有已打开的页面 tab。返回数组，每项含 `targetId`、`title`、`url`。
```bash
curl -s http://localhost:3456/targets
```

### POST /new
创建新后台 tab，自动等待页面加载完成。**URL 通过 POST body 原样传入**，无需 URL-encode、不会因 query 中含 `&` 被切分。返回 `{ targetId }`。
```bash
curl -s -X POST --data-raw 'https://example.com' http://localhost:3456/new
# 含 query 的目标 URL（如带 token 的小红书笔记）也直接原样传：
curl -s -X POST --data-raw 'https://www.xiaohongshu.com/explore/xxx?xsec_source=app_share&xsec_token=ABC&type=normal' http://localhost:3456/new
```
> v2.5.3 起改为 POST。旧的 `GET /new?url=...` 返回 400 + 迁移指引，详见 `migration-2.5.3.md`。

### GET /close?target=ID
关闭指定 tab。
```bash
curl -s "http://localhost:3456/close?target=TARGET_ID"
```

### POST /navigate?target=ID
在已有 tab 中导航到新 URL，自动等待加载。**target 走 query（不带特殊字符的不透明 ID），URL 走 POST body**。
```bash
curl -s -X POST --data-raw 'https://example.com' "http://localhost:3456/navigate?target=ID"
```
> v2.5.3 起改为 POST。旧的 `GET /navigate?target=...&url=...` 返回 400 + 迁移指引，详见 `migration-2.5.3.md`。

### GET /back?target=ID
后退一页。
```bash
curl -s "http://localhost:3456/back?target=ID"
```

### GET /info?target=ID
获取页面基础信息（title、url、readyState）。
```bash
curl -s "http://localhost:3456/info?target=ID"
```

### POST /eval?target=ID
执行 JavaScript 表达式，POST body 为 JS 代码。
```bash
curl -s -X POST "http://localhost:3456/eval?target=ID" -d 'document.title'
```

### POST /click?target=ID
JS 层面点击（`el.click()`），POST body 为 CSS 选择器。自动 scrollIntoView 后点击。简单快速，覆盖大多数场景。
```bash
curl -s -X POST "http://localhost:3456/click?target=ID" -d 'button.submit'
```

### POST /clickAt?target=ID
CDP 浏览器级真实鼠标点击（`Input.dispatchMouseEvent`），POST body 为 CSS 选择器。先获取元素坐标，再模拟鼠标按下/释放。算真实用户手势，能触发文件对话框、绕过部分反自动化检测。
```bash
curl -s -X POST "http://localhost:3456/clickAt?target=ID" -d 'button.upload'
```

### POST /setFiles?target=ID
给 file input 设置本地文件路径（`DOM.setFileInputFiles`），完全绕过文件对话框。POST body 为 JSON。
```bash
curl -s -X POST "http://localhost:3456/setFiles?target=ID" -d '{"selector":"input[type=file]","files":["/path/to/file1.png","/path/to/file2.png"]}'
```

### GET /scroll?target=ID&y=3000&direction=down
滚动页面。`direction` 可选 `down`（默认）、`up`、`top`、`bottom`。滚动后自动等待 800ms 供懒加载触发。
```bash
curl -s "http://localhost:3456/scroll?target=ID&y=3000"
curl -s "http://localhost:3456/scroll?target=ID&direction=bottom"
```

### GET /screenshot?target=ID&file=/tmp/shot.png
截图。指定 `file` 参数保存到本地文件；不指定则返回图片二进制。可选 `format=jpeg`。
```bash
curl -s "http://localhost:3456/screenshot?target=ID&file=/tmp/shot.png"
```

## /eval 使用提示

- POST body 为任意 JS 表达式，返回 `{ value }` 或 `{ error }`
- 支持 `awaitPromise`：可以写 async 表达式
- 返回值必须是可序列化的（字符串、数字、对象），DOM 节点不能直接返回，需要提取属性
- 提取大量数据时用 `JSON.stringify()` 包裹，确保返回字符串
- 根据页面实际 DOM 结构编写选择器，不要套用固定模板

## 错误处理

| 错误 | 原因 | 解决 |
|------|------|------|
| `Chrome 未开启远程调试端口` | Chrome 未开启远程调试 | 提示用户打开 `chrome://inspect/#remote-debugging` 并勾选 Allow |
| `attach 失败` | targetId 无效或 tab 已关闭 | 用 `/targets` 获取最新列表 |
| `CDP 命令超时` | 页面长时间未响应 | 重试或检查 tab 状态 |
| `端口已被占用` | 另一个 proxy 已在运行 | 已有实例可直接复用 |

## human-pace 发布模式（反风控）

**用途**：模拟人工节奏发布内容——「操作一个停顿一个」，不一次性粘贴标题+简介+标签，避免被风控识别为机器批量提交。

**用法**：给写操作端点加 `?pace=human` query，操作成功后 proxy 会随机睡 3-8 秒（默认区间）再返回，相当于在 Agent 这一步自然阻塞。

**支持 `?pace=human` 的端点**：
- `/navigate`、`/click`、`/clickAt`、`/eval`、`/scroll`、`/setFiles`

**注意事项**：
- 仅在操作成功后停顿；失败立即返回错误（让 Agent 尽快看到错误，不浪费时间）。
- 区间通过 env 配置（`CDP_HUMAN_PACE_MIN` / `CDP_HUMAN_PACE_MAX`，单位 ms，默认 3000/8000），改 env 需重启 proxy。
- 调用方负责自己再叠加操作间隔（如粘贴标题后等待，再粘贴简介）——proxy 只保证单步操作后有停顿，不负责编排多步序列。
- **封号风险告知**（必须向用户传达）：半自动发布模拟人工操作，但目标平台风控动态判定，账号封禁风险由用户自行承担。
