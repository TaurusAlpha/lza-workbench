"""AWS CodeBuild and CloudWatch Logs diagnostic utilities."""

from __future__ import annotations

import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


def extract_log_error_diagnostics(
    log_lines: list[str],
    *,
    max_messages: int = 5,
) -> list[str]:
    """Extract actionable failure diagnostics and error messages from raw log lines."""
    if not log_lines:
        return []

    high_priority_matches: list[str] = []
    standard_matches: list[str] = []
    seen_cleaned: set[str] = set()

    for raw_line in log_lines:
        line = raw_line.strip()
        if not line:
            continue

        cleaned = re.sub(
            r"^\[Container\]\s+\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+", "", line
        )

        if "Parameter 'CloudFormationExecutionPolicies' is not referenced" in cleaned:
            continue

        if (
            "❌" in cleaned
            or ("| error |" in cleaned and "failed:" in cleaned)
            or "ValidationError:" in cleaned
            or "StackPolicyException:" in cleaned
            or "ResourceStatusReason:" in cleaned
        ):
            if cleaned not in seen_cleaned:
                seen_cleaned.add(cleaned)
                high_priority_matches.append(cleaned)
        elif (
            "| error |" in cleaned
            or "Command failed with exit code" in cleaned
            or "State: FAILED" in cleaned
            or "COMMAND_EXECUTION_ERROR" in cleaned
            or ("Error:" in cleaned and not cleaned.startswith("info"))
        ):
            if cleaned not in seen_cleaned:
                seen_cleaned.add(cleaned)
                standard_matches.append(cleaned)

    results = list(high_priority_matches) if high_priority_matches else list(standard_matches)
    if high_priority_matches and len(high_priority_matches) < max_messages:
        for m in standard_matches:
            if m not in results and len(results) < max_messages:
                results.append(m)

    return results[:max_messages]


def get_codebuild_build_info(
    *,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
    build_id: str,
) -> dict[str, Any]:
    """Fetch CodeBuild build metadata including logs location and phase details."""
    clean_id = (build_id or "").strip()
    if not clean_id:
        return {}

    codebuild = (
        client if client is not None else (factory.get_client("codebuild") if factory else None)
    )
    if codebuild is None:
        return {}

    try:
        response = codebuild.batch_get_builds(ids=[clean_id])
        builds = response.get("builds", [])
        if not builds:
            return {}
        return dict(builds[0])
    except (ClientError, BotoCoreError):
        return {}


def get_cloudwatch_log_events(
    *,
    logs_client: Any | None = None,
    factory: AwsClientFactory | None = None,
    log_group_name: str,
    log_stream_name: str,
    limit: int = 150,
) -> list[str]:
    """Fetch the most recent log events from a CloudWatch log stream."""
    clean_group = (log_group_name or "").strip()
    clean_stream = (log_stream_name or "").strip()
    if not clean_group or not clean_stream:
        return []

    logs = (
        logs_client
        if logs_client is not None
        else (factory.get_client("logs") if factory else None)
    )
    if logs is None:
        return []

    try:
        response = logs.get_log_events(
            logGroupName=clean_group,
            logStreamName=clean_stream,
            startFromHead=False,
            limit=limit,
        )
        events = response.get("events", [])
        return [e.get("message", "") for e in events if e.get("message")]
    except (ClientError, BotoCoreError):
        return []


def fetch_codebuild_diagnostics(
    *,
    factory: AwsClientFactory | None = None,
    codebuild_client: Any | None = None,
    logs_client: Any | None = None,
    build_id: str,
    max_messages: int = 5,
) -> list[str]:
    """Fetch high-signal error diagnostics from CodeBuild and CloudWatch Logs."""
    build_info = get_codebuild_build_info(
        client=codebuild_client,
        factory=factory,
        build_id=build_id,
    )
    if not build_info:
        return []

    logs_cfg = build_info.get("logs", {})
    group_name = logs_cfg.get("groupName")
    stream_name = logs_cfg.get("streamName")

    if group_name and stream_name:
        log_lines = get_cloudwatch_log_events(
            logs_client=logs_client,
            factory=factory,
            log_group_name=group_name,
            log_stream_name=stream_name,
            limit=150,
        )
        extracted = extract_log_error_diagnostics(log_lines, max_messages=max_messages)
        if extracted:
            return extracted

    phase_errors: list[str] = []
    for phase in build_info.get("phases", []):
        if phase.get("phaseStatus") == "FAILED":
            for ctx in phase.get("contexts", []):
                msg = ctx.get("message")
                if msg and msg not in phase_errors:
                    phase_errors.append(msg)

    return phase_errors[:max_messages]


__all__ = [
    "extract_log_error_diagnostics",
    "fetch_codebuild_diagnostics",
    "get_cloudwatch_log_events",
    "get_codebuild_build_info",
]
