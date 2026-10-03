#!/usr/bin/env python3
"""Manage ~/.kimi-code/kimi-hud/config.json.

Usage:
  python3 scripts/configure.py                          # guided
  python3 scripts/configure.py --preset=essential
  python3 scripts/configure.py --set showTools=false --set colors.model=#FF88FF
  python3 scripts/configure.py --show
"""
import json
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = PROJECT_ROOT / "fixtures" / "config.example.json"
CFG = Path.home() / ".kimi-code" / "kimi-hud" / "config.json"

PRESETS = {
    "essential": {"showCompletedTools": False, "showAgents": True, "showTools": True, "contextBarWidth": 10},
    "full": {"showCompletedTools": True, "showAgents": True, "showTools": True, "contextBarWidth": 12},
    "minimal": {"showModel": True, "showGit": True, "showContextBar": True, "showTools": False, "showAgents": False},
}


def load() -> dict:
    if CFG.is_file():
        try:
            data = json.loads(CFG.read_text())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            print("[kimi-hud] existing config is invalid JSON; starting from the example")
    try:
        data = json.loads(EXAMPLE.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save(cfg: dict) -> None:
    CFG.parent.mkdir(parents=True, exist_ok=True)
    if CFG.is_file():
        shutil.copy2(CFG, f"{CFG}.bak-{int(time.time())}")
    CFG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"[kimi-hud] config written to {CFG}")
    print("[kimi-hud] run /reload-tui or start a new session if the footer looks stale")


def coerce(value: str):
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def set_path(cfg: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    o = cfg
    for k in keys[:-1]:
        if not isinstance(o.get(k), dict):
            o[k] = {}
        o = o[k]
    o[keys[-1]] = value


def main() -> None:
    args = sys.argv[1:]

    if "--show" in args:
        print(CFG.read_text() if CFG.is_file() else "(no config file yet)")
        return

    sets = []
    for i, a in enumerate(args):
        if a.startswith("--set="):
            sets.append(a[len("--set="):])
        elif a == "--set" and i + 1 < len(args):
            sets.append(args[i + 1])
    if sets:
        cfg = load()
        for s in sets:
            key, _, value = s.partition("=")
            set_path(cfg, key, coerce(value))
        save(cfg)
        return

    for a in args:
        if a.startswith("--preset="):
            name = a.split("=", 1)[1]
            if name not in PRESETS:
                sys.exit(f"[kimi-hud] unknown preset {name!r} (choose: {', '.join(PRESETS)})")
            save({**load(), **PRESETS[name]})
            return

    # guided
    cfg = load()
    preset = input("Preset (essential/full/minimal) [essential]: ").strip() or "essential"
    cfg.update(PRESETS.get(preset, PRESETS["essential"]))
    for key in ("showTools", "showAgents", "showCompletedTools", "showGit"):
        default = "y" if cfg.get(key, True) else "n"
        ans = input(f"{key} (y/n) [{default}]: ").strip().lower()
        if ans in ("y", "n"):
            cfg[key] = ans == "y"
    save(cfg)


if __name__ == "__main__":
    main()
