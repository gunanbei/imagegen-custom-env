#!/usr/bin/env python3
"""Run this skill's bundled imagegen CLI with custom OpenAI env vars."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - exercised on older supported Pythons
    tomllib = None
import ast
import re
import venv
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REQUIRED_KEYS = ("OPENAI_BASE_URL", "OPENAI_API_KEY")
CONFIG_DIR_NAME = "imagegen-custom-env"
CONFIG_FILE_NAME = "config.json"
DEFAULT_VENV_DIR_NAME = "venv"
DEFAULT_PYTHON_REQUEST = "3.12"
PYTHON_PACKAGES = ("openai", "pillow")
EXIT_NEEDS_CONFIRMATION = 32
EXIT_DEGRADED_RUNTIME = 33
FALLBACK_PATTERNS = (
    "api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "connection",
    "connect",
    "timeout",
    "timed out",
    "tls",
    "ssl",
    "dns",
    "name or service not known",
    "no address associated",
    "bad gateway",
    "service unavailable",
    "internal server error",
    "not found",
    "404",
    "401",
    "403",
    "429",
    "500",
    "502",
    "503",
    "504",
    "rate limit",
)


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def _bundled_cli() -> Path:
    # Keep the executable image workflow inside this skill; runtime execution
    # does not depend on a separately installed host skill.
    return _skill_root() / "scripts" / "image_gen.py"


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _config_dir() -> Path:
    return _codex_home() / "state" / CONFIG_DIR_NAME


def _config_path() -> Path:
    return _config_dir() / CONFIG_FILE_NAME


def _default_venv_path() -> Path:
    return _config_dir() / DEFAULT_VENV_DIR_NAME


def _venv_python_path(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _path_exists(value: Optional[str]) -> bool:
    return bool(value and Path(value).expanduser().exists())


def _load_config() -> Dict[str, str]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _save_config(config: Dict[str, str]) -> None:
    directory = _config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _config_path().write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate_pythons(explicit: Optional[str]) -> List[str]:
    config = _load_config()
    candidates: List[str] = []
    seen = set()

    def add(value: Optional[str]) -> None:
        if not value:
            return
        if value in seen:
            return
        seen.add(value)
        candidates.append(value)

    add(explicit)
    add(os.environ.get("IMAGEGEN_CUSTOM_ENV_PYTHON"))
    add(config.get("python"))
    add(str(_venv_python_path(_default_venv_path())))
    add(sys.executable)
    if os.name == "nt":
        add(shutil.which("python.exe"))
        add(shutil.which("python3.exe"))
        add(shutil.which("py.exe"))
    else:
        add(shutil.which("python3.13"))
        add(shutil.which("python3.12"))
        add(shutil.which("python3"))
        add("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3")
        add("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")
        add("/opt/homebrew/bin/python3")
        add("/usr/local/bin/python3")
        add("/usr/bin/python3")
    return candidates


def _python_capability(python_exe: str) -> Tuple[bool, str]:
    if not _path_exists(python_exe):
        return False, "not found"
    command = [
        python_exe,
        "-c",
        (
            "import importlib.util, inspect, json, sys; "
            "spec=importlib.util.find_spec('openai'); "
            "status={'ok': False, 'reason': 'openai missing'}; "
            "print(json.dumps(status)) if not spec else None; "
            "pillow=importlib.util.find_spec('PIL'); "
            "status={'ok': False, 'reason': 'pillow missing'}; "
            "print(json.dumps(status)) if not pillow else None; "
            "import openai; "
            "import PIL; "
            "from openai import OpenAI; "
            "g=str(inspect.signature(OpenAI().images.generate)); "
            "e=str(inspect.signature(OpenAI().images.edit)); "
            "ok=('output_format' in g and 'quality' in g and 'background' in g and 'output_format' in e and 'quality' in e); "
            "reason=f\"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; openai {getattr(openai, '__version__', 'unknown')}; pillow {getattr(PIL, '__version__', 'unknown')}\"; "
            "status={'ok': ok, 'reason': reason if ok else reason + ' lacks required image params'}; "
            "print(json.dumps(status))"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "sk-dummy")},
        )
    except OSError as exc:
        return False, f"unusable ({exc})"
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        return False, f"unusable ({detail})"
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception:
        detail = completed.stdout.strip() or "invalid capability output"
        return False, f"unusable ({detail})"
    ok = bool(payload.get("ok"))
    reason = str(payload.get("reason") or ("compatible" if ok else "incompatible"))
    return ok, reason


def _resolve_python(explicit: Optional[str]) -> Tuple[Optional[str], List[Tuple[str, bool, str]]]:
    checks: List[Tuple[str, bool, str]] = []
    for candidate in _candidate_pythons(explicit):
        ok, reason = _python_capability(candidate)
        checks.append((candidate, ok, reason))
        if ok:
            return candidate, checks
    return None, checks


def _python_executable(explicit: Optional[str]) -> str:
    resolved, _checks = _resolve_python(explicit)
    if resolved:
        return resolved
    if explicit:
        return explicit
    return os.environ.get("IMAGEGEN_CUSTOM_ENV_PYTHON") or sys.executable


def _run(command: Sequence[str], *, cwd: Optional[Path] = None) -> int:
    print("Running: " + shlex.join([str(part) for part in command]), file=sys.stderr)
    env = os.environ.copy()
    if command and Path(str(command[0])).name == "uv":
        uv_cache = _config_dir() / "uv-cache"
        uv_cache.mkdir(parents=True, exist_ok=True)
        env.setdefault("UV_CACHE_DIR", str(uv_cache))
    completed = subprocess.run([str(part) for part in command], cwd=str(cwd) if cwd else None, check=False, env=env)
    return completed.returncode


def _install_packages(python_exe: Path) -> int:
    uv = shutil.which("uv")
    if uv:
        code = _run([uv, "pip", "install", "--python", str(python_exe), "-U", *PYTHON_PACKAGES])
        if code == 0:
            return 0
        print("uv pip install failed; falling back to python -m pip.", file=sys.stderr)
    return _run([str(python_exe), "-m", "pip", "install", "-U", *PYTHON_PACKAGES])


def _create_venv_with_uv(target: Path, python_request: str) -> Optional[Path]:
    uv = shutil.which("uv")
    if not uv:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    code = _run([uv, "venv", str(target), "--python", python_request, "--seed", "--allow-existing", "--no-project"])
    if code != 0:
        code = _run([uv, "python", "install", python_request])
        if code != 0:
            return None
        code = _run([uv, "venv", str(target), "--python", python_request, "--seed", "--allow-existing", "--no-project"])
    if code != 0:
        return None
    return _venv_python_path(target)


def _create_venv_with_stdlib(target: Path) -> Optional[Path]:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(str(target))
    except Exception as exc:
        print(f"stdlib venv creation failed: {exc}", file=sys.stderr)
        return None
    return _venv_python_path(target)


def _configure_python(python_exe: Path) -> int:
    if not python_exe.is_file():
        print(f"Failed to create python runtime at {python_exe}", file=sys.stderr)
        return 2
    code = _install_packages(python_exe)
    if code != 0:
        return code
    ok, reason = _python_capability(str(python_exe))
    if not ok:
        print(f"Installed runtime is still incompatible: {reason}", file=sys.stderr)
        return 31
    config = _load_config()
    config["python"] = str(python_exe)
    config["python_source"] = "imagegen-custom-env"
    config["platform"] = platform.system() or os.name
    _save_config(config)
    print(f"Configured global imagegen python: {python_exe}")
    return 0


def _find_project_env(start: Path) -> Optional[Path]:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _strip_inline_comment(value: str) -> str:
    quote: Optional[str] = None
    escaped = False
    for idx, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "#" and (idx == 0 or value[idx - 1].isspace()):
            return value[:idx].rstrip()
    return value.strip()


def _parse_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in REQUIRED_KEYS:
            continue
        value = _strip_inline_comment(value.strip())
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]
        if value:
            values[key] = value
    return values


GLOBAL_ENV_SOURCE = "global-env"
WINDOWS_ENV_SOURCE = "windows-env"
LAUNCHCTL_SOURCE = "launchctl"
CODEX_CONFIG_SOURCE = "codex-config"
EXTERNAL_SOURCES = frozenset(
    {CODEX_CONFIG_SOURCE, GLOBAL_ENV_SOURCE, WINDOWS_ENV_SOURCE, LAUNCHCTL_SOURCE}
)


def _codex_config_path() -> Path:
    """Return the active/default Codex config path on macOS and Windows."""
    return _codex_home() / "config.toml"


def _minimal_toml_loads(text: str) -> Dict[str, object]:
    """Parse the small provider subset needed on Python versions without tomllib."""
    result: Dict[str, object] = {}
    section: Dict[str, object] = result
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"\[([^\]]+)\]", line)
        if match:
            section = result
            for part in match.group(1).split("."):
                section = section.setdefault(part.strip().strip('"'), {})  # type: ignore[assignment]
            continue
        if "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        key = key.strip('"')
        try:
            value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError):
            value = raw_value.strip('"')
        section[key] = value
    return result


def _codex_config_credentials() -> Dict[str, Tuple[str, str]]:
    """Read image endpoint credentials from the selected Codex model provider."""
    path = _codex_config_path()
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        if tomllib is not None:
            data = tomllib.loads(text)
        else:
            data = _minimal_toml_loads(text)
    except (OSError, UnicodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    provider_name = data.get("model_provider")
    providers = data.get("model_providers")
    if not isinstance(provider_name, str) or not isinstance(providers, dict):
        return {}
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return {}

    source = f"{CODEX_CONFIG_SOURCE}:{path}#{provider_name}"
    resolved: Dict[str, Tuple[str, str]] = {}
    base_url = provider.get("base_url")
    if isinstance(base_url, str) and base_url.strip():
        resolved["OPENAI_BASE_URL"] = (base_url.strip(), source)

    for field in ("experimental_bearer_token", "api_key", "key"):
        value = provider.get(field)
        if isinstance(value, str) and value.strip():
            resolved["OPENAI_API_KEY"] = (value.strip(), source)
            break
    return resolved


def _launchctl_getenv(key: str) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["launchctl", "getenv", key],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _global_env_getenv(key: str) -> Optional[str]:
    value = os.environ.get(key)
    if value and value.strip():
        return value.strip()
    return None


def _windows_registry_getenv(key: str) -> Optional[str]:
    try:
        import winreg
    except ImportError:
        return None

    for hive, subkey in (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as handle:
                value, _value_type = winreg.QueryValueEx(handle, key)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_platform_credential(key: str) -> Optional[Tuple[str, str]]:
    if os.name == "nt":
        value = _windows_registry_getenv(key)
        if value:
            return value, WINDOWS_ENV_SOURCE
    else:
        value = _launchctl_getenv(key)
        if value:
            return value, LAUNCHCTL_SOURCE

    value = _global_env_getenv(key)
    if value:
        return value, GLOBAL_ENV_SOURCE
    return None


def _fallback_credential_values() -> Dict[str, Tuple[str, str]]:
    config_values = _codex_config_credentials()
    values: Dict[str, Tuple[str, str]] = {}
    for key in REQUIRED_KEYS:
        resolved = config_values.get(key) or _resolve_platform_credential(key)
        if resolved:
            values[key] = resolved
    return values


def _collect_env(cwd: Path) -> Tuple[Dict[str, str], Dict[str, str], Optional[Path]]:
    env_values: Dict[str, str] = {}
    sources: Dict[str, str] = {}

    dotenv_path = _find_project_env(cwd)
    dotenv_values = _parse_dotenv(dotenv_path) if dotenv_path else {}
    for key in REQUIRED_KEYS:
        if key in dotenv_values:
            env_values[key] = dotenv_values[key]
            sources[key] = f".env:{dotenv_path}"

    for key in REQUIRED_KEYS:
        if key in env_values:
            continue
        resolved = _codex_config_credentials().get(key) or _resolve_platform_credential(key)
        if resolved:
            env_values[key], sources[key] = resolved

    return env_values, sources, dotenv_path


def _project_env_target(cwd: Path, dotenv_path: Optional[Path]) -> Path:
    if dotenv_path:
        return dotenv_path
    current = cwd.resolve()
    if current.is_file():
        current = current.parent
    return current / ".env"


def _quote_dotenv(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_dotenv_values(path: Path, values: Dict[str, str], *, overwrite: bool) -> List[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    written: List[str] = []
    seen = set()
    output: List[str] = []
    for raw in original:
        stripped = raw.strip()
        candidate = stripped[len("export ") :].lstrip() if stripped.startswith("export ") else stripped
        key = candidate.split("=", 1)[0].strip() if "=" in candidate else ""
        if key in values:
            seen.add(key)
            if overwrite:
                output.append(f"{key}={_quote_dotenv(values[key])}")
                written.append(key)
            else:
                output.append(raw)
            continue
        output.append(raw)
    for key in REQUIRED_KEYS:
        if key in values and key not in seen:
            if output and output[-1].strip():
                output.append("")
            output.append(f"{key}={_quote_dotenv(values[key])}")
            written.append(key)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return written


def _persistable_project_values(cwd: Path, *, overwrite: bool = False) -> Tuple[Dict[str, str], Dict[str, str], Optional[Path]]:
    _env_values, _sources, dotenv_path = _collect_env(cwd)
    target = _project_env_target(cwd, dotenv_path)
    existing = _parse_dotenv(target) if target.is_file() else {}
    values: Dict[str, str] = {}
    value_sources: Dict[str, str] = {}
    fallback_values = _fallback_credential_values()
    for key in REQUIRED_KEYS:
        if existing.get(key) and not overwrite:
            continue
        resolved = fallback_values.get(key)
        if resolved:
            values[key], value_sources[key] = resolved
    return values, value_sources, target


def _source_label(sources: Dict[str, str]) -> str:
    if not sources:
        return "none"
    source_set = set(sources.values())
    if len(source_set) == 1:
        only = next(iter(source_set))
        return ".env" if only.startswith(".env:") else only
    return "mixed (" + ", ".join(f"{key}={sources[key]}" for key in REQUIRED_KEYS if key in sources) + ")"


def _has_complete_custom_env(values: Dict[str, str]) -> bool:
    return all(values.get(key) for key in REQUIRED_KEYS)


def _configured_model() -> str:
    return _load_config().get("model", "gpt-image-2")


def _models_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


def models(args: argparse.Namespace) -> int:
    values, _sources, _dotenv = _collect_env(Path(args.cwd))
    if not _has_complete_custom_env(values):
        print("Custom image endpoint credentials are unavailable.", file=sys.stderr)
        return 20
    request = Request(_models_endpoint(values["OPENAI_BASE_URL"]), headers={"Authorization": f"Bearer {values['OPENAI_API_KEY']}"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Failed to query models: {exc}", file=sys.stderr)
        return 21
    model_ids = sorted({str(item if isinstance(item, str) else item.get("id")) for item in payload.get("data", []) if (isinstance(item, str) or isinstance(item, dict)) and (item if isinstance(item, str) else item.get("id"))})
    print(json.dumps({"current_model": _configured_model(), "models": model_ids}, indent=2, ensure_ascii=False))
    return 0


def set_model(args: argparse.Namespace) -> int:
    requested = args.model_name.strip()
    if not requested:
        print("Model name cannot be empty.", file=sys.stderr)
        return 2
    values, _sources, _dotenv = _collect_env(Path(args.cwd))
    if not _has_complete_custom_env(values):
        print("Custom image endpoint credentials are unavailable.", file=sys.stderr)
        return 20
    request = Request(_models_endpoint(values["OPENAI_BASE_URL"]), headers={"Authorization": f"Bearer {values['OPENAI_API_KEY']}"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Failed to query models: {exc}", file=sys.stderr)
        return 21
    model_ids = {str(item if isinstance(item, str) else item.get("id")) for item in payload.get("data", []) if (isinstance(item, str) or isinstance(item, dict)) and (item if isinstance(item, str) else item.get("id"))}
    if requested not in model_ids:
        print(f"Model not found upstream: {requested}", file=sys.stderr)
        return 22
    config = _load_config(); config["model"] = requested; _save_config(config)
    print(f"Configured default image model: {requested}")
    return 0


def _is_dry_run(forwarded_args: Iterable[str]) -> bool:
    return "--dry-run" in set(forwarded_args)


def _looks_like_provider_failure(returncode: int, stderr: str) -> bool:
    if returncode == 0:
        return False
    lower = stderr.lower()
    return any(pattern in lower for pattern in FALLBACK_PATTERNS)


def _dedicated_venv_python() -> str:
    return str(_venv_python_path(_default_venv_path()))


def _is_degraded_runtime(checks: List[Tuple[str, bool, str]]) -> bool:
    dedicated = _dedicated_venv_python()
    if not _default_venv_path().exists():
        return False
    for candidate, ok, _reason in checks:
        if candidate == dedicated and not ok:
            return True
    configured = _load_config().get("python")
    if configured:
        for candidate, ok, _reason in checks:
            if candidate == configured and not ok:
                return True
    return False


def _classify_runtime_status(checks: List[Tuple[str, bool, str]]) -> Tuple[str, str]:
    if any(ok for _candidate, ok, _reason in checks):
        return "ok", ""

    dedicated = _dedicated_venv_python()
    degraded_reasons: List[str] = []
    for candidate, ok, reason in checks:
        if ok:
            continue
        if candidate == dedicated or candidate == _load_config().get("python"):
            degraded_reasons.append(reason)

    if degraded_reasons:
        joined = "; ".join(degraded_reasons)
        if any(
            marker in joined
            for marker in ("lacks required image params", "openai missing", "pillow missing")
        ):
            return (
                "degraded-sdk",
                "Run `setup-python --reinstall --yes` to refresh the dedicated runtime packages.",
            )
        return (
            "degraded-venv",
            "Run `setup-python --reinstall --yes` to repair the dedicated runtime.",
        )

    if _default_venv_path().exists():
        return (
            "degraded-venv",
            "Run `setup-python --reinstall --yes` to repair the dedicated runtime.",
        )

    return (
        "missing",
        "Run `setup-python --yes` to create the dedicated global runtime.",
    )


def _print_runtime_guidance(checks: List[Tuple[str, bool, str]], *, stream=sys.stderr) -> Tuple[str, str]:
    status, hint = _classify_runtime_status(checks)
    if status != "ok":
        print(f"runtime_status: {status}", file=stream)
        print(f"runtime_remediation: {hint}", file=stream)
    return status, hint


def _preview_confirmation(action: str, lines: Sequence[str]) -> None:
    print(f"Confirmation required before {action}.", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print("Re-run the same command with --yes after the user approves.", file=sys.stderr)


def _ensure_runtime(explicit: Optional[str], *, install: bool) -> Tuple[Optional[str], List[Tuple[str, bool, str]], int]:
    resolved, checks = _resolve_python(explicit)
    if resolved:
        return resolved, checks, 0
    if not install:
        status, _hint = _print_runtime_guidance(checks)
        return None, checks, EXIT_DEGRADED_RUNTIME if status.startswith("degraded") else 30

    reinstall = _is_degraded_runtime(checks)
    code = setup_python(
        argparse.Namespace(
            venv_path=None,
            python_request=DEFAULT_PYTHON_REQUEST,
            reinstall=reinstall,
            yes=True,
            auto_install=True,
        )
    )
    if code != 0:
        _print_runtime_guidance(checks)
        return None, checks, code
    resolved, checks = _resolve_python(explicit)
    if resolved:
        return resolved, checks, 0
    _print_runtime_guidance(checks)
    status, _hint = _classify_runtime_status(checks)
    return None, checks, EXIT_DEGRADED_RUNTIME if status.startswith("degraded") else 30


def doctor(args: argparse.Namespace) -> int:
    env_values, sources, dotenv_path = _collect_env(Path(args.cwd))
    resolved_python, checks = _resolve_python(args.python)
    persist_values, persist_sources, persist_target = _persistable_project_values(Path(args.cwd))
    print(f"cwd: {Path(args.cwd).resolve()}")
    print(f"project_env: {dotenv_path or 'not found'}")
    print(f"python: {resolved_python or 'not found'}")
    print(f"source: {_source_label(sources)}")
    for key in REQUIRED_KEYS:
        value = env_values.get(key)
        if key == "OPENAI_API_KEY" and value:
            shown = value[:7] + "..." if len(value) > 10 else "***"
        else:
            shown = value or "missing"
        print(f"{key}: {shown} ({sources.get(key, 'missing')})")
    if not _bundled_cli().is_file():
        print(f"bundled_cli: missing at {_bundled_cli()}", file=sys.stderr)
        return 2
    print(f"bundled_cli: {_bundled_cli()}")
    if args.verbose:
        for candidate, ok, reason in checks:
            marker = "ok" if ok else "no"
            print(f"python_check[{marker}]: {candidate} :: {reason}")
        if persist_values:
            print(
                "persistable_project_env: "
                + ", ".join(f"{key}<-{persist_sources[key]}" for key in REQUIRED_KEYS if key in persist_values)
                + f" -> {persist_target}"
            )
        else:
            print("persistable_project_env: none")
    if resolved_python is None:
        status, hint = _print_runtime_guidance(checks, stream=sys.stdout)
        print(f"python_status: {status}", file=sys.stderr)
        if status.startswith("degraded"):
            return EXIT_DEGRADED_RUNTIME
        return 3
    runtime_status, _hint = _classify_runtime_status(checks)
    if runtime_status == "ok":
        print("runtime_status: ok")
    return 0 if _has_complete_custom_env(env_values) else 1


def run(args: argparse.Namespace) -> int:
    cli = _bundled_cli()
    if not cli.is_file():
        print(f"Bundled imagegen CLI not found: {cli}", file=sys.stderr)
        return 2

    python_exe, checks, code = _ensure_runtime(args.python, install=not getattr(args, "no_auto_setup", False))
    if python_exe is None:
        print(
            "No compatible Python runtime found for the bundled imagegen CLI.",
            file=sys.stderr,
        )
        for candidate, ok, reason in checks:
            marker = "ok" if ok else "no"
            print(f"python_check[{marker}]: {candidate} :: {reason}", file=sys.stderr)
        return code or 30

    env_values, sources, dotenv_path = _collect_env(Path(args.cwd))
    if not _has_complete_custom_env(env_values):
        missing = ", ".join(key for key in REQUIRED_KEYS if not env_values.get(key))
        print(
            "Custom image endpoint credentials are unavailable "
            f"(missing: {missing}). Custom-endpoint execution cannot continue.",
            file=sys.stderr,
        )
        persist_values, persist_sources, persist_target = _persistable_project_values(Path(args.cwd))
        if persist_values and any(
            src.startswith(tuple(EXTERNAL_SOURCES)) for src in persist_sources.values()
        ):
            keys = ", ".join(key for key in REQUIRED_KEYS if key in persist_values)
            source_summary = ", ".join(
                sorted({persist_sources[key] for key in REQUIRED_KEYS if key in persist_values})
            )
            print(
                f"Tip: fallback credentials ({source_summary}) are available for this project. "
                f"After user approval, run `persist-env --yes` to copy {keys} into {persist_target}.",
                file=sys.stderr,
            )
        return 20

    run_env = os.environ.copy()
    run_env.update({key: env_values[key] for key in REQUIRED_KEYS})
    run_env["IMAGE_MODEL"] = _configured_model()
    source_label = _source_label(sources)
    missing_in_env = [
        key
        for key in REQUIRED_KEYS
        if sources.get(key, "").startswith(tuple(EXTERNAL_SOURCES))
    ]
    if missing_in_env:
        source_summary = ", ".join(sorted({sources[key] for key in missing_in_env}))
        print(
            "Project .env is missing "
            + ", ".join(missing_in_env)
            + f". After user approval, run `persist-env --yes` so future sessions in this project do not need {source_summary} lookup.",
            file=sys.stderr,
        )
    print(f"Using custom image endpoint credentials from {source_label}.", file=sys.stderr)

    command = [python_exe, str(cli), *args.imagegen_args]
    completed = subprocess.run(
        command,
        env=run_env,
        cwd=args.cwd,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode == 0 or _is_dry_run(args.imagegen_args):
        return completed.returncode

    if "indeterminate" in (completed.stderr + "\n" + completed.stdout).lower():
        return 24
    if _looks_like_provider_failure(completed.returncode, completed.stderr + "\n" + completed.stdout):
        print(
            "Custom image endpoint failed with an API/auth/network/provider error. "
            "Bundled imagegen execution cannot continue for this request.",
            file=sys.stderr,
        )
        return 21
    return completed.returncode


def setup_python(args: argparse.Namespace) -> int:
    target = Path(args.venv_path or _default_venv_path()).expanduser()
    python_request = args.python_request or DEFAULT_PYTHON_REQUEST
    reinstall = bool(getattr(args, "reinstall", False))
    auto_install = bool(getattr(args, "auto_install", False))

    if not getattr(args, "yes", False) and not auto_install:
        action = "refresh the dedicated runtime" if reinstall else "create the dedicated runtime"
        _preview_confirmation(
            action,
            [
                f"venv: {target}",
                f"python_request: {python_request}",
                f"reinstall: {reinstall}",
                "scope: global, only for imagegen-custom-env",
            ],
        )
        return EXIT_NEEDS_CONFIRMATION

    if reinstall and target.exists():
        print(
            f"Reinstall requested for {target}. Existing files will be reused when possible and packages will be refreshed.",
            file=sys.stderr,
        )

    python_exe = _create_venv_with_uv(target, python_request)
    if python_exe is None:
        print(
            "uv-managed runtime setup was unavailable or failed; falling back to stdlib venv in the current interpreter.",
            file=sys.stderr,
        )
        python_exe = _create_venv_with_stdlib(target)
    if python_exe is None:
        return 2
    return _configure_python(python_exe)


def set_python(args: argparse.Namespace) -> int:
    target = str(Path(args.python_path).expanduser())
    ok, reason = _python_capability(target)
    if not ok:
        print(f"Refusing to save incompatible python: {reason}", file=sys.stderr)
        return 31
    config = _load_config()
    config["python"] = target
    config["python_source"] = "user"
    config["platform"] = platform.system() or os.name
    _save_config(config)
    print(f"Configured global imagegen python: {target}")
    return 0


def persist_env(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd)
    values, sources, target = _persistable_project_values(cwd, overwrite=bool(args.overwrite))
    if not values:
        print(f"No fallback credentials need to be persisted to {target}.")
        return 0

    overwrite = bool(args.overwrite)
    if not overwrite and not args.missing_only:
        args.missing_only = True

    if not getattr(args, "yes", False):
        preview_lines = [
            f"target: {target}",
            f"overwrite: {overwrite}",
            f"missing_only: {bool(args.missing_only)}",
        ]
        for key in REQUIRED_KEYS:
            if key not in values:
                continue
            if key == "OPENAI_API_KEY":
                shown = values[key][:7] + "..." if len(values[key]) > 10 else "***"
            else:
                shown = values[key]
            preview_lines.append(f"{key} <- {sources.get(key, 'global')} = {shown}")
        _preview_confirmation("persist credentials into the project .env", preview_lines)
        return EXIT_NEEDS_CONFIRMATION

    written = _write_dotenv_values(target, values, overwrite=overwrite)
    if not written:
        print(f"No .env changes were needed for {target}.")
        return 0
    detail = ", ".join(f"{key}<-{sources[key]}" for key in written if key in sources)
    print(f"Persisted {', '.join(written)} to {target} ({detail}).")
    return 0


def show_config(_args: argparse.Namespace) -> int:
    config = _load_config()
    print(json.dumps(config, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve custom OpenAI image env vars and run the bundled imagegen CLI.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Project directory used to find .env and run the imagegen CLI.",
    )
    parser.add_argument(
        "--python",
        help="Python executable used to run the bundled imagegen CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Show resolved credential sources.")
    doctor_parser.add_argument("--verbose", action="store_true", help="Show all python compatibility checks.")
    doctor_parser.set_defaults(func=doctor)

    run_parser = subparsers.add_parser("run", help="Run bundled imagegen CLI with custom env.")
    run_parser.add_argument(
        "imagegen_args",
        nargs=argparse.REMAINDER,
        help="Arguments for image_gen.py. Put -- before the subcommand.",
    )
    run_parser.add_argument(
        "--no-auto-setup",
        action="store_true",
        help="Do not attempt automatic dedicated runtime setup when no compatible python is available.",
    )
    run_parser.set_defaults(func=run)

    models_parser = subparsers.add_parser("models", help="List models exposed by the configured endpoint.")
    models_parser.set_defaults(func=models)

    set_model_parser = subparsers.add_parser("set-model", help="Set the local default model after upstream validation.")
    set_model_parser.add_argument("model_name")
    set_model_parser.set_defaults(func=set_model)

    setup_parser = subparsers.add_parser(
        "setup-python",
        help="Create a dedicated global python runtime and install compatible dependencies.",
    )
    setup_parser.add_argument(
        "--venv-path",
        help="Custom venv path. Defaults to the skill state directory under CODEX_HOME.",
    )
    setup_parser.add_argument(
        "--python-request",
        default=DEFAULT_PYTHON_REQUEST,
        help="Requested Python version for uv-managed setup. Defaults to 3.12.",
    )
    setup_parser.add_argument(
        "--reinstall",
        action="store_true",
        help="Refresh the dedicated runtime even when the target venv already exists.",
    )
    setup_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm runtime creation or refresh. Without this flag, setup-python only prints a preview.",
    )
    setup_parser.set_defaults(func=setup_python)

    set_parser = subparsers.add_parser(
        "set-python",
        help="Persist a compatible python executable for this skill.",
    )
    set_parser.add_argument("python_path", help="Python executable to validate and persist.")
    set_parser.set_defaults(func=set_python)

    config_parser = subparsers.add_parser("show-config", help="Show persisted global config.")
    config_parser.set_defaults(func=show_config)

    persist_parser = subparsers.add_parser(
        "persist-env",
        help="Copy reusable external credentials into the project .env file.",
    )
    persist_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing OPENAI_BASE_URL and OPENAI_API_KEY entries in the project .env file.",
    )
    persist_parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Write only keys that are currently missing from the project .env file.",
    )
    persist_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm writing credentials into the project .env. Without this flag, persist-env only prints a preview.",
    )
    persist_parser.set_defaults(func=persist_env)
    return parser


def _normalize_remainder(args: List[str]) -> List[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _validate_forwarded_args(args: Sequence[str]) -> Optional[str]:
    """Reject a second interpreter/script prefix before argparse sees it.

    ``run`` owns both the Python interpreter and the bundled ``image_gen.py``
    path.  Everything after ``--`` must therefore be image_gen.py *arguments*
    and start with one of its subcommands, not another ``python`` invocation.
    Keeping this check here turns the otherwise confusing ``invalid choice:
    'python3'`` error into an actionable invocation error.
    """
    if not args:
        return "run requires imagegen arguments after -- (generate, edit, or generate-batch)"

    first = str(args[0])
    first_name = Path(first).name.lower()
    interpreter_names = {"python", "python3", "python3.11", "python3.12", "python3.13"}
    if first_name in interpreter_names or first_name.startswith("python3."):
        return (
            "do not pass a Python executable after `run --`; the adapter selects it automatically. "
            "Use `run -- generate ...`"
        )
    if first_name == "image_gen.py":
        return (
            "do not pass the image_gen.py path after `run --`; the adapter locates it automatically. "
            "Use `run -- generate ...`"
        )
    if first not in {"generate", "edit", "generate-batch"}:
        return (
            f"unexpected first imagegen argument {first!r}; expected `generate`, `edit`, or `generate-batch`"
        )
    return None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "imagegen_args"):
        args.imagegen_args = _normalize_remainder(args.imagegen_args)
        validation_error = _validate_forwarded_args(args.imagegen_args)
        if validation_error:
            parser.error(validation_error)
        print(
            "Forwarding to bundled imagegen CLI: "
            + shlex.join([str(_bundled_cli()), *args.imagegen_args]),
            file=sys.stderr,
        )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
