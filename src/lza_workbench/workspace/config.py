from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from lza_workbench.workspace.schema import WorkspaceConfig

WORKSPACE_CONFIG_FILE = Path("lza-workspace.yaml")


def _get_config_path(workspace_dir: Path) -> Path:
    """Construct and normalize the absolute configuration file path from workspace root."""
    return workspace_dir.expanduser().resolve() / WORKSPACE_CONFIG_FILE


def load_workspace_config(workspace_dir: Path) -> WorkspaceConfig:
    """Read and validate lza-workspace.yaml from a given workspace directory."""
    path = _get_config_path(workspace_dir)
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        _reject_persisted_aws_secrets(data)
        return WorkspaceConfig.model_validate(data)
    except (OSError, YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace configuration {path}: {exc}") from exc


def _reject_persisted_aws_secrets(data: object) -> None:
    """Give existing workspaces a safe, actionable migration error for secret keys."""
    if not isinstance(data, dict) or not isinstance(aws := data.get("aws"), dict):
        return
    secret_fields = {
        "access_key",
        "secret_access_key",
        "aws_access_key_id",
        "aws_secret_access_key",
    }
    present = sorted(field for field in secret_fields if aws.get(field) is not None)
    if present:
        names = ", ".join(present)
        raise ValueError(
            f"AWS secret field(s) [{names}] are not supported in lza-workspace.yaml. "
            "Remove them and configure credentials externally through an AWS profile, "
            "environment, SSO, or an assumed role."
        )


def write_workspace_config(workspace_dir: Path, config: WorkspaceConfig) -> None:
    """Write validated workspace configuration into the workspace directory as YAML."""
    path = _get_config_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    yaml = YAML()
    yaml.default_flow_style = False
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(config.model_dump(mode="json"), handle)
