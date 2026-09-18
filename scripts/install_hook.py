#!/usr/bin/env python3
"""Install or remove the image priority hook without clobbering other hooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--hooks-file", type=Path, default=Path.home() / ".codex" / "hooks.json")
    args = parser.parse_args()
    action = "remove" if args.remove else "install"
    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("非交互环境请显式添加 --yes；未修改 hooks.json")
        answer = input(f"将{('移除' if args.remove else '安装')} UserPromptSubmit 图像优先 Hook，修改 {args.hooks_file}。继续？ [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("已取消，未修改 hooks.json")
            return 0
    source = Path(__file__).resolve().parents[1] / "hooks" / "imagegen-priority-hook.py"
    target = args.hooks_file.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    if not isinstance(data, dict):
        raise SystemExit("hooks file must contain a JSON object")
    events = data.setdefault("UserPromptSubmit", [])
    if not isinstance(events, list):
        raise SystemExit("UserPromptSubmit must be a JSON array")
    marker = "imagegen-custom-env/hooks/imagegen-priority-hook.py"
    events[:] = [entry for entry in events if marker not in json.dumps(entry, ensure_ascii=False)]
    if not args.remove:
        command = f"python3 {source}"
        events.append({"hooks": [{"type": "command", "command": command}]})
    if target.exists():
        shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(("Removed" if args.remove else "Installed") + f" imagegen priority hook in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
