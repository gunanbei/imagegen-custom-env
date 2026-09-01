# imagegen-custom-env

这是一个可独立安装的 Codex skill，为官方 `imagegen` 工作流增加项目级自定义凭据支持和专用 Python 运行时管理。

## 环境要求

- 已安装 Codex 内置的 `imagegen` skill。
- 启动包装脚本需要 Python 3.11 或更高版本。图像生成依赖可由 skill 自动配置专用 Python 3.12 运行时。

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
python "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" doctor
```

仓库根目录就是 skill 根目录。`SKILL.md`、`agents/openai.yaml` 和 `scripts/imagegen_custom_env.py` 均为必需运行文件。本地密钥、专用虚拟环境和生成的字节码不会纳入版本控制。

## 版本管理

使用语义化版本 Git 标签发布，例如：

```bash
git tag -a v1.0.0 -m "imagegen-custom-env v1.0.0"
git push origin main --tags
```

