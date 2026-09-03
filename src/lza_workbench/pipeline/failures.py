"""Pipeline failure interpretation shared by monitoring and status workflows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PipelineActionFailure:
    """Action failure with normalized diagnostics and optional resource attribution."""

    stage_name: str | None
    action_name: str
    summary: str | None
    error_message: str | None
    external_execution_id: str | None
    external_execution_url: str | None
    diagnostic_details: list[str]
    raw_diagnostic_details: list[str]
    failed_resource: str | None


def collect_pipeline_action_failures(
    stages: Iterable[Any],
    *,
    fetch_diagnostics: Callable[[str], list[str]],
    normalize_diagnostic: Callable[[str], tuple[str, str | None]],
) -> list[PipelineActionFailure]:
    """Collect failed actions and derive concise, normalized root-cause diagnostics."""
    failures: list[PipelineActionFailure] = []
    for stage in stages:
        stage_name = getattr(stage, "stage_name", None)
        for action in getattr(stage, "actions", []):
            if getattr(action, "status", None) != "Failed":
                continue

            external_execution_id = getattr(action, "external_execution_id", None)
            diagnostics = fetch_diagnostics(external_execution_id) if external_execution_id else []
            raw_diagnostics = list(diagnostics)
            normalized_diagnostics: list[str] = []
            failed_resource: str | None = None

            if diagnostics:
                for diagnostic in diagnostics:
                    normalized, resource = normalize_diagnostic(diagnostic)
                    if resource and not failed_resource:
                        failed_resource = resource
                    if normalized and normalized not in normalized_diagnostics:
                        normalized_diagnostics.append(normalized)
            else:
                raw_error = getattr(action, "error_message", None) or getattr(
                    action, "summary", None
                )
                if raw_error:
                    raw_text = str(raw_error)
                    raw_diagnostics = [raw_text]
                    normalized, resource = normalize_diagnostic(raw_text)
                    if resource:
                        failed_resource = resource
                    normalized_diagnostics = [normalized] if normalized else [raw_text]

            failures.append(
                PipelineActionFailure(
                    stage_name=stage_name,
                    action_name=getattr(action, "action_name", ""),
                    summary=getattr(action, "summary", None),
                    error_message=getattr(action, "error_message", None),
                    external_execution_id=external_execution_id,
                    external_execution_url=getattr(action, "external_execution_url", None),
                    diagnostic_details=normalized_diagnostics,
                    raw_diagnostic_details=raw_diagnostics,
                    failed_resource=failed_resource,
                )
            )
    return failures


__all__ = ["PipelineActionFailure", "collect_pipeline_action_failures"]
