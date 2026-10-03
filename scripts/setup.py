#!/usr/bin/env python3
"""Write (or remove) the [status_line] entry in ~/.kimi-code/tui.toml.

Usage:
  python3 scripts/setup.py           # install
  python3 scripts/setup.py --remove  # uninstall
"""
import re
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMMAND = f"python3 {PROJECT_ROOT / 'kimi-hud.py'}"
HOME = Path.home() / ".kimi-code"
TUI = HOME / "tui.toml"

if "--remove" not in sys.argv and not (PROJECT_ROOT / "kimi-hud.py").is_file():
    sys.exit(f"[kimi-hud] {PROJECT_ROOT / 'kimi-hud.py'} not found")

text = TUI.read_text() if TUI.is_file() else ""
if TUI.is_file():
    shutil.copy2(TUI, f"{TUI}.kimi-hud-bak-{int(time.time())}")

SECTION = re.compile(r"^\[status_line\]\s*$")
TABLE = re.compile(r"^\[.*\]\s*$")

if "--remove" in sys.argv:
    if not SECTION.search(text):
        print("[kimi-hud] no [status_line] section found; nothing to remove.")
        sys.exit(0)
    out, in_section = [], False
    for line in text.splitlines():
        if TABLE.match(line) and not SECTION.match(line):
            in_section = False
        if SECTION.match(line):
            in_section = True
            continue
        if not in_section or not line.startswith("command"):
            out.append(line)
    TUI.write_text("\n".join(out).replace("\n\n\n", "\n\n"))
    print(f"[kimi-hud] removed status_line.command from {TUI} (backup kept)")
    print("[kimi-hud] run /reload-tui or start a new session to apply")
    sys.exit(0)

if SECTION.search(text):
    out, in_section, replaced = [], False, False
    for line in text.splitlines():
        if TABLE.match(line):
            in_section = bool(SECTION.match(line))
        if in_section and line.startswith("command"):
            line = f'command = "{COMMAND}"'
            replaced = True
        out.append(line)
    if not replaced:
        idx = next(i for i, l in enumerate(out) if SECTION.match(l))
        out.insert(idx + 1, f'command = "{COMMAND}"')
    text = "\n".join(out) + "\n"
else:
    if text.strip() and not text.endswith("\n"):
        text += "\n"
    text += f'\n[status_line]\ncommand = "{COMMAND}"\n'

TUI.write_text(text)
print(f"[kimi-hud] wrote status_line.command to {TUI}")
print(f"[kimi-hud] command = {COMMAND}")
print("[kimi-hud] run /reload-tui or start a new session to apply")
print("[kimi-hud] disable temporarily with: KIMI_HUD_DISABLE=1 kimi")
