---
name: "imagegen-custom-env"
description: "Use the bundled Image Gen CLI with a custom OpenAI-compatible base URL and API key. This adapter only resolves and injects credentials; the imagegen workflow owns prompting, model and parameter choices, execution, retries, output handling, and validation."
---

# ImageGen Custom Env

Use this skill when an image generation or editing request should use custom OpenAI-compatible credentials. The executable CLI is bundled at `scripts/image_gen.py`.

## Ownership boundary

This Skill is self-contained for CLI execution. Treat this Skill and its bundled `scripts/image_gen.py` as the authority for:

- generate versus edit decisions;
- CLI workflow rules;
- prompts, models, parameters, masks, sizes, formats, and output paths;
- process handling, retries, fallback, inspection, validation, and reporting.

The wrapper owns credential discovery and launching the bundled CLI. Do not route execution through the host's separately installed imagegen Skill or its `image_gen.py`.

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

## Bundled workflow

Use this Skill's bundled CLI workflow to determine the task, prompt, arguments, and validation steps.

When a complete custom credential pair is available, the actual image request must use the bundled Image Gen CLI through this adapter, because the built-in image tool cannot receive a custom `OPENAI_BASE_URL`:

```bash
python3 "$CODEX_HOME/skills/imagegen-custom-env/scripts/imagegen_custom_env.py" run -- generate <imagegen-cli-arguments>
```

The adapter owns the interpreter and the path to the bundled `scripts/image_gen.py`. The first token after `--` must be the CLI subcommand `generate`, `edit`, or `generate-batch`; pass only the remaining CLI arguments after that subcommand. Do **not** put `python`, `python3`, or `image_gen.py` after `run --` (for example, never use `run -- python3 .../image_gen.py generate ...`). The adapter injects `OPENAI_BASE_URL` and `OPENAI_API_KEY`, then invokes the bundled CLI.

The bundled CLI accepts both standard OpenAI Images response forms: `data[].b64_json` and `data[].url`. URL responses are downloaded and then pass through the same local write and image-processing path as base64 responses.

Every non-dry-run generate, edit, or batch job validates that the output is a non-empty decodable image and, when an explicit size was requested, that the actual dimensions match it. A sibling `.receipt.json` records the run ID, absolute path, SHA-256, actual dimensions/format, and requested dimensions/format. A URL response may contain a different standard image format than requested; this is recorded rather than rejected.

Use `models` to inspect the configured endpoint's available models and `set-model <model>` to persist a validated local default. A per-request `--model` still takes precedence. This Skill intentionally supports synchronous image endpoints only; it does not implement a provider-specific async task protocol.

Do not routinely run `doctor`, `--help`, dry-run commands, source-file searches, directory inventories, or extra preflight checks. Use diagnostics only after a concrete credential or runtime failure. In particular, do not invent parameters such as `--input-fidelity`; use only arguments supported by the bundled CLI.

When no complete custom credential pair is available, stop applying the custom-endpoint path and report that credentials are missing. Do not silently switch to the host's separate imagegen CLI. If the adapter reports a credential, runtime, authentication, network, or provider failure, report that failure without routing to another imagegen implementation.

## Optional credential maintenance

These commands are maintenance tools, not normal generation steps:

- `doctor`: inspect credential sources or diagnose runtime problems.
- `persist-env --yes`: copy reusable credentials into the project `.env`; run only with explicit user approval.
- `setup-python --yes`, `set-python`, and `show-config`: repair or inspect the adapter runtime when a concrete runtime problem requires it.

For normal requests, report the credential source used and that the bundled CLI ran through `custom-cli`, together with the bundled workflow's image-result details.
