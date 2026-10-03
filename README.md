# kimi-hud

Real-time statusline HUD for Kimi Code CLI — context usage, account quota, active tools, running subagents, todo progress, and mode badges. Always visible below your input.

🌐 [English](README.md) | [中文文档](README.zh.md)

Inspired by [cursor-hud](https://github.com/huai-xia/cursor-hud) (which itself was inspired by claude-hud).
Same product idea (native statusline + session logs), reimplemented for Kimi Code's `status_line` protocol and `wire.jsonl` event log — in dependency-free Python.

If this helps you, a star on this repo is appreciated — and you're also welcome to star [cursor-hud](https://github.com/huai-xia/cursor-hud).

## Install

Requires Python 3 (≥ 3.9; macOS ships one at `/usr/bin/python3`). No third-party packages, no build step.

```sh
git clone https://github.com/coordinate-bob/kimi-hud.git
cd kimi-hud
python3 scripts/setup.py
```

Then start a new Kimi Code session, or run `/reload-tui` in an existing one. The HUD appears in the footer below the input box.

To remove: `python3 scripts/setup.py --remove` (the tui.toml backup is kept).

## What is kimi-hud?

kimi-hud gives you better insight into what's happening in your Kimi Code session.

| What You See | Why It Matters |
| --- | --- |
| Model badge | Know which model you're on |
| Mode badges | `⧉ Plan` / `⚡ yolo` / `◈ auto` — know how much the agent can do without asking |
| Project path + git | Know which project and branch you're in (dirty `*`) |
| Context health | Know how full the context window is before it's too late |
| Account quota | 5h / 7d / month usage bars from the official `/usages` API |
| Todo progress | `☰ 2/5` — track task completion in real time |
| Tool activity | Watch reads, edits, and searches as they happen |
| Subagent tracking | See which subagents are running and for how long |

Example line:

```
Kimi for Coding ⧉ Plan │ kimi-hud │ main* │ ████░░░░░░ 15% │ 5h ███░░ month ░░░░░ │ ☰ 2/5 │ ▶ Bash │ ◐ explore-1 12s
```

Segments you don't have data for simply don't render (e.g. no git repo → no git segment; account without a 7-day quota → no 7d bar).

## How It Works

Kimi Code natively supports a custom status line: it runs a command, passes a JSON snapshot on stdin, and renders the first stdout line as the footer (300ms timeout, refreshed at most once per second; failures fall back to the built-in footer).

```
Kimi Code ──stdin JSON──▶ kimi-hud ──single ANSI line──▶ footer
                │                ├─▶ session_index.jsonl → wire.jsonl (tools / subagents / todos)
                │                └─▶ /usages API (quota, disk cache + background refetch)
                └─ model / cwd / git / context / permission / plan / sessionId / version
```

Key points:

- **Context % comes from the snapshot** (`contextTokens / maxContextTokens`), not a guess.
- **Tools, subagents and todos** are parsed from the session's `wire.jsonl` — a structured event log with stable tool-call ids and `agent.turn.started/ended` lifecycle, so it's exact rather than heuristic. Read-only; no hooks are injected into your config.
- **Quota** reuses the same official endpoint the CLI itself uses (`GET /usages`, Bearer token from `~/.kimi-code/credentials/kimi-code.json`). The token never leaves your machine except to `api.kimi.com`. Results are cached on disk (300s by default); when the cache expires a detached background process refetches, so the status line itself never blocks on the network.
- Everything runs well inside the 300ms budget: a warm render takes ~50ms.

Kimi-specific adaptations (vs Cursor CLI / cursor-hud):

- **Single line, not multi-row** — Kimi renders only the first stdout line, so all segments are folded into one compact row.
- **No hooks side-channel** — Kimi Code's `wire.jsonl` already has structured tool and turn events.
- **Plan-usage bars became quota bars** — powered by Kimi's managed-usage API instead of Cursor's plan endpoints.

## Configuration

Run the configurator anytime:

```sh
python3 scripts/configure.py                      # guided
python3 scripts/configure.py --preset=full        # essential / full / minimal
python3 scripts/configure.py --set showQuota=false --set colors.model=#FF88FF
python3 scripts/configure.py --show               # print current config
```

Or edit `~/.kimi-code/kimi-hud/config.json` directly (see [fixtures/config.example.json](fixtures/config.example.json)). Invalid JSON silently falls back to defaults.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `pathLevels` | number \| `"full"` | 1 | Directory levels in the project path |
| `showModel` | boolean | true | Model badge |
| `showMode` | boolean | true | `⧉ Plan` / `⚡ yolo` / `◈ auto` badges |
| `showGit` / `showDirty` | boolean | true | Git branch + dirty `*` |
| `showContextBar` / `contextBarWidth` | boolean / number | true / 10 | Context usage bar |
| `showQuota` / `quotaCacheTtlS` / `quotaBarWidth` | — | true / 300 / 5 | Account quota bars |
| `showTodos` / `todoDoneTtlS` | boolean / number | true / 120 | Todo progress; how long an all-done list stays visible |
| `showTools` / `showCompletedTools` | boolean | true / false | Tool activity; `✓ Read ×3` tallies when idle |
| `toolsMaxVisible` / `toolNameMaxLength` | number | 4 / 0 | Cap shown tool groups (0 = no truncation) |
| `showAgents` / `agentNameMaxLength` | boolean / number | true / 12 | Subagent segment |
| `maxLineWidth` | number | 0 | Truncate beyond this width (0 = use `COLUMNS`) |
| `colors.*` | name or `"#RRGGBB"` | see example | Per-segment colors |
| `thresholds` | object | 25/50/75/90 | Context bar mid/high/warn/crit (%) |

Quota bars turn yellow at 70% and red at 90% (`colors.quotaOk/Warn/Crit`).

Colors example:

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

Color names: `black red green yellow blue magenta cyan white gray brightRed brightGreen brightYellow brightBlue brightMagenta brightCyan brightWhite textMuted`, or any `#RRGGBB` truecolor value.

## Disabling the HUD temporarily

```sh
KIMI_HUD_DISABLE=1 kimi
```

No need to touch `tui.toml`.

## Troubleshooting

**Footer still shows the built-in layout?**

- Run `/reload-tui` or start a new session after `setup.py`.
- Confirm `[status_line] command = "python3 .../kimi-hud.py"` in `~/.kimi-code/tui.toml`.
- The command may be failing silently (failures fall back to the built-in footer). Debug with:
  ```sh
  KIMI_HUD_CAPTURE=1 kimi   # stdin snapshots land in ~/.kimi-code/kimi-hud/capture/
  ```

**Quota segment missing?**

- Only appears for managed (logged-in) Kimi Code accounts.
- First fetch is asynchronous — give it a few seconds after starting a session.
- Set `showQuota=false` if you don't want the HUD to read your local OAuth token.

**Something looks stale after config changes?**

- Run `/reload-tui`, or start a new session.

## Development

```sh
python3 kimi-hud.py < fixtures/sample-stdin.json   # simulate one statusline call
python3 kimi-hud.py --fetch-quota                  # force a quota refresh
```

## Credits & inspiration

- [cursor-hud](https://github.com/huai-xia/cursor-hud) by huai-xia — the original statusline HUD for Cursor CLI; kimi-hud borrows the product idea and UX patterns, then reimplements them for Kimi Code.
- [claude-hud](https://github.com/jarrodwatts/claude-hud) by Jarrod Watts — the original statusline HUD for Claude Code.
- Independent project — not affiliated with Moonshot AI or any Cursor/Anthropic entity.

## License

MIT
