#!/usr/bin/env python3
"""Install or remove the image priority hook without clobbering other hooks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys


MARKER = "imagegen-priority-hook.py"


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def _python_command(script: Path, windows: bool = False) -> str:
    """Return a Codex command for the target platform.

    Codex selects ``commandWindows`` on Windows. Keep the regular command
    POSIX-compatible so the same hooks.json can be copied between hosts.
    """
    if windows:
        return f'py -3 "{script}"'
    return f'python3 "{script}"'


def _hook_entry(installed: Path) -> dict:
    return {
        "hooks": [{
            "type": "command",
            "command": _python_command(installed),
            "commandWindows": _python_command(installed, windows=True),
            "timeout": 5,
        }]
    }


def _events(data: dict) -> list:
    container = data["hooks"] if isinstance(data.get("hooks"), dict) else data
    events = container.setdefault("UserPromptSubmit", [])
    if not isinstance(events, list):
        raise SystemExit("hooks.UserPromptSubmit must be a JSON array")
    return events


def _contains_marker(value: object) -> bool:
    return MARKER in json.dumps(value, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--hooks-file", type=Path, help="Codex hooks.json path")
    args = parser.parse_args()
    action = "remove" if args.remove else "install"
    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("非交互环境请显式添加 --yes；未修改 hooks.json")
        answer = input(f"将{('移除' if args.remove else '安装')} UserPromptSubmit 图像优先 Hook，修改 {args.hooks_file}。继续？ [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("已取消，未修改 hooks.json")
            return 0
    source = Path(__file__).resolve().parents[1] / "hooks" / MARKER
    codex_home = _codex_home()
    target = (args.hooks_file or codex_home / "hooks.json").expanduser()
    installed = target.parent / "hooks" / MARKER
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    if not isinstance(data, dict):
        raise SystemExit("hooks file must contain a JSON object")
    events = _events(data)
    events[:] = [entry for entry in events if not _contains_marker(entry)]
    if not args.remove:
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, installed)
        installed.chmod(installed.stat().st_mode | 0o111)
        events.append(_hook_entry(installed))
    elif installed.exists():
        installed.unlink()
    if target.exists():
        shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(("Removed" if args.remove else "Installed") + f" imagegen priority hook in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
