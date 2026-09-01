---
name: "imagegen-custom-env"
description: "Generate or edit raster images with the official Image Gen CLI and custom credentials. Prefer project .env, then the selected provider in the default Codex config.toml, then platform-persistent and process-global environment variables; fall back to the official built-in imagegen workflow when custom credentials are unavailable or fail."
---

# ImageGen Custom Env

Use this global skill as the default entry point for image generation and editing tasks whenever Codex should produce or modify raster images.

This skill is a thin wrapper around the official `$imagegen` skill. It keeps the same prompt, output, transparency, and CLI guardrails, but changes credential selection and top-level preference:

1. Project `.env` in the current workspace, nearest ancestor first.
2. The selected provider in the default Codex `config.toml` (`$CODEX_HOME/config.toml`, normally `~/.codex/config.toml` on macOS and Windows):
   - `base_url` becomes `OPENAI_BASE_URL`.
   - `experimental_bearer_token`, `api_key`, or `key` becomes `OPENAI_API_KEY`, in that order.
3. Platform global credentials:
   - macOS: `launchctl getenv`, then global environment variables
   - Windows: persistent user/system environment variables from the registry, then global environment variables
4. If no complete custom pair is available, or the custom endpoint/key fails, use the official `$imagegen` workflow instead.

This skill should be preferred over the built-in `$imagegen` skill for new sessions because it preserves the same workflow while adding project-aware credentials and a globally managed Python runtime.

## Required companion skill

Before acting, read the official `$imagegen` skill instructions and follow its workflow rules unless this skill explicitly overrides credential selection.

Official resources:
- `$CODEX_HOME/skills/.system/imagegen/SKILL.md`
- `$CODEX_HOME/skills/.system/imagegen/references/cli.md` when CLI/API/model controls are needed
- `$CODEX_HOME/skills/.system/imagegen/scripts/image_gen.py` as the underlying CLI

Do not modify the official `image_gen.py`.

## Custom credential behavior

Treat custom credentials as usable only when both variables are present:

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`

The project `.env` wins over every other source for keys it defines. Missing keys are filled from the selected Codex provider, then the platform/global sources. Only read `.env` from the current working directory or its ancestors; do not scan unrelated locations.

The `.env` parser intentionally supports simple dotenv lines:

```text
OPENAI_BASE_URL=https://example.test/v1
OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL="https://example.test/v1"
```

If `.env` provides only one of the two required variables, fill the missing variable from the next global source in priority order. Report the mixed sources briefly before running.

Credential source labels:

- `codex-config` — selected model provider in the default Codex `config.toml`
- `launchctl` — macOS launchd persistent environment
- `windows-env` — Windows registry user/system environment
- `global-env` — process global environment variables (`OPENAI_BASE_URL`, `OPENAI_API_KEY`)

## Execution

For this custom skill, change the top-level preference:

1. Resolve custom credentials.
2. If both `OPENAI_BASE_URL` and `OPENAI_API_KEY` are available, prefer the wrapper CLI path for generation and editing so the custom endpoint is actually used.
3. If custom credentials are missing or the custom call fails with a provider/auth/network error, fall back to the official `$imagegen` workflow and apply its normal built-in-vs-CLI decision tree.

Reason: the built-in image tool path does not accept a custom `OPENAI_BASE_URL`, so custom credentials can only be honored through the CLI wrapper.

When explicit CLI/API execution is appropriate, use the wrapper script instead of calling the official CLI directly:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" run -- generate \
  --prompt "A minimal product hero image of a ceramic mug" \
  --out output/imagegen/mug.png
```

The wrapper sets `OPENAI_BASE_URL` and `OPENAI_API_KEY` for the official CLI, then forwards all arguments after `--` to `image_gen.py`.

This skill also manages a global dedicated Python runtime for CLI fallback. Preferred Python resolution order:

1. `--python`
2. `IMAGEGEN_CUSTOM_ENV_PYTHON`
3. persisted global config at `$CODEX_HOME/state/imagegen-custom-env/config.json`
4. dedicated global venv at `$CODEX_HOME/state/imagegen-custom-env/venv`
5. discovered system Python candidates

If no compatible runtime exists, create and persist one with:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" setup-python --yes
```

If the dedicated runtime becomes incompatible after an official Image Gen upgrade, refresh it with:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" setup-python --reinstall --yes
```

`setup-python` requires `--yes` for explicit user-approved setup. Automatic first-use setup from `run` is allowed without `--yes`.

To pin an already-compatible interpreter globally:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" set-python /path/to/python
```

To inspect the saved runtime config:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" show-config
```

Useful self-check:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" doctor
```

Verbose Python compatibility check:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" doctor --verbose
```

Use `--dry-run` with forwarded CLI commands to validate payloads without making API calls:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" run -- generate \
  --prompt "Test image" \
  --out output/imagegen/test.png \
  --dry-run
```

On first custom-skill use, the wrapper should auto-check whether a compatible dedicated runtime exists. If it does not, it should attempt to create one for this skill only, using a dedicated venv under `$CODEX_HOME/state/imagegen-custom-env/venv`. If a dedicated venv exists but fails compatibility checks, auto-repair via reinstall is allowed during `run`. Prefer `uv` for Windows and macOS because it can provision a requested Python version before creating the venv. If `uv` is unavailable, fall back to stdlib `venv` and then validate compatibility.

`doctor` reports `runtime_status` and `runtime_remediation` when the dedicated runtime is missing or degraded.

To persist reusable project credentials from the external persistent source into the nearest project `.env` after the user grants permission:

```bash
python "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" persist-env --yes
```

Do not run `persist-env` silently. If project `.env` is missing or incomplete and the external persistent source has reusable values, ask the user for permission before copying them into the project `.env`. Without `--yes`, `persist-env` only prints a preview and exits with code 32.

## Fallback

If custom credentials are unavailable, incomplete, or the custom CLI call fails with an API/auth/network/provider error, do not keep retrying blindly. Tell the user that the custom endpoint path failed and continue with the official `$imagegen` default path when the request can be satisfied there.

If the only blocker is an incompatible Python runtime, fix that first with the global setup flow rather than downgrading the request immediately.

Do not treat local validation problems as custom-provider failures. Examples that should be fixed rather than falling back:

- missing `--prompt`
- invalid size/quality/model arguments
- missing input image files
- output file already exists without `--force`
- unsupported transparent-background options

## Reporting

When this skill runs, briefly state:

- which credential source was used: `.env`, `codex-config`, `launchctl`, `windows-env`, `global-env`, or mixed
- whether the final path used custom CLI credentials or official `$imagegen` fallback
- final saved output paths, following the official `$imagegen` output handling rules
