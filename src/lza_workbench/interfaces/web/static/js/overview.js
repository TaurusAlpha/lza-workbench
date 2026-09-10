export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

export function getStatusVariant(status) {
  if (!status) return "neutral";
  const norm = String(status).toLowerCase();

  // 1. Danger states (failures, errors, rollback, inaccessible)
  if (
    norm.includes("failed") ||
    norm.includes("cancelled") ||
    norm.includes("stopped") ||
    norm.includes("missing") ||
    norm.includes("inaccessible") ||
    norm.includes("diverged") ||
    norm.includes("out of sync") ||
    norm.includes("mismatch") ||
    norm.includes("error") ||
    norm === "offline" ||
    norm.includes("rollback")
  ) {
    return "danger";
  }

  // 2. Warning states (recorded/offline data, attention, drift, in-progress)
  if (
    norm.includes("recorded") ||
    norm.includes("last known") ||
    norm.includes("offline") ||
    norm.includes("not live") ||
    norm.includes("attention") ||
    norm.includes("incomplete") ||
    norm.includes("running") ||
    norm.includes("in progress") ||
    norm.includes("inprogress") ||
    norm.includes("building") ||
    norm.includes("pending") ||
    norm.includes("ahead") ||
    norm.includes("behind") ||
    norm.includes("dirty") ||
    norm.includes("drift") ||
    norm.includes("local changes") ||
    norm.includes("aws unavailable") ||
    norm.includes("bootstrap required") ||
    norm.includes("action required")
  ) {
    return "warning";
  }

  // 3. Success states (only live positive outcomes)
  if (
    norm.includes("healthy") ||
    norm.includes("succeeded") ||
    norm.includes("complete") ||
    norm.includes("available") ||
    norm.includes("clean") ||
    norm.includes("in sync") ||
    norm.includes("synchronized") ||
    norm.includes("present") ||
    norm.includes("exists") ||
    norm.includes("live") ||
    norm === "0"
  ) {
    return "success";
  }

  return "neutral";
}

export function renderBadge(status) {
  if (status === null || status === undefined || status === "") return "";
  const variant = getStatusVariant(status);
  const text = escapeHtml(status);
  return `<span class="badge badge-${variant}" title="${text}"><span class="badge-dot" aria-hidden="true"></span>${text}</span>`;
}

function isInactiveOrEmpty(val) {
  if (val === null || val === undefined || val === "") return true;
  const str = String(val).trim().toLowerCase();
  return (
    str === "not available" ||
    str === "none" ||
    str === "not implemented yet" ||
    str === "none recorded" ||
    str === "—"
  );
}

export function formatFieldValue(fieldValue, options = {}) {
  if (options.raw) {
    return String(fieldValue);
  }

  if (isInactiveOrEmpty(fieldValue)) {
    const raw = fieldValue === null || fieldValue === undefined || fieldValue === "" ? "—" : String(fieldValue);
    const str = raw.trim().toLowerCase();
    const display = str === "not available" || str === "none" || str === "none recorded" || raw === "—" ? "—" : escapeHtml(raw);
    const tooltip = escapeHtml(raw);
    return `<span class="val-empty" title="${tooltip}">${display}</span>`;
  }

  if (options.statusIndicator) {
    const variant = getStatusVariant(fieldValue);
    const escaped = escapeHtml(fieldValue);
    return `<span class="status-indicator status-${variant}"><span class="status-dot" aria-hidden="true"></span><span class="status-val">${escaped}</span></span>`;
  }

  const rawStr = String(fieldValue);
  const escaped = escapeHtml(rawStr);

  const copyBtn = options.copy
    ? `<button type="button" class="btn-copy-inline" data-copy="${escaped}" title="Copy to clipboard">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
      </button>`
    : "";

  if (options.mono) {
    if (options.truncate) {
      return `<span class="mono-val truncate" title="${escaped}">${escaped}</span>${copyBtn}`;
    }
    return `<span class="mono-val">${escaped}</span>${copyBtn}`;
  }

  if (options.truncate) {
    return `<span class="truncate" title="${escaped}">${escaped}</span>${copyBtn}`;
  }

  return `<span>${escaped}</span>${copyBtn}`;
}

export function card(title, fields, status, options = {}) {
  const rows = fields
    .filter(([, fieldValue]) => fieldValue !== undefined)
    .map(([label, fieldValue, fieldOptions = {}]) => {
      return `<div class="kv-row"><dt class="kv-label">${escapeHtml(label)}</dt><dd class="kv-value">${formatFieldValue(fieldValue, fieldOptions)}</dd></div>`;
    })
    .join("");
  const badge = status ? renderBadge(status) : "";
  const titleHtml = options.href
    ? `<h2 class="card-title"><a href="${options.href}" class="card-title-link" title="View ${escapeHtml(title)} details">${escapeHtml(title)}</a></h2>`
    : `<h2 class="card-title">${escapeHtml(title)}</h2>`;
  const interactiveClass = options.href ? " card-interactive" : "";
  const dataHref = options.href ? ` data-href="${escapeHtml(options.href)}"` : "";
  return `<article class="card${interactiveClass}"${dataHref}><div class="card-header">${titleHtml}${badge}</div><dl class="card-body">${rows}</dl></article>`;
}

function pipelineFields(pipeline) {
  const isRecorded = !pipeline.isLive && pipeline.status && pipeline.status !== "—";
  const execStatus = isRecorded ? `Recorded: ${pipeline.status}` : pipeline.status;
  return [
    ["Pipeline", pipeline.name, { mono: true, truncate: true, copy: Boolean(pipeline.name) }],
    ["Latest execution", execStatus, { statusIndicator: Boolean(pipeline.status) }],
    ["Current work", [pipeline.currentStage, pipeline.currentAction].filter(Boolean).join(" / ") || null, { truncate: true }],
    ["Failure", pipeline.failureSummary, { truncate: true }],
  ];
}

function pipelineBadge(pipeline) {
  if (!pipeline.exists || !pipeline.status || pipeline.status === "—") return pipeline.status;
  if (!pipeline.isLive) {
    return `Recorded: ${pipeline.status}`;
  }
  return pipeline.status;
}

function configurationSyncStatus(configuration, isLive = true) {
  if (!configuration.localGitClean) {
    return "Local changes";
  }

  const sync = configuration.remoteSync || configuration.gitSync;
  if (!sync) {
    return "Sync unavailable";
  }

  switch (sync.status) {
    case "Synchronized":
      return isLive ? "In sync" : "Recorded: In sync";
    case "Ahead":
    case "Behind":
    case "Diverged":
      return "Drift detected";
    case "Not Uploaded":
      return "Not deployed";
    case "No Upstream":
      return "No Upstream";
    case undefined:
      return "Sync unavailable";
    default:
      return sync.status;
  }
}

function renderLifecycleStepper(status, bootstrapPlan) {
  // Step 1: Workspace
  const s1Status = "Complete";
  const s1Text = status.workspace.customerName || "Configured";

  // Step 2: Bootstrap Prerequisites
  let s2Status = "In sync";
  let s2Variant = "success";
  let s2Text = "Prerequisites Ready";
  if (!status.aws.isLive) {
    s2Status = "Offline";
    s2Variant = "warning";
    s2Text = "AWS Offline";
  } else if (bootstrapPlan?.isBlocked) {
    s2Status = "Blocked";
    s2Variant = "danger";
    s2Text = "Prerequisites Blocked";
  } else if (bootstrapPlan?.isMutationRequired) {
    s2Status = "Action required";
    s2Variant = "warning";
    s2Text = "Bootstrap Required";
  }

  // Step 3: Installer Stack
  let s3Status = "Pending";
  let s3Variant = "neutral";
  let s3Text = "Not Deployed";
  const instStatus = status.installer.status || "";
  if (instStatus.includes("COMPLETE")) {
    s3Status = "Complete";
    s3Variant = "success";
    s3Text = instStatus;
  } else if (instStatus.includes("IN_PROGRESS")) {
    s3Status = "In Progress";
    s3Variant = "warning";
    s3Text = instStatus;
  } else if (instStatus.includes("FAILED") || instStatus.includes("ROLLBACK")) {
    s3Status = "Failed";
    s3Variant = "danger";
    s3Text = instStatus;
  } else if (instStatus) {
    s3Status = instStatus;
    s3Text = instStatus;
  }

  // Step 4: Configuration & Pipeline
  let s4Status = "In sync";
  let s4Variant = "success";
  let s4Text = "Synced & Ready";
  if (!status.configuration.localGitClean) {
    s4Status = "Local changes";
    s4Variant = "warning";
    s4Text = `${status.configuration.localGitUncommitted} uncommitted`;
  } else if (status.configurationPipeline?.status === "Failed") {
    s4Status = "Failed";
    s4Variant = "danger";
    s4Text = "Pipeline Failed";
  } else if (status.configurationPipeline?.status === "InProgress") {
    s4Status = "Running";
    s4Variant = "warning";
    s4Text = "Pipeline Running";
  }

  return `
    <article class="card card-full lifecycle-card">
      <div class="card-header">
        <div class="lifecycle-header-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <h2 class="card-title">LZA Environment Lifecycle</h2>
        </div>
        <span class="badge badge-${s4Variant}">${escapeHtml(s4Status)}</span>
      </div>
      <div class="card-body">
        <div class="stepper-track">
          <!-- Step 1 -->
          <a href="#/setup" class="stepper-step complete" title="Workspace Initialized">
            <div class="step-indicator">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
            <div class="step-content">
              <span class="step-phase">Phase 1</span>
              <strong class="step-label">Workspace</strong>
              <span class="step-state">${escapeHtml(s1Text)}</span>
            </div>
          </a>

          <div class="stepper-divider ${s2Variant === "success" ? "active" : ""}"></div>

          <!-- Step 2 -->
          <a href="#/bootstrap" class="stepper-step ${s2Variant}" title="AWS Bootstrap Prerequisites">
            <div class="step-indicator">
              ${
                s2Variant === "success"
                  ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
                  : `<span>2</span>`
              }
            </div>
            <div class="step-content">
              <span class="step-phase">Phase 2</span>
              <strong class="step-label">Prerequisites</strong>
              <span class="step-state">${escapeHtml(s2Text)}</span>
            </div>
          </a>

          <div class="stepper-divider ${s3Variant === "success" ? "active" : ""}"></div>

          <!-- Step 3 -->
          <a href="#/installer" class="stepper-step ${s3Variant}" title="Installer Pipeline Stack">
            <div class="step-indicator">
              ${
                s3Variant === "success"
                  ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
                  : `<span>3</span>`
              }
            </div>
            <div class="step-content">
              <span class="step-phase">Phase 3</span>
              <strong class="step-label">Installer Stack</strong>
              <span class="step-state">${escapeHtml(s3Text)}</span>
            </div>
          </a>

          <div class="stepper-divider ${s4Variant === "success" ? "active" : ""}"></div>

          <!-- Step 4 -->
          <a href="#/configuration" class="stepper-step ${s4Variant}" title="Configuration &amp; Pipelines">
            <div class="step-indicator">
              ${
                s4Variant === "success"
                  ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
                  : `<span>4</span>`
              }
            </div>
            <div class="step-content">
              <span class="step-phase">Phase 4</span>
              <strong class="step-label">Config &amp; Pipeline</strong>
              <span class="step-state">${escapeHtml(s4Text)}</span>
            </div>
          </a>
        </div>
      </div>
    </article>
  `;
}

export function renderOverview(container, status, bootstrapPlan = null) {
  const repoTarget = status.configuration.target
    ? `${status.configuration.repositoryType} / ${status.configuration.target}`
    : status.configuration.repositoryType;

  const uncommittedValue = status.configuration.localGitClean
    ? "0 (Clean)"
    : `${status.configuration.localGitUncommitted} uncommitted`;

  const remoteSyncSummary =
    status.configuration.remoteSync?.summary || status.configuration.gitSync?.summary;

  const installerStatusDisplay = !status.aws.isLive && status.installer.status && status.installer.status !== "—"
    ? `Recorded: ${status.installer.status}`
    : status.installer.status;

  let workspaceBadge = "In sync";
  let prerequisitesDisplay = "In sync";
  let hasPrerequisitesIndicator = true;

  if (!status.aws.isLive) {
    workspaceBadge = "Offline";
    prerequisitesDisplay = "Offline";
  } else if (bootstrapPlan) {
    if (bootstrapPlan.isBlocked) {
      workspaceBadge = "Attention required";
      prerequisitesDisplay = "Missing resources";
    } else if (bootstrapPlan.isMutationRequired) {
      workspaceBadge = "Action required";
      prerequisitesDisplay = "Bootstrap required";
    } else {
      workspaceBadge = "In sync";
      prerequisitesDisplay = "In sync";
    }
  } else if (status.health && status.health.workspace) {
    workspaceBadge = status.health.workspace;
    prerequisitesDisplay = "In sync";
  }

  function renderNextStepsCard() {
    const steps = [];
    if (status.assessment && !status.assessment.installerConfigured) {
      steps.push({
        title: "Configure Installer",
        description: "Installer settings (AWS accounts, regions, repository) are incomplete.",
        action: "#/installer",
        actionText: "Configure Installer",
      });
    }
    if (status.assessment && !status.assessment.configurationPresent) {
      steps.push({
        title: "Initialize Configuration",
        description: "Local LZA configuration files are missing or not initialized.",
        action: "#/configuration",
        actionText: "Go to Configuration",
      });
    }
    if (bootstrapPlan && bootstrapPlan.isMutationRequired) {
      steps.push({
        title: "Bootstrap AWS Prerequisites",
        description: "Prerequisite S3 buckets, encryption keys, or secrets require creation or update.",
        action: "#/bootstrap",
        actionText: "Review Bootstrap",
      });
    }

    if (steps.length === 0) return "";

    const stepItems = steps
      .map(
        (s) => `
      <li class="next-step-item">
        <div class="next-step-info">
          <strong class="next-step-title">${escapeHtml(s.title)}</strong>
          <span class="next-step-desc">${escapeHtml(s.description)}</span>
        </div>
        <a href="${escapeHtml(s.action)}" class="btn btn-sm btn-primary">${escapeHtml(s.actionText)}</a>
      </li>`
      )
      .join("");

    return `
      <article class="card card-full card-next-steps">
        <div class="card-header">
          <h2 class="card-title">Pending Workspace Actions</h2>
          <span class="badge badge-warning">${steps.length} pending</span>
        </div>
        <div class="card-body">
          <ul class="next-steps-list">
            ${stepItems}
          </ul>
        </div>
      </article>
    `;
  }

  const lifecycleStepperHtml = renderLifecycleStepper(status, bootstrapPlan);
  const nextStepsHtml = renderNextStepsCard();

  container.innerHTML = [
    lifecycleStepperHtml,
    nextStepsHtml,
    card("Workspace", [
      ["Customer", status.workspace.customerName],
      ["LZA version", status.workspace.lzaVersion, { mono: true }],
      ["Directory", status.workspace.directory, { mono: true, truncate: true, copy: true }],
      ["Prerequisites", prerequisitesDisplay, { statusIndicator: hasPrerequisitesIndicator }],
      ["Switch", '<a href="#/welcome" class="card-link-inline">Switch or open workspace &rarr;</a>', { raw: true }],
    ], workspaceBadge, { href: "#/bootstrap" }),
    card("AWS context", [
      ["Profile", status.aws.profile, { mono: true, copy: Boolean(status.aws.profile) }],
      ["Region", status.aws.region, { mono: true }],
      ["Account", status.aws.identity?.account, { mono: true, copy: Boolean(status.aws.identity?.account) }],
      ["Identity", status.aws.identity?.arn, { mono: true, truncate: true, copy: Boolean(status.aws.identity?.arn) }],
    ], status.aws.isLive ? "Live" : "Offline"),
    card("Installer", [
      ["Stack", status.installer.name, { mono: true, truncate: true, copy: Boolean(status.installer.name) }],
      ["Stack status", installerStatusDisplay, { statusIndicator: Boolean(status.installer.status) }],
      ["Deployed version", status.installer.deployedVersion, { mono: true }],
    ], status.health.installer, { href: "#/installer" }),
    card("Configuration", [
      ["Repository", repoTarget, { mono: true, truncate: true }],
      ["Local Git", status.configuration.localGitBranch, { mono: true }],
      ["Uncommitted", uncommittedValue, { statusIndicator: !status.configuration.localGitClean }],
      ["Remote sync", remoteSyncSummary, { truncate: true }],
    ], configurationSyncStatus(status.configuration, status.aws.isLive), { href: "#/configuration" }),
    card("Installer pipeline", pipelineFields(status.installerPipeline), pipelineBadge(status.installerPipeline), { href: "#/pipeline/installer" }),
    card("Configuration pipeline", pipelineFields(status.configurationPipeline), pipelineBadge(status.configurationPipeline), { href: "#/pipeline/configuration" }),
  ].filter(Boolean).join("");

  // Bind interactive cards
  container.querySelectorAll(".card-interactive").forEach((interactiveCard) => {
    interactiveCard.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input")) return;
      const href = interactiveCard.dataset.href;
      if (href) {
        window.location.hash = href;
      }
    });
  });

  // Bind inline copy buttons
  container.querySelectorAll(".btn-copy-inline").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const text = btn.dataset.copy;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        btn.classList.add("copied");
        setTimeout(() => btn.classList.remove("copied"), 1500);
      } catch (err) {
        console.warn("Clipboard copy failed:", err);
      }
    });
  });
}
