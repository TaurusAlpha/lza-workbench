from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from lza_workbench.workspace.models import WorkspaceConfig


def load_workspace_config(path: Path) -> WorkspaceConfig:
    """Read and validate lza-workspace.yaml."""
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        return WorkspaceConfig.model_validate(data)
    except (OSError, YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace configuration {path}: {exc}") from exc


def write_workspace_config(path: Path, config: WorkspaceConfig) -> None:
    """Write validated workspace configuration as reviewable YAML."""
    yaml = YAML()
    yaml.default_flow_style = False
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(config.model_dump(mode="json"), handle)
