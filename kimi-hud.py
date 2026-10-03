#!/usr/bin/env python3
"""kimi-hud: real-time statusline HUD for Kimi Code CLI.

Reads the Kimi Code status_line JSON snapshot on stdin and prints a single
ANSI-colored line: model, path, git, context bar, tool activity, subagents.
Data source beyond the snapshot: ~/.kimi-code session wire.jsonl logs (read-only).

Env:
  KIMI_HUD_DISABLE=1   print nothing (footer falls back to built-in layout)
  KIMI_HUD_CAPTURE=1   dump the stdin snapshot to ~/.kimi-code/kimi-hud/capture/
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TAIL_BYTES = 512 * 1024
GIT_TTL_S = 2.0
GIT_TIMEOUT_S = 0.15

DEFAULT_CONFIG: dict = {
    "pathLevels": 1,
    "showModel": True,
    "showGit": True,
    "showDirty": True,
    "showContextBar": True,
    "contextBarWidth": 10,
    "showTools": True,
    "showCompletedTools": False,
    "showAgents": True,
    "showMode": True,
    "showTodos": True,
    "todoDoneTtlS": 120,
    "showQuota": True,
    "quotaCacheTtlS": 300,
    "quotaBarWidth": 5,
    "toolNameMaxLength": 0,
    "toolsMaxVisible": 4,
    "agentNameMaxLength": 12,
    "maxLineWidth": 0,
    "colors": {
        "model": "cyan",
        "path": "yellow",
        "git": "blue",
        "dirty": "red",
        "separator": "textMuted",
        "context": {"ok": "blue", "mid": "cyan", "high": "yellow", "warn": "magenta", "crit": "red"},
        "toolRunning": "yellow",
        "toolDone": "green",
        "agentRunning": "magenta",
        "agentDone": "green",
        "modePlan": "#E8A838",
        "modeAuto": "magenta",
        "modeYolo": "red",
        "todo": "cyan",
        "todoDone": "green",
        "quotaOk": "green",
        "quotaWarn": "yellow",
        "quotaCrit": "red",
        "text": "white",
    },
    "thresholds": {"mid": 25, "high": 50, "warn": 75, "crit": 90},
}

CODES = {
    "black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37, "gray": 90, "grey": 90,
    "textMuted": 90, "brightRed": 91, "brightGreen": 92, "brightYellow": 93,
    "brightBlue": 94, "brightMagenta": 95, "brightCyan": 96, "brightWhite": 97,
}

ESC = "\x1b"


def paint(spec: str, text: str) -> str:
    if not text:
        return text
    if spec.startswith("#") and len(spec) == 7:
        try:
            r, g, b = (int(spec[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return text
        return f"{ESC}[38;2;{r};{g};{b}m{text}{ESC}[0m"
    code = CODES.get(spec)
    if code is None:
        return text
    return f"{ESC}[{code}m{text}{ESC}[0m"


def plain(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == ESC and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] != "m":
                j += 1
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def truncate(text: str, max_len: int) -> str:
    if max_len <= 0 or len(plain(text)) <= max_len:
        return text
    return plain(text)[: max(0, max_len - 1)] + "…"


def bar(pct: float, width: int, color: str) -> str:
    clamped = min(100.0, max(0.0, pct))
    filled = round(clamped / 100 * width)
    return paint(color, "█" * filled + "░" * (width - filled))


def kimi_home() -> Path:
    return Path(os.environ.get("KIMI_CODE_HOME", Path.home() / ".kimi-code"))


QUOTA_WINDOWS = (("limit_5h", "5h"), ("limit_7d", "7d"), ("limit_month_total", "month"))


def quota_cache_path() -> Path:
    return kimi_home() / "kimi-hud" / "quota-cache.json"


def fetch_quota() -> dict:
    """Background entry point (--fetch-quota): call the managed usage API and cache it."""
    token_file = kimi_home() / "credentials" / "kimi-code.json"
    base = (os.environ.get("KIMI_CODE_BASE_URL") or "https://api.kimi.com/coding/v1").rstrip("/")
    out = {"fetchedAt": int(time.time())}
    try:
        token = json.loads(token_file.read_text()).get("access_token")
        if not token:
            raise ValueError("no access_token")
        import urllib.request

        req = urllib.request.Request(
            f"{base}/usages",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            payload = json.loads(res.read().decode("utf-8"))
        usages = payload.get("usages") if isinstance(payload, dict) else None
        out["usages"] = {
            key: entry.get("used_ratio")
            for key, _label in QUOTA_WINDOWS
            if isinstance(usages, dict)
            and isinstance(entry := usages.get(key), dict)
            and isinstance(entry.get("used_ratio"), (int, float))
        }
    except Exception as e:
        out["error"] = str(e)[:200]
    try:
        path = quota_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
        os.chmod(path, 0o600)
    except Exception:
        pass
    return out


def read_cached_quota(cfg: dict) -> dict | None:
    """Fresh cache -> usages; stale/missing -> spawn one background fetch, return None."""
    try:
        cache = json.loads(quota_cache_path().read_text())
        age = time.time() - cache.get("fetchedAt", 0)
        if age < cfg.get("quotaCacheTtlS", 300) and "usages" in cache:
            return cache["usages"]
        if cache.get("error") and age < 120:
            return None  # back off after errors
    except Exception:
        pass
    try:
        import subprocess

        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--fetch-quota"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
    return None


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = kimi_home() / "kimi-hud" / "config.json"
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in ("colors", "thresholds") and isinstance(v, dict):
                    cfg[k].update(v)
                    if k == "colors" and isinstance(v.get("context"), dict):
                        cfg["colors"]["context"].update(v["context"])
                else:
                    cfg[k] = v
    except Exception:
        pass
    return cfg


_git_cache: dict | None = None
_git_cache_at = 0.0


def git_info(cwd: str) -> dict:
    global _git_cache, _git_cache_at
    now = time.monotonic()
    if _git_cache and now - _git_cache_at < GIT_TTL_S:
        return _git_cache
    info = {"branch": None, "dirty": False}

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, timeout=GIT_TIMEOUT_S
        ).stdout.decode("utf-8", "replace").strip()

    try:
        branch = run("branch", "--show-current")
        info["branch"] = branch or None
        info["dirty"] = bool(run("status", "--porcelain"))
    except Exception:
        pass
    _git_cache, _git_cache_at = info, now
    return info


def resolve_session_dir(session_id: str, cwd: str | None) -> Path | None:
    home = kimi_home()
    index = home / "session_index.jsonl"
    try:
        for line in index.read_text().splitlines():
            if session_id not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("sessionId") == session_id and Path(rec["sessionDir"]).is_dir():
                return Path(rec["sessionDir"])
    except Exception:
        pass
    try:
        candidates = sorted(
            (p for p in (home / "sessions").glob(f"*/{session_id}") if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None
    except Exception:
        return None


def each_raw_line(path: Path):
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
            text = f.read().decode("utf-8", "replace")
    except Exception:
        return
    lines = text.splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # drop the possibly-truncated first line
    for line in lines:
        if '"type"' in line:
            yield line


def each_wire_event(path: Path):
    for line in each_raw_line(path):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        ev = e.get("event") if isinstance(e.get("event"), dict) else e
        yield ev, e.get("time")


def parse_main_transcript(wire: Path) -> dict:
    calls: list[tuple[str, str]] = []
    done: set[str] = set()
    for ev, _t in each_wire_event(wire):
        etype = ev.get("type")
        if etype == "tool.call":
            key = ev.get("toolCallId") or ev.get("uuid") or f"call-{len(calls)}"
            calls.append((ev.get("name") or "?", key))
        elif etype == "tool.result":
            key = ev.get("toolCallId") or ev.get("parentUuid")
            if key:
                done.add(key)
    running, completed = [], {}
    for name, key in calls:
        if key in done:
            completed[name] = completed.get(name, 0) + 1
        else:
            running.append(name)
    return {"running": running, "completed": completed}


def parse_agent_transcript(wire: Path, agent_id: str) -> dict:
    started_at, running = None, False
    for ev, t in each_wire_event(wire):
        etype = ev.get("type")
        if etype == "agent.turn.started":
            started_at = t or int(time.time() * 1000)
            running = True
        elif etype in ("agent.turn.ended", "turn.ended", "turn.aborted", "turn.failed"):
            running = False
    return {"label": agent_id, "running": running, "startedAt": started_at}


def parse_todos(wire: Path) -> dict | None:
    """Reconstruct todo state from the latest TodoList tool call in the wire log."""
    latest: list | None = None
    updated_at = None
    for line in each_raw_line(wire):
        if "TodoList" not in line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = e.get("event") if isinstance(e.get("event"), dict) else e
        todos = None
        if ev.get("type") == "tool.call" and isinstance(ev.get("args"), dict):
            todos = ev["args"].get("todos")
        else:
            msg = ev.get("message")
            content = msg.get("message", {}).get("content") if isinstance(msg, dict) else None
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    for tc in part.get("toolCalls") or []:
                        if not isinstance(tc, dict) or tc.get("name") != "TodoList":
                            continue
                        try:
                            args = json.loads(tc.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            continue
                        if isinstance(args.get("todos"), list) and args["todos"]:
                            todos = args["todos"]
        if isinstance(todos, list) and todos:
            latest = todos
            t = e.get("time")
            updated_at = t or updated_at
    if latest is None:
        return None
    return {
        "done": sum(1 for item in latest if item.get("status") == "done"),
        "total": len(latest),
        "inProgress": sum(1 for item in latest if item.get("status") == "in_progress"),
        "updatedAt": updated_at,
    }


def collect_state(session_dir: Path) -> dict:
    tools = {"running": [], "completed": {}}
    agents = []
    todos = None
    agents_dir = session_dir / "agents"
    try:
        entries = sorted(agents_dir.iterdir())
    except Exception:
        return {"tools": tools, "agents": agents, "todos": todos}
    for entry in entries:
        wire = entry / "wire.jsonl"
        if not wire.is_file():
            continue
        if entry.name == "main":
            tools = parse_main_transcript(wire)
            todos = parse_todos(wire)
        else:
            agents.append(parse_agent_transcript(wire, entry.name))
    return {"tools": tools, "agents": agents, "todos": todos}


def fmt_elapsed(started_at: int | None) -> str:
    if not started_at:
        return ""
    s = max(0, int(time.time() - started_at / 1000))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s}s"
    h, m = divmod(m, 60)
    return f"{h}h{m}m"


def shorten_path(cwd: str, levels) -> str:
    if levels == "full":
        return cwd
    parts = [p for p in cwd.split("/") if p]
    if not parts:
        return cwd
    n = max(1, int(levels)) if str(levels).isdigit() else 1
    return "/".join(parts[-n:])


def context_color(pct: float, cfg: dict) -> str:
    t, c = cfg["thresholds"], cfg["colors"]["context"]
    if pct >= t["crit"]:
        return c["crit"]
    if pct >= t["warn"]:
        return c["warn"]
    if pct >= t["high"]:
        return c["high"]
    if pct >= t["mid"]:
        return c["mid"]
    return c["ok"]


def render(snap: dict, cfg: dict, git: dict, state: dict) -> str:
    sep = paint(cfg["colors"]["separator"], "│")
    parts: list[str] = []

    if cfg["showModel"] and snap.get("model"):
        seg = paint(cfg["colors"]["model"], snap["model"])
        if cfg["showMode"]:
            badges = []
            if snap.get("planMode"):
                badges.append(paint(cfg["colors"]["modePlan"], "⧉ Plan"))
            mode = (snap.get("permissionMode") or "").lower()
            if mode == "yolo":
                badges.append(paint(cfg["colors"]["modeYolo"], "⚡ yolo"))
            elif mode == "auto":
                badges.append(paint(cfg["colors"]["modeAuto"], "◈ auto"))
            if badges:
                seg += " " + " ".join(badges)
        parts.append(seg)

    if snap.get("cwd"):
        parts.append(paint(cfg["colors"]["path"], shorten_path(snap["cwd"], cfg["pathLevels"])))

    if cfg["showGit"]:
        branch = snap.get("gitBranch") or git["branch"]
        if branch:
            seg = paint(cfg["colors"]["git"], branch)
            if cfg["showDirty"] and git["dirty"]:
                seg += paint(cfg["colors"]["dirty"], "*")
            parts.append(seg)

    ctx_tokens, ctx_max = snap.get("contextTokens"), snap.get("maxContextTokens")
    if cfg["showContextBar"] and ctx_tokens and ctx_max:
        pct = min(100.0, ctx_tokens / ctx_max * 100)
        color = context_color(pct, cfg)
        parts.append(f"{bar(pct, cfg['contextBarWidth'], color)} {paint(color, f'{round(pct)}%')}")

    todos = state.get("todos")
    if cfg["showTodos"] and todos:
        fresh = (
            todos["done"] < todos["total"]
            or not todos.get("updatedAt")
            or (time.time() * 1000 - todos["updatedAt"]) / 1000 < cfg.get("todoDoneTtlS", 120)
        )
        if fresh:
            color = cfg["colors"]["todoDone"] if todos["done"] == todos["total"] else cfg["colors"]["todo"]
            parts.append(paint(color, f"☰ {todos['done']}/{todos['total']}"))

    if cfg["showQuota"]:
        usages = read_cached_quota(cfg)
        if usages:
            segs = []
            for key, label in QUOTA_WINDOWS:
                ratio = usages.get(key)
                if ratio is None:
                    continue
                pct = min(100.0, max(0.0, ratio * 100))
                if pct >= 90:
                    color = cfg["colors"]["quotaCrit"]
                elif pct >= 70:
                    color = cfg["colors"]["quotaWarn"]
                else:
                    color = cfg["colors"]["quotaOk"]
                segs.append(f"{label} {bar(pct, cfg['quotaBarWidth'], color)}")
            if segs:
                parts.append(" ".join(segs))

    if cfg["showTools"]:
        tools = state["tools"]
        shown = []
        for name in tools["running"][: cfg["toolsMaxVisible"]]:
            if cfg["toolNameMaxLength"] > 0:
                name = truncate(name, cfg["toolNameMaxLength"])
            shown.append(f"{paint(cfg['colors']['toolRunning'], '▶')} {name}")
        if not tools["running"] and cfg["showCompletedTools"]:
            for name, count in list(tools["completed"].items())[-cfg["toolsMaxVisible"]:]:
                if cfg["toolNameMaxLength"] > 0:
                    name = truncate(name, cfg["toolNameMaxLength"])
                shown.append(f"{paint(cfg['colors']['toolDone'], '✓')} {name}{f' ×{count}' if count > 1 else ''}")
        if shown:
            parts.append(" ".join(shown))

    if cfg["showAgents"] and state["agents"]:
        multi = len(state["agents"]) >= 2
        segs = []
        for i, a in enumerate(state["agents"][:4]):
            label = truncate(a["label"], cfg["agentNameMaxLength"])
            tag = f"#{i + 1} {label}" if multi else label
            icon = paint(cfg["colors"]["agentRunning"], "◐") if a["running"] else paint(cfg["colors"]["agentDone"], "✓")
            elapsed = f" {fmt_elapsed(a['startedAt'])}" if a["running"] else ""
            segs.append(f"{icon} {tag}{elapsed}")
        extra = f" +{len(state['agents']) - 4}" if len(state["agents"]) > 4 else ""
        parts.append(f"🤖 {' '.join(segs)}{extra}")

    line = f" {sep} ".join(parts)
    width = cfg["maxLineWidth"] or int(os.environ.get("COLUMNS", "0") or 0)
    if width > 0 and len(plain(line)) > width:
        line = truncate(line, width)
    return line


def main() -> None:
    if "--fetch-quota" in sys.argv:
        fetch_quota()
        return
    if os.environ.get("KIMI_HUD_DISABLE") == "1":
        return
    raw = sys.stdin.read()
    if os.environ.get("KIMI_HUD_CAPTURE") == "1" and raw.strip():
        try:
            cap_dir = kimi_home() / "kimi-hud" / "capture"
            cap_dir.mkdir(parents=True, exist_ok=True)
            (cap_dir / f"stdin-{int(time.time() * 1000)}.json").write_text(raw)
        except Exception:
            pass
    try:
        snap = json.loads(raw)
    except json.JSONDecodeError:
        return  # empty stdout -> footer falls back to the built-in layout
    if not isinstance(snap, dict):
        return

    cfg = load_config()
    cwd = snap.get("cwd") or os.getcwd()
    git = git_info(cwd)

    state = {"tools": {"running": [], "completed": {}}, "agents": [], "todos": None}
    session_id = snap.get("sessionId")
    if session_id:
        session_dir = resolve_session_dir(session_id, cwd)
        if session_dir:
            state = collect_state(session_dir)

    line = render(snap, cfg, git, state)
    if line:
        sys.stdout.write(line + "\n")


if __name__ == "__main__":
    main()
