# imagegen-custom-env

[中文](README.md) · [English](README_EN.md) · [日本語](README_JP.md)

这是一个可独立安装的 Codex skill，为官方 `imagegen` 工作流增加项目级自定义凭据支持和专用 Python 运行时管理。

## 环境要求

- 已安装 Codex 内置的 `imagegen` skill。
- 启动包装脚本需要 Python 3.8 或更高版本。图像生成依赖可由 skill 自动配置专用 Python 3.12 运行时。

## 安装

直接将仓库克隆到 Codex skills 目录：

```bash
git clone <repository-url> "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env"
```

安装后重启 Codex，使其发现该 skill。更新已有安装：

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env" pull --ff-only
```

如果希望将仓库保存在其他位置，也可以使用符号链接：

```bash
ln -s /absolute/path/to/imagegen-custom-env \
  "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env"
```

## 验证

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" doctor
```

实际生成时，`run` 会自行选择专用 Python 并定位官方 `image_gen.py`。因此 `--` 后必须直接从
`generate`、`edit` 或 `generate-batch` 开始；不要再次传入 `python3` 或 `image_gen.py` 路径：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" run -- generate \
  --prompt "A misty mountain sunrise" --out output/imagegen/misty-mountain-sunrise.png
```

## 可选：安装图像优先 Hook

仓库附带一个宿主级 `UserPromptSubmit` Hook。Skill 更新/克隆**不会自动修改宿主配置**；
首次安装 Hook 时，安装器会先申请确认，确认后才写入。它只在检测到图像生成/编辑意图时注入
`$imagegen-custom-env` 优先规则，不会覆盖已有 Hook，也不能强制替换宿主内置的
`image_gen` 工具。安装前请确认你希望修改 `~/.codex/hooks.json`：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/install_hook.py"
```

上面的命令可从任意目录执行。非交互环境（例如脚本、CI）不会擅自写入，需显式确认：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/install_hook.py" --yes
```

脚本会先创建 `hooks.json.bak`；移除本项目 Hook（保留其他 Hook）可运行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/install_hook.py" --remove
```

修改宿主 Hook 后请重启 Codex。若当前宿主不支持 `hookSpecificOutput`，该 Hook 会安全地
返回空对象，不影响普通请求。

仓库根目录就是 skill 根目录。`SKILL.md`、`agents/openai.yaml` 和 `scripts/imagegen_custom_env.py` 均为必需运行文件。本地密钥、专用虚拟环境和生成的字节码不会纳入版本控制。

## 版本管理

使用语义化版本 Git 标签发布，例如：

```bash
git tag -a v1.0.0 -m "imagegen-custom-env v1.0.0"
git push origin main --tags
```
