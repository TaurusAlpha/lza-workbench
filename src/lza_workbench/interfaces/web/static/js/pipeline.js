import { card, escapeHtml, renderBadge } from "./overview.js";

function formatTimestamp(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return String(isoStr);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return String(isoStr);
  }
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.round(Number(seconds));
  if (isNaN(total) || total < 0) return "—";
  if (total < 60) return `${total}s`;
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hours}h ${remMins}m`;
}

function renderPipelineBanner(snapshot) {
  const status = (snapshot.status || "").toLowerCase();

  if (status === "failed") {
    const stageDetail = snapshot.failedStage
      ? ` in stage <strong>${escapeHtml(snapshot.failedStage)}</strong>` +
        (snapshot.failedAction ? ` (action <strong>${escapeHtml(snapshot.failedAction)}</strong>)` : "")
      : "";
    const errorText = snapshot.error
      ? `<div class="pipeline-banner-error">${escapeHtml(snapshot.error)}</div>`
      : "";

    return `
      <section class="diagnostic-panel diagnostic-panel-warning" style="border-left-color: #dc2626;">
        <div class="diagnostic-header">
          <span class="badge badge-danger"><span class="badge-dot" aria-hidden="true"></span>Failed</span>
          <h2 class="diagnostic-title">Pipeline Execution Failed${stageDetail}</h2>
        </div>
        ${errorText}
      </section>
    `;
  }

  if (status === "inprogress" || status === "running") {
    const currentDetail = snapshot.currentStage
      ? ` &bull; Stage: <strong>${escapeHtml(snapshot.currentStage)}</strong>` +
        (snapshot.currentAction ? ` &rarr; <strong>${escapeHtml(snapshot.currentAction)}</strong>` : "")
      : "";

    return `
      <section class="diagnostic-panel diagnostic-panel-warning" style="border-left-color: #f59e0b;">
        <div class="diagnostic-header">
          <span class="badge badge-warning"><span class="badge-dot pulse-dot" aria-hidden="true"></span>In Progress</span>
          <h2 class="diagnostic-title">Pipeline is Actively Executing${currentDetail}</h2>
        </div>
        <div class="section-subtitle" style="margin-top: 0.5rem;">
          Monitoring progress with periodic single-pass snapshots.
        </div>
      </section>
    `;
  }

  if (status === "succeeded" || status === "complete") {
    const durStr = snapshot.durationSeconds ? ` (${formatDuration(snapshot.durationSeconds)})` : "";
    return `
      <section class="diagnostic-panel diagnostic-panel-clean">
        <div class="diagnostic-status">
          <span class="badge badge-success"><span class="badge-dot" aria-hidden="true"></span>Succeeded</span>
          <span class="diagnostic-clean-text">Pipeline execution completed successfully${durStr}.</span>
        </div>
      </section>
    `;
  }

  if (status === "stopped" || status === "cancelled") {
    return `
      <section class="diagnostic-panel diagnostic-panel-warning">
        <div class="diagnostic-header">
          <span class="badge badge-neutral">${escapeHtml(snapshot.status)}</span>
          <h2 class="diagnostic-title">Pipeline execution was stopped or cancelled.</h2>
        </div>
      </section>
    `;
  }

  return "";
}

function renderDiagnosticsSection(snapshot, diagnosticsData, onLoadDiagnostics) {
  if (snapshot.status !== "Failed" && (!diagnosticsData || diagnosticsData.length === 0)) {
    return "";
  }

  if (!diagnosticsData) {
    return `
      <section class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h2 class="card-title">Failure Diagnostics</h2>
          <span class="badge badge-danger">Failure Detected</span>
        </div>
        <div class="card-body">
          <p style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 1rem;">
            Enriched failure diagnostics and CloudFormation/CodeBuild root causes can be inspected.
          </p>
          <button type="button" id="btn-load-diagnostics" class="btn btn-primary">
            <span>Load Failure Diagnostics</span>
          </button>
        </div>
      </section>
    `;
  }

  if (diagnosticsData.length === 0) {
    return `
      <section class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h2 class="card-title">Failure Diagnostics</h2>
          <span class="badge badge-neutral">No Root Cause Found</span>
        </div>
        <div class="card-body">
          <span class="val-empty">No detailed build diagnostics could be collected for this execution.</span>
        </div>
      </section>
    `;
  }

  const items = diagnosticsData.map((fail) => {
    const rc = fail.rootCause;
    const categoryBadge = rc?.category
      ? `<span class="badge badge-warning" style="text-transform: uppercase;">${escapeHtml(rc.category)}</span>`
      : "";
    const resRow = fail.failedResource
      ? `<div style="font-size: 0.8125rem; margin-top: 0.25rem;"><span style="color: var(--text-muted);">Resource:</span> <span class="mono-val">${escapeHtml(fail.failedResource)}</span></div>`
      : "";
    const link = fail.externalExecutionUrl
      ? `<a href="${escapeHtml(fail.externalExecutionUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm" style="margin-top: 0.5rem; align-self: flex-start;">View Build Console &rarr;</a>`
      : "";

    const details = (fail.diagnosticDetails || [])
      .map((d) => `<li style="margin-bottom: 0.375rem;">${escapeHtml(d)}</li>`)
      .join("");

    return `
      <div class="diagnostic-failure-card" style="border: 1px solid #fee2e2; background: #fff5f5; border-radius: var(--radius-card); padding: 1rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div>
            <strong style="font-size: 0.9375rem; color: #991b1b;">
              Stage: ${escapeHtml(fail.stageName || "Unknown")} &rarr; Action: ${escapeHtml(fail.actionName)}
            </strong>
            ${resRow}
          </div>
          ${categoryBadge}
        </div>
        ${rc?.message ? `<div style="margin-top: 0.5rem; font-weight: 600; color: #b91c1c;">${escapeHtml(rc.message)}</div>` : ""}
        ${details ? `<ul style="margin: 0.5rem 0 0 1.25rem; font-size: 0.8125rem; color: #4b5563;">${details}</ul>` : ""}
        ${link}
      </div>
    `;
  }).join("");

  return `
    <section class="card" style="margin-top: 1.5rem; border-color: #fca5a5;">
      <div class="card-header" style="background: #fef2f2;">
        <h2 class="card-title" style="color: #991b1b;">Root Cause Failure Diagnostics (${diagnosticsData.length})</h2>
        <span class="badge badge-danger">Identified Root Causes</span>
      </div>
      <div class="card-body">
        ${items}
      </div>
    </section>
  `;
}

function renderStages(stages) {
  if (!stages || stages.length === 0) {
    return `
      <article class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h2 class="card-title">Pipeline Stage Progression</h2>
          <span class="badge badge-neutral">No Stages Recorded</span>
        </div>
        <div class="card-body">
          <span class="val-empty">Detailed stage execution data is not available or pipeline has not started yet.</span>
        </div>
      </article>
    `;
  }

  const stageElements = stages
    .map((stage, idx) => {
      const stageStatusBadge = renderBadge(stage.status || "Unknown");
      const actions = (stage.actions || [])
        .map((action) => {
          const actionStatus = action.status || "Unknown";
          const actionBadge = renderBadge(actionStatus);
          const errorMsg = action.errorMessage
            ? `<div class="stage-action-error">${escapeHtml(action.errorMessage)}</div>`
            : "";
          const link = action.externalExecutionUrl
            ? `<a href="${escapeHtml(action.externalExecutionUrl)}" target="_blank" rel="noopener noreferrer" class="stage-action-link">View Logs &rarr;</a>`
            : "";
          const timing = action.lastStatusChange
            ? `<span style="font-size: 0.75rem; color: var(--text-muted);">${formatTimestamp(action.lastStatusChange)}</span>`
            : "";

          return `
            <div class="stage-action">
              <div class="stage-action-header">
                <span class="stage-action-name mono-val">${escapeHtml(action.name)}</span>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                  ${timing}
                  ${actionBadge}
                </div>
              </div>
              ${action.summary ? `<div class="stage-action-summary">${escapeHtml(action.summary)}</div>` : ""}
              ${errorMsg}
              ${link}
            </div>
          `;
        })
        .join("");

      return `
        <div class="pipeline-stage">
          <div class="pipeline-stage-header">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span class="stage-index-badge">${idx + 1}</span>
              <h3 class="pipeline-stage-title">${escapeHtml(stage.name)}</h3>
            </div>
            ${stageStatusBadge}
          </div>
          <div class="pipeline-stage-actions">${actions}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="pipeline-stages-wrapper" style="margin-top: 1.5rem;">
      <h3 class="subsection-title">Pipeline Stage Progression (${stages.length} stages)</h3>
      <div class="pipeline-stages-grid">${stageElements}</div>
    </div>
  `;
}

export function renderPipelineDetails(container, snapshot, onRefresh, diagnosticsData, onLoadDiagnostics) {
  const pipeType = snapshot.pipelineType === "installer" ? "Installer Pipeline" : "Configuration Pipeline";

  // 1. Pipeline & Execution Card
  const infoFields = [
    ["Pipeline name", snapshot.pipelineName, { mono: true, truncate: true }],
    ["Pipeline type", pipeType],
    ["Pipeline ARN", snapshot.pipelineArn, { mono: true, truncate: true }],
    ["Execution ID", snapshot.executionId || "—", { mono: true, truncate: true }],
    ["Live observation", snapshot.isLive ? "Yes" : "Offline (Recorded)"],
  ];

  // 2. Timing & Progression Card
  const timingFields = [
    ["Status", snapshot.status || "Unknown", { statusIndicator: Boolean(snapshot.status) }],
    ["Started", formatTimestamp(snapshot.startTime)],
    ["Completed / Updated", formatTimestamp(snapshot.lastUpdateTime)],
    ["Duration", formatDuration(snapshot.durationSeconds)],
  ];

  if (snapshot.currentStage) {
    timingFields.push([
      "Current stage/action",
      `${snapshot.currentStage} / ${snapshot.currentAction || "—"}`,
      { mono: true },
    ]);
  }
  if (snapshot.failedStage) {
    timingFields.push([
      "Failed stage/action",
      `${snapshot.failedStage} / ${snapshot.failedAction || "—"}`,
      { mono: true },
    ]);
  }

  container.innerHTML = `
    <div class="config-details-layout">
      ${renderPipelineBanner(snapshot)}

      <div class="details-grid">
        ${card("Pipeline Information", infoFields, snapshot.pipelineType ? snapshot.pipelineType.toUpperCase() : undefined)}
        ${card("Execution & Timing", timingFields, snapshot.status || "Unknown")}
      </div>

      ${renderDiagnosticsSection(snapshot, diagnosticsData, onLoadDiagnostics)}

      ${renderStages(snapshot.stages)}
    </div>
  `;

  // Wire up Load Diagnostics button if present
  container.querySelector("#btn-load-diagnostics")?.addEventListener("click", () => {
    if (typeof onLoadDiagnostics === "function") {
      onLoadDiagnostics();
    }
  });
}
