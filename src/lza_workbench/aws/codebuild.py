"""AWS CodeBuild and CloudWatch Logs service adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class CodeBuildLogConfig:
    """Observed CodeBuild CloudWatch log stream configuration."""

    group_name: str | None = None
    stream_name: str | None = None


@dataclass(frozen=True)
class CodeBuildPhaseContext:
    """Status context within a CodeBuild phase."""

    status_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class CodeBuildPhase:
    """Execution status and contexts for a specific build phase."""

    phase_type: str | None = None
    phase_status: str | None = None
    contexts: list[CodeBuildPhaseContext] = field(default_factory=list)


@dataclass(frozen=True)
class CodeBuildBuildObservation:
    """Typed observation of a CodeBuild build execution."""

    build_id: str
    exists: bool
    build_status: str | None = None
    current_phase: str | None = None
    logs: CodeBuildLogConfig = field(default_factory=CodeBuildLogConfig)
    phases: list[CodeBuildPhase] = field(default_factory=list)


def get_codebuild_build_info(
    *,
    client: Any,
    build_id: str,
) -> CodeBuildBuildObservation:
    """Fetch CodeBuild build metadata including logs location and phase details."""
    clean_id = (build_id or "").strip()
    if not clean_id:
        return CodeBuildBuildObservation(build_id="", exists=False)

    try:
        response = client.batch_get_builds(ids=[clean_id])
        builds = response.get("builds", [])
        if not builds:
            return CodeBuildBuildObservation(build_id=clean_id, exists=False)
        raw = builds[0]
        logs_raw = raw.get("logs") or {}
        log_config = CodeBuildLogConfig(
            group_name=logs_raw.get("groupName"),
            stream_name=logs_raw.get("streamName"),
        )
        phases: list[CodeBuildPhase] = []
        for p in raw.get("phases", []):
            contexts = [
                CodeBuildPhaseContext(
                    status_code=ctx.get("statusCode"),
                    message=ctx.get("message"),
                )
                for ctx in p.get("contexts", [])
            ]
            phases.append(
                CodeBuildPhase(
                    phase_type=p.get("phaseType"),
                    phase_status=p.get("phaseStatus"),
                    contexts=contexts,
                )
            )
        return CodeBuildBuildObservation(
            build_id=clean_id,
            exists=True,
            build_status=raw.get("buildStatus"),
            current_phase=raw.get("currentPhase"),
            logs=log_config,
            phases=phases,
        )
    except (ClientError, BotoCoreError):
        return CodeBuildBuildObservation(build_id=clean_id, exists=False)


def get_cloudwatch_log_events(
    *,
    client: Any,
    log_group_name: str,
    log_stream_name: str,
    limit: int = 150,
) -> list[str]:
    """Fetch the most recent log events from a CloudWatch log stream."""
    clean_group = (log_group_name or "").strip()
    clean_stream = (log_stream_name or "").strip()
    if not clean_group or not clean_stream:
        return []

    try:
        response = client.get_log_events(
            logGroupName=clean_group,
            logStreamName=clean_stream,
            startFromHead=False,
            limit=limit,
        )
        events = response.get("events", [])
        return [e.get("message", "") for e in events if e.get("message")]
    except (ClientError, BotoCoreError):
        return []


__all__ = [
    "CodeBuildBuildObservation",
    "CodeBuildLogConfig",
    "CodeBuildPhase",
    "CodeBuildPhaseContext",
    "get_cloudwatch_log_events",
    "get_codebuild_build_info",
]
