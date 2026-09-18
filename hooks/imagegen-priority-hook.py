#!/usr/bin/env python3
"""Inject imagegen-custom-env guidance for image-related UserPromptSubmit events.

The hook is intentionally advisory: it adds context, but cannot replace the
host's built-in image tool. It is safe for non-image prompts and never prints
credentials.
"""

from __future__ import annotations

import json
import re
import sys


IMAGE_INTENT = re.compile(
    r"(?:生成|创建|画图|绘图|绘制|制作|设计|渲染|编辑|修改|替换|移除|抠图|上色|修复|扩图|放大|裁剪|合成|图片|图像|照片|海报|插画|头像|generate|create|draw|image|picture|photo|poster|illustration|avatar|edit|replace|remove|background|inpaint|outpaint)",
    re.IGNORECASE,
)

CONTEXT = (
    "检测到图像生成或编辑意图。优先使用 $imagegen-custom-env 技能：先读取 "
    "其 SKILL.md 及官方 $imagegen 技能；由官方技能决定提示词、模型、参数、输出路径和验证；"
    "若存在完整自定义凭据，通过 imagegen_custom_env.py run -- 调用官方 image_gen.py。"
    "不要直接调用内置 image_gen 来绕过自定义 OPENAI_BASE_URL。"
)


def _prompt(data: dict) -> str:
    for key in ("prompt", "user_prompt", "text", "message"):
        value = data.get(key)
        if isinstance(value, str):
            return value
    return json.dumps(data, ensure_ascii=False)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print("{}")
        return 0
    if not isinstance(data, dict) or not IMAGE_INTENT.search(_prompt(data)):
        print("{}")
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": CONTEXT,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
