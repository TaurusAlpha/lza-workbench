"""AWS CodeBuild and CloudWatch Logs diagnostic utilities."""

from __future__ import annotations

import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


def _clean_log_line(raw_line: str) -> str:
    """Strip prefixes, timestamps, log-level wrappers, and ANSI escapes from a log line."""
    line = raw_line.strip()
    if not line:
        return ""

    # Strip ANSI escape sequences
    line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line)

    # Strip [Container] timestamp prefix
    line = re.sub(
        r"^\[Container\]\s+\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+", "", line
    )

    # Strip ISO timestamps and toolkit/log level prefixes
    # e.g. "2026-08-23 16:47:44.027 | error |" or "2026-08-23 | error |"
    line = re.sub(
        r"^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\s*(?:\|\s*(?:error|warn|info)\s*\|\s*(?:toolkit\s*\|\s*)?)?",
        "",
        line,
        flags=re.IGNORECASE,
    )



    # Strip leading log prefixes like "[ERROR]", "[error]", "ERROR:", "Deployment of Stack failed: "
    prefix_pat = (
        r"^(?:\[(?:ERROR|error|WARN|warn|INFO|info)\]\s*|"
        r"ERROR:\s*|Deployment of Stack failed:\s*|Deployment of (?:Stack )?)+"
    )
    line = re.sub(prefix_pat, "", line, flags=re.IGNORECASE)


    # Strip leading presentation emojis like ❌, ✖
    line = re.sub(r"^[❌✖⚠️❗\s]+", "", line)

    # Normalize double spaces
    line = re.sub(r"\s+", " ", line).strip()
    return line


def normalize_root_cause_and_resource(raw_error: str) -> tuple[str, str | None]:
    """Normalize a diagnostic error line by stripping wrapper artifacts and extracting resource."""
    msg = _clean_log_line(raw_error)
    if not msg:
        return ("", None)

    failed_resource: str | None = None

    # Check for pattern "<Resource/StackName> failed: <ErrorDetails>"
    res_match = re.match(
        r"^(?P<resource>[A-Za-z0-9_\-]+(?:Stack|Resource|Project)[A-Za-z0-9_\-]*)\s+failed:\s*(?P<error>.*)$",
        msg,
        flags=re.IGNORECASE,
    )
    if res_match:
        failed_resource = res_match.group("resource")
        err = res_match.group("error").strip()
        # Clean nested emojis or "Deployment of ... failed"
        err = re.sub(r"^[❌✖⚠️❗\s]+", "", err).strip()
        err = re.sub(
            r"^(?:Deployment of (?:Stack )?(?:[\w\-]+ )?failed:\s*)+",
            "",
            err,
            flags=re.IGNORECASE,
        ).strip()
        # Clean nested "<resource> failed: " if duplicated
        if failed_resource and err.startswith(f"{failed_resource} failed:"):
            err = err[len(failed_resource) + 8 :].strip()
        msg = _clean_log_line(err)

    # Clean generic "DeploymentError: Resource updates failed:" prefix if more details follow
    if re.search(r"^DeploymentError:\s*Resource updates failed:\s*.+", msg, flags=re.IGNORECASE):
        msg = re.sub(
            r"^DeploymentError:\s*Resource updates failed:\s*", "", msg, flags=re.IGNORECASE
        ).strip()

    # Clean leading stack name path prefix from resource
    # (e.g. "StackName/LogicalResourceId" -> "LogicalResourceId")
    if failed_resource:
        msg = re.sub(rf"^{re.escape(failed_resource)}/", "", msg)

    # Clean duplicated custom resource type in parenthesis
    # e.g. "(Custom::Type Type)" -> "(Custom::Type)"
    msg = re.sub(
        r"\(Custom::([A-Za-z0-9_]+)\s+[A-Za-z0-9_]+\)",
        r"(Custom::\1)",
        msg,
    )


    # Clean double spaces
    msg = re.sub(r"\s+", " ", msg).strip()
    return (msg, failed_resource)


def _is_wrapper_or_noise(line: str) -> bool:
    """Check whether a log line is buildspec/wrapper boilerplate or benign noise."""
    noise_patterns = [
        r"^Error while executing command:",
        r"^COMMAND_EXECUTION_ERROR",
        r"^Phase context status code:",
        r"^Command failed with exit code",
        r"^Command did not exit successfully",
        r"^Build command failed",
        r"^Subprocess exited with error",
        r"^npm ERR!",
        r"^yarn run\s+",
        r"^State:\s*FAILED",
        r"^Phase complete:\s*\w+\s+State:\s*\w+",
        r"Parameter 'CloudFormationExecutionPolicies' is not referenced",
        r"^npm notice",
        r"^\s*info\s*\|",
    ]
    return any(re.search(pat, line, flags=re.IGNORECASE) for pat in noise_patterns)


def _is_high_priority_error(line: str) -> bool:
    """Check whether a log line represents an actionable root cause."""
    high_priority_indicators = [
        "❌",
        "ValidationError:",
        "StackPolicyException:",
        "ResourceStatusReason:",
        "StatusReason:",
        "TerminationProtection",
        "AccessDenied",
        "UnauthorizedOperation",
        "is not authorized to perform",
        "ResourceNotFoundException",
        "LimitExceededException",
        "AlreadyExistsException",
        "ClientError:",
        "BotoCoreError:",
        "The following resource(s) failed to create",
        "Received response status [FAILED]",
        "Message returned:",
        "Resource handler returned message",
        "DeploymentError:",
        "Custom::",
        "Resource updates failed:",
        "was not found in the organization configuration",
        "not found in the organization configuration",
    ]
    if any(k in line for k in high_priority_indicators):
        return True
    if "| error |" in line and "failed:" in line:
        return True
    if re.search(r"\b\w+Stack\b.*failed:", line, flags=re.IGNORECASE):
        return True
    if re.search(r"^[A-Z][A-Za-z0-9_]*(?:Error|Exception|Fault):\s+", line):
        return True
    return False


def _is_continuation_line(line: str, prev_cleaned: str) -> bool:
    """Check whether a line is a continuation of a preceding error message."""
    clean = line.strip()
    if not clean or _is_wrapper_or_noise(clean):
        return False

    # Indented lines (e.g. starting with whitespace in raw log)
    if line.startswith(" ") or line.startswith("\t"):
        return True

    continuation_indicators = [
        "Received response status",
        "Message returned:",
        "Resource handler returned message",
        "ResourceStatusReason:",
        "StatusReason:",
        "Custom::",
        "was not found in",
        "not found in",
        "The following resource(s) failed",
        "failed to satisfy constraint",
    ]
    if any(k in clean for k in continuation_indicators):
        return True

    # If previous line ended with a colon or generic wrapper
    if prev_cleaned.endswith(":") or "Resource updates failed" in prev_cleaned:
        if not re.match(r"^\d{4}-\d{2}-\d{2}", clean) and not clean.startswith("[Container]"):
            return True

    return False


def _combine_error_block(lines: list[str]) -> str:
    """Combine multi-line error block into a single coherent error message."""
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]

    header = lines[0]
    tail_lines = lines[1:]

    cleaned_tail: list[str] = []
    for line in tail_lines:
        clean_l = _clean_log_line(line)
        if clean_l and clean_l not in cleaned_tail:
            cleaned_tail.append(clean_l)

    tail_str = " ".join(cleaned_tail)
    if header.endswith(":"):
        return f"{header} {tail_str}".strip()
    return f"{header}: {tail_str}".strip()


def _deduplicate_messages(messages: list[str], max_messages: int = 5) -> list[str]:
    """Deduplicate near-identical and substring error messages, prioritizing richer messages."""
    unique: list[str] = []
    for msg in messages:
        clean = msg.strip()
        if not clean:
            continue

        # Check if already covered or if it replaces an existing shorter message
        matched = False
        for idx, existing in enumerate(unique):
            if clean == existing:
                matched = True
                break
            if clean in existing:
                # Existing message is more specific / has more context
                matched = True
                break
            if existing in clean:
                # New message has more context (e.g. contains stack name + error vs error alone)
                unique[idx] = clean
                matched = True
                break

        if not matched:
            unique.append(clean)

        if len(unique) >= max_messages:
            break

    return unique[:max_messages]


def extract_log_error_diagnostics(
    log_lines: list[str],
    *,
    max_messages: int = 5,
) -> list[str]:
    """Extract actionable failure diagnostics and error messages from raw log lines."""
    if not log_lines:
        return []

    # Flatten log lines in case single events contained newlines
    flat_lines: list[str] = []
    for entry in log_lines:
        if entry:
            flat_lines.extend(entry.splitlines())

    high_priority_matches: list[str] = []
    standard_matches: list[str] = []

    i = 0
    n = len(flat_lines)
    while i < n:
        raw_line = flat_lines[i]
        cleaned = _clean_log_line(raw_line)
        if not cleaned:
            i += 1
            continue

        if _is_high_priority_error(cleaned) or (
            "| error |" in raw_line and not _is_wrapper_or_noise(cleaned)
        ):
            # Look ahead for continuation lines
            block_lines = [cleaned]
            j = i + 1
            while j < n and len(block_lines) < 8:
                next_raw = flat_lines[j]
                next_cleaned = _clean_log_line(next_raw)
                if not next_cleaned:
                    j += 1
                    continue
                if _is_wrapper_or_noise(next_cleaned):
                    break
                if _is_continuation_line(next_raw, block_lines[-1]) or (
                    len(block_lines) == 1
                    and (
                        block_lines[0].endswith(":")
                        or "Resource updates failed" in block_lines[0]
                        or "failed to create" in block_lines[0]
                    )
                ):
                    block_lines.append(next_cleaned)
                    j += 1
                else:
                    break

            combined_msg = _combine_error_block(block_lines)
            if _is_high_priority_error(combined_msg):
                high_priority_matches.append(combined_msg)
            else:
                standard_matches.append(combined_msg)

            i = j
        elif not _is_wrapper_or_noise(cleaned):
            if (
                "| error |" in raw_line
                or "error" in cleaned.lower()
                or "failed" in cleaned.lower()
            ):
                standard_matches.append(cleaned)
            i += 1
        else:
            i += 1

    if high_priority_matches:
        return _deduplicate_messages(high_priority_matches, max_messages=max_messages)

    return _deduplicate_messages(standard_matches, max_messages=max_messages)



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
                if msg:
                    cleaned_msg = _clean_log_line(msg)
                    if cleaned_msg and not _is_wrapper_or_noise(cleaned_msg):
                        phase_errors.append(cleaned_msg)
                    elif msg not in phase_errors:
                        phase_errors.append(msg)

    return _deduplicate_messages(phase_errors, max_messages=max_messages)


__all__ = [
    "extract_log_error_diagnostics",
    "fetch_codebuild_diagnostics",
    "get_cloudwatch_log_events",
    "get_codebuild_build_info",
    "normalize_root_cause_and_resource",
]

