import { card, escapeHtml, formatFieldValue, renderBadge } from "./overview.js";

function renderPipelineBanner(pipeline) {
  const status = (pipeline.status || "").toLowerCase();

  if (status === "failed") {
    const detail = pipeline.failedStage
      ? ` in stage <strong>${escapeHtml(pipeline.failedStage)}</strong>` +
        (pipeline.failedAction ? ` (action <strong>${escapeHtml(pipeline.failedAction)}</strong>)` : "")
      : "";
    const errorText = pipeline.error
      ? `<div class="pipeline-banner-error">${escapeHtml(pipeline.error)}</div>`
      : "";
    const logLink = pipeline.failedBuildUrl
      ? `<div class="pipeline-banner-action"><a href="${escapeHtml(pipeline.failedBuildUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm">View Build Logs &rarr;</a></div>`
      : "";

    return `
      <section class="diagnostic-panel diagnostic-panel-warning">
        <div class="diagnostic-header">
          <span class="badge badge-danger"><span class="badge-dot" aria-hidden="true"></span>Failed</span>
          <h2 class="diagnostic-title">Pipeline Execution Failed${detail}</h2>
        </div>
        ${errorText}
        ${logLink}
      </section>
    `;
  }

  if (status === "inprogress" || status === "running") {
    return `
      <section class="diagnostic-panel diagnostic-panel-warning">
        <div class="diagnostic-header">
          <span class="badge badge-warning"><span class="badge-dot" aria-hidden="true"></span>In Progress</span>
          <h2 class="diagnostic-title">Pipeline is currently executing</h2>
        </div>
      </section>
    `;
  }

  if (status === "succeeded" || status === "complete") {
    return `
      <section class="diagnostic-panel diagnostic-panel-clean">
        <div class="diagnostic-status">
          <span class="badge badge-success"><span class="badge-dot" aria-hidden="true"></span>Succeeded</span>
          <span class="diagnostic-clean-text">Latest pipeline execution completed successfully.</span>
        </div>
      </section>
    `;
  }

  return "";
}

function renderStages(stages) {
  if (!stages || stages.length === 0) {
    return `
      <article class="card">
        <div class="card-header">
          <h2 class="card-title">Pipeline Stages Execution</h2>
          <span class="badge badge-neutral">No Stages Recorded</span>
        </div>
        <div class="card-body">
          <span class="val-empty">Detailed stage execution data is not available or pipeline has not been executed yet.</span>
        </div>
      </article>
    `;
  }

  const stageElements = stages
    .map((stage) => {
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
          return `
            <div class="stage-action">
              <div class="stage-action-header">
                <span class="stage-action-name mono-val">${escapeHtml(action.name)}</span>
                ${actionBadge}
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
            <h3 class="pipeline-stage-title">${escapeHtml(stage.name)}</h3>
            ${stageStatusBadge}
          </div>
          <div class="pipeline-stage-actions">${actions}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="pipeline-stages-wrapper">
      <h3 class="subsection-title">Pipeline Stages Execution (${stages.length})</h3>
      <div class="pipeline-stages-grid">${stageElements}</div>
    </div>
  `;
}

export function renderPipelineDetails(container, status) {
  const pipe = status.pipeline;
  const ws = status.workspace;

  // Pipeline Info Fields
  const infoFields = [
    ["Pipeline name", pipe.name, { mono: true, truncate: true }],
    ["Pipeline ARN", pipe.arn, { mono: true, truncate: true }],
    ["Status", pipe.status || "Not Executed", { statusIndicator: Boolean(pipe.status) }],
    ["Latest execution ID", pipe.executionId || "—", { mono: true, truncate: true }],
    ["AWS Region", ws.region, { mono: true }],
    ["AWS Account", ws.identity?.account || "—", { mono: true }],
  ];

  // Execution Breakdown Fields
  const execFields = [
    ["Latest status", pipe.status || "Not Executed", { statusIndicator: Boolean(pipe.status) }],
    ["Execution ID", pipe.executionId || "—", { mono: true, truncate: true }],
  ];

  if (pipe.failedStage) {
    execFields.push(["Failed stage", pipe.failedStage, { mono: true }]);
  }
  if (pipe.failedAction) {
    execFields.push(["Failed action", pipe.failedAction, { mono: true }]);
  }
  if (pipe.error) {
    execFields.push(["Failure details", pipe.error]);
  }
  if (pipe.failedBuildUrl) {
    execFields.push(["Build console", pipe.failedBuildUrl, { mono: true, truncate: true }]);
  }

  container.innerHTML = `
    <div class="config-details-layout">
      ${renderPipelineBanner(pipe)}

      <div class="details-grid">
        ${card("Pipeline Information", infoFields, pipe.status || "Not Executed")}
        ${card("Execution Breakdown", execFields, pipe.status || "Not Executed")}
      </div>

      ${renderStages(pipe.stages)}
    </div>
  `;
}
