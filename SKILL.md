---
name: "imagegen-custom-env"
description: "Use the official Image Gen skill with a custom OpenAI-compatible base URL and API key. This adapter only resolves and injects credentials; the official imagegen skill owns prompting, model and parameter choices, execution, retries, output handling, and validation."
---

# ImageGen Custom Env

Use this skill when an image generation or editing request should use custom OpenAI-compatible credentials.

## Ownership boundary

Before acting, read and follow the official `$imagegen` skill at `$CODEX_HOME/skills/.system/imagegen/SKILL.md`. Treat it as the authority for:

- generate versus edit decisions;
- built-in versus CLI workflow rules, except for the custom-credential override below;
- prompts, models, parameters, masks, sizes, formats, and output paths;
- process handling, retries, fallback, inspection, validation, and reporting.

This skill overrides only credential discovery and how the official CLI is launched. Do not create a second workflow, success gate, retry policy, run-state system, or output-validation checklist here. Do not add or remove official CLI arguments based on this skill.

## Credential resolution

Resolve `OPENAI_BASE_URL` and `OPENAI_API_KEY` independently in this order, filling a missing value from the next source:

1. The nearest project `.env` in the current directory or an ancestor.
2. The selected provider in the default Codex `config.toml`:
   - `base_url` -> `OPENAI_BASE_URL`
   - `experimental_bearer_token`, `api_key`, or `key` -> `OPENAI_API_KEY`, in that order
3. Platform-persistent environment:
   - macOS: `launchctl getenv`
   - Windows: persistent user/system environment variables
4. Current process environment.

Use custom credentials only when both values are present. Never print the complete API key.

## Official workflow handoff

Let the official `$imagegen` skill determine the task, prompt, arguments, and validation steps first.

When a complete custom credential pair is available, the only execution override is that the actual image request must use the official Image Gen CLI through this adapter, because the built-in image tool cannot receive a custom `OPENAI_BASE_URL`:

```bash
python3 "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" run -- generate <official-imagegen-cli-arguments>
```

The adapter owns the interpreter and the path to the official `image_gen.py`. The first token after `--` must be the official CLI subcommand `generate`, `edit`, or `generate-batch`; pass only the remaining CLI arguments after that subcommand. Do **not** put `python`, `python3`, or `image_gen.py` after `run --` (for example, never use `run -- python3 .../image_gen.py generate ...`). The adapter injects `OPENAI_BASE_URL` and `OPENAI_API_KEY`, then invokes the unmodified official `image_gen.py`.

Do not routinely run `doctor`, `--help`, dry-run commands, source-file searches, directory inventories, or extra preflight checks. Use diagnostics only after a concrete credential or runtime failure. In particular, do not invent parameters such as `--input-fidelity`; use only arguments selected under the official skill's current rules.

When no complete custom credential pair is available, stop applying this adapter and continue with the official `$imagegen` skill's normal top-level workflow. If the adapter reports a credential, runtime, authentication, network, or provider failure, follow the official skill's failure and fallback rules rather than defining new behavior here.

## Optional credential maintenance

These commands are maintenance tools, not normal generation steps:

- `doctor`: inspect credential sources or diagnose runtime problems.
- `persist-env --yes`: copy reusable credentials into the project `.env`; run only with explicit user approval.
- `setup-python --yes`, `set-python`, and `show-config`: repair or inspect the adapter runtime when a concrete runtime problem requires it.

For normal requests, report only the credential source used and that the official workflow ran through `custom-cli`; let the official `$imagegen` skill provide all image-result reporting.
