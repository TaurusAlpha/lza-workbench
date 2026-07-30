"""Project metadata and generated file serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from ruamel.yaml import YAML

INSTALLER_STACK_NAME = "AWSAccelerator-InstallerStack"


class InstallerSettings(BaseModel):
    """Installer defaults persisted for later commands."""

    control_tower_enabled: bool = True
    enable_approval_stage: bool = True
    enable_diagnostics_pack: bool = True
    anonymous_data: bool = False


class InitRequest(BaseModel):
    """Resolved inputs for initializing a customer workspace."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    customer_name: str
    customer_slug: str
    workspace_dir: Path
    project_dir: Path
    aws_profile: str
    aws_region: str
    lza_version: str
    template_source: str
    template_source_type: str
    template_config_dir: Path
    dry_run: bool = False
    force: bool = False
    skip_aws_check: bool = False
    installer: InstallerSettings = InstallerSettings()


class ImportRequest(BaseModel):
    """Resolved inputs for importing an existing customer workspace."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    customer_name: str
    customer_slug: str
    workspace_dir: Path
    project_dir: Path
    aws_profile: str
    aws_region: str
    lza_version: str
    template_source: str
    template_source_type: str = "local"
    template_config_dir: Path
    dry_run: bool = False
    installer: InstallerSettings = InstallerSettings()


def project_metadata(request: InitRequest | ImportRequest) -> dict[str, Any]:
    return {
        "customer": {
            "name": request.customer_name,
            "slug": request.customer_slug,
        },
        "aws": {
            "profile": request.aws_profile,
            "region": request.aws_region,
        },
        "lza": {
            "version": request.lza_version,
            "accelerator_prefix": "AWSAccelerator",
            "config_repository_location": "s3",
            "template_source_type": request.template_source_type,
            "template_source": request.template_source,
        },
        "installer": request.installer.model_dump(),
    }


def state_metadata(request: InitRequest | ImportRequest) -> dict[str, Any]:
    return {
        "customer": request.customer_slug,
        "lza_version": request.lza_version,
        "aws_profile": request.aws_profile,
        "aws_region": request.aws_region,
        "installer_stack_name": INSTALLER_STACK_NAME,
        "config_location": "s3",
        "last_pipeline_execution_id": None,
    }


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
