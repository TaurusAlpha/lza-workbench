"""Pipeline operational state models, execution observations, and operation records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from lza_workbench.pipeline.failures import PipelineActionFailure
from lza_workbench.pipeline.model import PipelineStageState

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceState


class PipelineObservationRecord(BaseModel):
    """Last-known AWS CodePipeline execution observation and failure diagnostics."""

    model_config = ConfigDict(extra="forbid", strict=False)

    pipeline_name: str | None = None
    execution_id: str | None = None
    status: str | None = None
    failed_stage: str | None = None
    failed_action: str | None = None
    failed_build_url: str | None = None
    error: str | None = None
    observed_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_attempt_error: str | None = None
    exists: bool = False


class PipelineOperationRecord(BaseModel):
    """Recorded initiation or monitoring operation for a pipeline execution."""

    model_config = ConfigDict(extra="forbid", strict=False)

    action: Literal["start", "watch"]
    pipeline_name: str
    execution_id: str
    status: str
    recorded_at: datetime
    error: str | None = None


class PipelineTrackState(BaseModel):
    """Persisted observation and operation record for one pipeline track."""

    model_config = ConfigDict(extra="forbid", strict=False)

    observation: PipelineObservationRecord | None = None
    last_operation: PipelineOperationRecord | None = None

    def has_newer_unobserved_operation(self) -> bool:
        """Return whether last_operation records a newer execution than observation."""
        if self.last_operation is None or not self.last_operation.execution_id:
            return False
        if self.observation is None:
            return True
        if self.observation.execution_id == self.last_operation.execution_id:
            return False
        if self.observation.observed_at is None:
            return True
        return self.last_operation.recorded_at >= self.observation.observed_at

    def resolve_offline_observation(self) -> PipelineObservationRecord | None:
        """Reconcile observation and last_operation for offline status readers.

        When a newer execution was started locally after the last AWS observation,
        preserve the newer execution_id with unknown AWS status (None) rather than
        reporting stale status from a superseded execution.
        """
        if self.has_newer_unobserved_operation():
            assert self.last_operation is not None
            return PipelineObservationRecord(
                pipeline_name=self.last_operation.pipeline_name,
                execution_id=self.last_operation.execution_id,
                status=None,
            )
        return self.observation

    @property
    def latest_known_execution_id(self) -> str | None:
        """Return the most recently started or observed execution ID for this track."""
        reconciled = self.resolve_offline_observation()
        if reconciled is not None and reconciled.execution_id:
            return reconciled.execution_id
        if self.last_operation is not None and self.last_operation.execution_id:
            return self.last_operation.execution_id
        if self.observation is not None and self.observation.execution_id:
            return self.observation.execution_id
        return None

    def execution_id_for_pipeline(self, pipeline_name: str) -> str | None:
        """Return the recorded execution ID matching the given pipeline name."""
        if (
            self.has_newer_unobserved_operation()
            and self.last_operation is not None
            and self.last_operation.pipeline_name == pipeline_name
            and self.last_operation.execution_id
        ):
            return self.last_operation.execution_id
        if (
            self.observation is not None
            and self.observation.pipeline_name == pipeline_name
            and self.observation.execution_id
        ):
            return self.observation.execution_id
        if (
            self.last_operation is not None
            and self.last_operation.pipeline_name == pipeline_name
            and self.last_operation.execution_id
        ):
            return self.last_operation.execution_id
        return None


class PipelinesState(BaseModel):
    """Persisted state for installer and configuration pipelines."""

    model_config = ConfigDict(extra="forbid", strict=False)

    installer: PipelineTrackState = Field(default_factory=PipelineTrackState)
    configuration: PipelineTrackState = Field(default_factory=PipelineTrackState)

    def track(self, pipeline_type: str) -> PipelineTrackState:
        return self.installer if pipeline_type == "installer" else self.configuration


def record_pipeline_started(
    state: WorkspaceState,
    *,
    execution_id: str,
    pipeline_name: str,
    pipeline_type: str = "configuration",
) -> None:
    """Record a pipeline start operation without falsifying AWS pipeline observations."""
    now = datetime.now(UTC)
    track = state.pipelines.track(pipeline_type)
    track.last_operation = PipelineOperationRecord(
        action="start",
        pipeline_name=pipeline_name,
        execution_id=execution_id,
        status="Started",
        recorded_at=now,
        error=None,
    )
    state.touch(now)


def record_pipeline_attempt(
    state: WorkspaceState,
    *,
    pipeline_type: str = "configuration",
    last_attempt_at: datetime | None = None,
    error: str | None = None,
) -> None:
    """Record an attempted but failed pipeline observation without overwriting last-known observation."""
    now = last_attempt_at or datetime.now(UTC)
    track = state.pipelines.track(pipeline_type)
    if track.observation is not None:
        track.observation = track.observation.model_copy(
            update={"last_attempt_at": now, "last_attempt_error": error}
        )
    else:
        track.observation = PipelineObservationRecord(
            observed_at=None,
            last_attempt_at=now,
            last_attempt_error=error,
            exists=False,
        )
    state.touch(now)


def record_pipeline_observation(
    state: WorkspaceState,
    *,
    pipeline_name: str,
    execution_id: str | None,
    status: str | None,
    pipeline_type: str = "configuration",
    failed_stage: str | None = None,
    failed_action: str | None = None,
    failed_build_url: str | None = None,
    error: str | None = None,
    observed_at: datetime | None = None,
    last_attempt_at: datetime | None = None,
    exists: bool | None = None,
) -> PipelineObservationRecord:
    """Record a verified AWS CodePipeline execution observation."""
    now = observed_at or datetime.now(UTC)
    track = state.pipelines.track(pipeline_type)
    resolved_exists = (
        exists
        if exists is not None
        else (bool(status and status != "Not Deployed"))
    )
    observation = PipelineObservationRecord(
        pipeline_name=pipeline_name,
        execution_id=execution_id,
        status=status,
        failed_stage=failed_stage,
        failed_action=failed_action,
        failed_build_url=failed_build_url,
        error=error,
        observed_at=now,
        last_attempt_at=last_attempt_at or now,
        last_attempt_error=None,
        exists=resolved_exists,
    )
    track.observation = observation
    state.touch(now)
    return observation


def _find_stage_for_action(
    stages: list[PipelineStageState] | None, action_name: str | None
) -> str | None:
    if not stages or not action_name:
        return None
    for st in stages:
        st_name = getattr(st, "stage_name", "")
        for act in getattr(st, "actions", []):
            if getattr(act, "action_name", "") == action_name:
                return st_name
    return None


def _extract_watch_failure_details(
    *,
    status: str,
    stages: list[PipelineStageState] | None,
    failed_actions: list[PipelineActionFailure] | None,
    error_message: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if status not in {"Failed", "Cancelled", "TimedOut"}:
        return None, None, None, None

    failed_stage: str | None = None
    failed_action: str | None = None
    failed_build_url: str | None = None
    resolved_error: str | None = None

    if failed_actions:
        first_fa = failed_actions[0]
        failed_action = first_fa.action_name
        failed_build_url = first_fa.external_execution_url
        diags = first_fa.diagnostic_details
        resolved_error = "\n".join(diags) if diags else (first_fa.error_message or first_fa.summary)
        failed_stage = _find_stage_for_action(stages, failed_action)
    elif stages:
        for st in stages:
            if st.status == "Failed":
                failed_stage = st.stage_name
                for act in st.actions:
                    if act.status == "Failed":
                        failed_action = act.action_name
                        failed_build_url = act.external_execution_url
                        resolved_error = act.error_message or act.summary
                        break
                break

    if not resolved_error:
        resolved_error = error_message

    return failed_stage, failed_action, failed_build_url, resolved_error


def record_pipeline_watch_result(
    state: WorkspaceState,
    *,
    execution_id: str,
    pipeline_name: str,
    status: str,
    observed_pipeline_status: str | None = None,
    stages: list[PipelineStageState] | None = None,
    failed_actions: list[PipelineActionFailure] | None = None,
    error_message: str | None = None,
    pipeline_type: str = "configuration",
) -> None:
    """Record watch operation outcome and any verified pipeline execution observation."""
    now = datetime.now(UTC)
    failed_stage, failed_action, failed_build_url, resolved_error = _extract_watch_failure_details(
        status=status,
        stages=stages,
        failed_actions=failed_actions,
        error_message=error_message,
    )

    track = state.pipelines.track(pipeline_type)
    track.last_operation = PipelineOperationRecord(
        action="watch",
        pipeline_name=pipeline_name,
        execution_id=execution_id,
        status=status,
        recorded_at=now,
        error=resolved_error,
    )

    effective_observed_status = (
        observed_pipeline_status if status == "TimedOut" else status
    )
    if effective_observed_status and effective_observed_status not in {"UNKNOWN", "NOT_FOUND"}:
        obs_stage, obs_action, obs_url, obs_error = (
            (failed_stage, failed_action, failed_build_url, resolved_error)
            if effective_observed_status in {"Failed", "Cancelled"}
            else (None, None, None, None)
        )
        record_pipeline_observation(
            state,
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            status=effective_observed_status,
            pipeline_type=pipeline_type,
            failed_stage=obs_stage,
            failed_action=obs_action,
            failed_build_url=obs_url,
            error=obs_error,
            observed_at=now,
        )
    else:
        state.touch(now)


__all__ = [
    "PipelineObservationRecord",
    "PipelineOperationRecord",
    "PipelineTrackState",
    "PipelinesState",
    "record_pipeline_attempt",
    "record_pipeline_observation",
    "record_pipeline_started",
    "record_pipeline_watch_result",
]
