# imagegen-custom-env

[中文](README.md) · [English](README_EN.md) · [日本語](README_JP.md)

公式の `imagegen` ワークフローに、プロジェクト単位のカスタム認証情報と専用 Python ランタイム管理を追加する、独立インストール可能な Codex skill です。

## 必要条件

- Codex に組み込みの `imagegen` skill がインストールされていること。
- ラッパースクリプトの起動には Python 3.8 以降が必要です。画像生成用の依存関係は、skill が専用の Python 3.12 ランタイムとして構成できます。

## インストール

リポジトリを Codex の skills ディレクトリへ直接クローンします。

```bash
git clone <repository-url> "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env"
```

インストール後、skill が認識されるよう Codex を再起動してください。既存のインストールを更新するには、次を実行します。

```bash
git -C "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env" pull --ff-only
```

別の場所にリポジトリを置く場合は、シンボリックリンクも利用できます。

```bash
ln -s /absolute/path/to/imagegen-custom-env \
  "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env"
```

## 検証

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" doctor
```

生成時は `run` が専用 Python と公式 `image_gen.py` を自動的に選択します。
`--` の直後は `generate`、`edit`、または `generate-batch` から始め、
`python3` や `image_gen.py` のパスをもう一度渡さないでください。

リポジトリのルートがそのまま skill のルートです。`SKILL.md`、`agents/openai.yaml`、`scripts/imagegen_custom_env.py` はすべて必須の実行ファイルです。ローカルの秘密情報、管理対象の仮想環境、生成されたバイトコードはバージョン管理から除外されます。

## バージョン管理

セマンティックバージョンの Git タグでリリースします。例：

```bash
git tag -a v1.0.0 -m "imagegen-custom-env v1.0.0"
git push origin main --tags
```
