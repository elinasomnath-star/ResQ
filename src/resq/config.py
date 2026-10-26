"""Load the region configuration without embedding study-area assumptions in code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # OSM ingestion should still run in restricted Python environments.
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimal_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if not value or value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        contents = value[1:-1].strip()
        return [] if not contents else [_minimal_yaml_scalar(part) for part in contents.split(",")]
    if value.startswith(("'", '"')) and value.endswith(value[0]):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Parse the simple mapping/list/scalar subset used by config/region.yaml."""
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        content = raw.split("#", 1)[0].rstrip()
        if content.strip():
            lines.append((len(content) - len(content.lstrip()), content.lstrip()))

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        is_list = lines[start][1].startswith("- ")
        result: Any = [] if is_list else {}
        index = start
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected YAML indentation near: {content}")
            if is_list:
                if not content.startswith("- "):
                    break
                result.append(_minimal_yaml_scalar(content[2:]))
                index += 1
                continue
            if content.startswith("- ") or ":" not in content:
                raise ValueError(f"Expected YAML key/value near: {content}")
            key, scalar = content.split(":", 1)
            scalar = scalar.strip()
            index += 1
            if scalar:
                result[key.strip()] = _minimal_yaml_scalar(scalar)
            elif index < len(lines) and lines[index][0] > current_indent:
                result[key.strip()], index = parse_block(index, lines[index][0])
            else:
                result[key.strip()] = None
        return result, index

    if not lines:
        raise ValueError("Configuration file is empty")
    parsed, end = parse_block(0, lines[0][0])
    if end != len(lines) or not isinstance(parsed, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return parsed


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML configuration and resolve its data paths against the repo root."""
    config_path = Path(path) if path is not None else REPO_ROOT / "config" / "region.yaml"
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path
    content = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(content) if yaml is not None else _minimal_yaml_load(content)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {config_path}")
    return config


def configured_path(value: str | Path) -> Path:
    """Resolve a config path relative to the repository root."""
    result = Path(value)
    return result if result.is_absolute() else REPO_ROOT / result
