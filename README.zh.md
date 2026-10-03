# kimi-hud

Kimi Code CLI 的实时状态栏 HUD —— 上下文用量、账号额度、工具活动、子代理进度、Todo 进度和模式徽标，常驻输入框下方。

🌐 [English](README.md) | [中文文档](README.zh.md)

思路借鉴 [cursor-hud](https://github.com/huai-xia/cursor-hud)（其本身又借鉴 claude-hud）。
同样的产品思路（原生 statusline + 会话日志），针对 Kimi Code 的 `status_line` 协议和 `wire.jsonl` 事件日志重新实现——零依赖纯 Python。

如果这个项目对你有帮助，欢迎点一个 star——也欢迎去 star [cursor-hud](https://github.com/huai-xia/cursor-hud)。

## 安装

要求 Python 3（≥ 3.9；macOS 自带 `/usr/bin/python3`）。无第三方依赖，无需构建。

```sh
git clone https://github.com/coordinate-bob/kimi-hud.git
cd kimi-hud
python3 scripts/setup.py
```

然后新开一个 Kimi Code 会话，或在现有会话里执行 `/reload-tui`。HUD 出现在输入框下方的 footer。

卸载：`python3 scripts/setup.py --remove`（tui.toml 备份保留）。

## kimi-hud 是什么？

kimi-hud 让你随时看清 Kimi Code 会话里正在发生什么。

| 你看到什么 | 为什么有用 |
| --- | --- |
| 模型徽标 | 知道当前用的是哪个模型 |
| 模式徽标 | `⧉ Plan` / `⚡ yolo` / `◈ auto`——知道代理有多大权限、哪些操作不用问你 |
| 项目路径 + Git | 知道在哪个项目、哪个分支（脏标记 `*`） |
| 上下文健康度 | 在上下文窗口撑满之前心里有数 |
| 账号额度 | 5 小时 / 7 天 / 自然月的用量条，数据来自官方 `/usages` 接口 |
| Todo 进度 | `☰ 2/5`——实时跟踪任务完成情况 |
| 工具活动 | 实时看到 Read、Bash、Grep 等工具的执行 |
| 子代理追踪 | 看到哪些子代理在运行、跑了多久 |

示例一行：

```
Kimi for Coding ⧉ Plan │ kimi-hud │ main* │ ████░░░░░░ 15% │ 5h ███░░ month ░░░░░ │ ☰ 2/5 │ ▶ Bash │ ◐ explore-1 12s
```

没有数据的段自动不渲染（比如非 git 仓库不显示 git 段；账号没有 7 天额度档就不显示 7d 条）。

## 工作原理

Kimi Code 原生支持自定义 status line：运行一个命令，把 JSON 快照从 stdin 传入，把 stdout 第一行渲染为 footer（300ms 超时，每秒最多刷新一次；失败时回退到内置 footer）。

```
Kimi Code ──stdin JSON──▶ kimi-hud ──单行 ANSI──▶ footer
                │                ├─▶ session_index.jsonl → wire.jsonl（工具 / 子代理 / Todo）
                │                └─▶ /usages API（额度，磁盘缓存 + 后台刷新子进程）
                └─ model / cwd / git / context / permission / plan / sessionId / version
```

要点：

- **上下文百分比来自快照**（`contextTokens / maxContextTokens`），不是估算。
- **工具、子代理、Todo** 从会话的 `wire.jsonl` 解析——结构化事件日志，工具调用 ID 稳定、`agent.turn.started/ended` 生命周期明确，所以是精确匹配而非启发式猜测。纯只读，不向你配置里注入任何 hooks。
- **额度**复用 CLI 自己在用的官方接口（`GET /usages`，Bearer token 取自 `~/.kimi-code/credentials/kimi-code.json`）。token 只在本机读取、只发往 `api.kimi.com`。结果磁盘缓存（默认 300 秒）；缓存过期后由一个独立后台进程拉取新数据，status line 本身永不阻塞在网络请求上。
- 全部逻辑都在 300ms 预算内完成：热渲染约 50ms。

相对 Cursor CLI / cursor-hud 的 Kimi 特有适配：

- **单行而非多行**——Kimi 只渲染 stdout 第一行，所以所有段折叠进一行紧凑显示。
- **无 hooks 旁路**——Kimi Code 的 `wire.jsonl` 已有结构化的工具和 turn 事件。
- **Plan 用量条变成了额度条**——由 Kimi 的托管用量 API 驱动，而非 Cursor 的套餐接口。

## 配置

随时可运行配置器：

```sh
python3 scripts/configure.py                      # 引导式
python3 scripts/configure.py --preset=full        # essential / full / minimal
python3 scripts/configure.py --set showQuota=false --set colors.model=#FF88FF
python3 scripts/configure.py --show               # 查看当前配置
```

或直接编辑 `~/.kimi-code/kimi-hud/config.json`（示例见 [fixtures/config.example.json](fixtures/config.example.json)）。非法 JSON 静默回退默认值。

| 选项 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `pathLevels` | number \| `"full"` | 1 | 项目路径显示的目录层级 |
| `showModel` | boolean | true | 模型徽标 |
| `showMode` | boolean | true | `⧉ Plan` / `⚡ yolo` / `◈ auto` 徽标 |
| `showGit` / `showDirty` | boolean | true | Git 分支 + 脏标记 `*` |
| `showContextBar` / `contextBarWidth` | boolean / number | true / 10 | 上下文用量条 |
| `showQuota` / `quotaCacheTtlS` / `quotaBarWidth` | — | true / 300 / 5 | 账号额度条 |
| `showTodos` / `todoDoneTtlS` | boolean / number | true / 120 | Todo 进度；全部完成后保留秒数 |
| `showTools` / `showCompletedTools` | boolean | true / false | 工具活动；空闲时 `✓ Read ×3` 统计（默认关） |
| `toolsMaxVisible` / `toolNameMaxLength` | number | 4 / 0 | 工具显示上限（0 = 不截断） |
| `showAgents` / `agentNameMaxLength` | boolean / number | true / 12 | 子代理段 |
| `maxLineWidth` | number | 0 | 超过则截断（0 = 用 COLUMNS） |
| `colors.*` | 颜色名或 `"#RRGGBB"` | 见示例 | 各段颜色 |
| `thresholds` | object | 25/50/75/90 | 上下文条变色阈值（%） |

额度条 ≥70% 变黄、≥90% 变红（`colors.quotaOk/Warn/Crit`）。

颜色示例：

```json
{
  "colors": {
    "model": "#FF88FF",
    "context": { "ok": "blue", "mid": "cyan", "high": "yellow", "warn": "magenta", "crit": "red" },
    "quotaWarn": "#E8A838"
  },
  "thresholds": { "mid": 25, "high": 50, "warn": 75, "crit": 90 }
}
```

颜色名：`black red green yellow blue magenta cyan white gray brightRed brightGreen brightYellow brightBlue brightMagenta brightCyan brightWhite textMuted`，或任意 `#RRGGBB` 真彩色。

## 临时禁用

```sh
KIMI_HUD_DISABLE=1 kimi
```

无需改动 `tui.toml`。

## 故障排查

**footer 还是内置布局？**

- `setup.py` 之后执行 `/reload-tui` 或新开会话。
- 确认 `~/.kimi-code/tui.toml` 里有 `[status_line] command = "python3 .../kimi-hud.py"`。
- 命令失败会静默回退到内置 footer。调试：
  ```sh
  KIMI_HUD_CAPTURE=1 kimi   # stdin 快照落盘到 ~/.kimi-code/kimi-hud/capture/
  ```

**额度段不显示？**

- 仅对登录（managed）账号可用。
- 首次拉取是异步的——开会话后等几秒。
- 不想让 HUD 读取本机 OAuth token 的话，设 `showQuota=false`。

**改配置后看起来没变化？**

- 执行 `/reload-tui` 或新开会话。

## 开发

```sh
python3 kimi-hud.py < fixtures/sample-stdin.json   # 模拟一次 statusline 调用
python3 kimi-hud.py --fetch-quota                  # 强制刷新额度缓存
```

## 致谢与灵感来源

- [cursor-hud](https://github.com/huai-xia/cursor-hud)（huai-xia）——Cursor CLI 的 statusline HUD 原版；kimi-hud 借鉴其产品思路和交互模式，为 Kimi Code 重新实现。
- [claude-hud](https://github.com/jarrodwatts/claude-hud)（Jarrod Watts）——Claude Code 的 statusline HUD 鼻祖。
- 独立项目，与月之暗面（Moonshot AI）及 Cursor/Anthropic 均无隶属关系。

## License

MIT
