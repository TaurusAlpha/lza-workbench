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

  if (options.mono) {
    if (options.truncate) {
      return `<span class="mono-val truncate" title="${escaped}">${escaped}</span>`;
    }
    return `<span class="mono-val">${escaped}</span>`;
  }

  if (options.truncate) {
    return `<span class="truncate" title="${escaped}">${escaped}</span>`;
  }

  return `<span>${escaped}</span>`;
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
    ["Pipeline", pipeline.name, { mono: true, truncate: true }],
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

  container.innerHTML = [
    card("Workspace", [
      ["Customer", status.workspace.customerName],
      ["LZA version", status.workspace.lzaVersion, { mono: true }],
      ["Directory", status.workspace.directory, { mono: true, truncate: true }],
      ["Prerequisites", prerequisitesDisplay, { statusIndicator: hasPrerequisitesIndicator }],
    ], workspaceBadge, { href: "#/bootstrap" }),
    card("AWS context", [
      ["Profile", status.aws.profile, { mono: true }],
      ["Region", status.aws.region, { mono: true }],
      ["Account", status.aws.identity?.account, { mono: true }],
      ["Identity", status.aws.identity?.arn, { mono: true, truncate: true }],
    ], status.aws.isLive ? "Live" : "Offline"),
    card("Installer", [
      ["Stack", status.installer.name, { mono: true, truncate: true }],
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
  ].join("");

  container.querySelectorAll(".card-interactive").forEach((interactiveCard) => {
    interactiveCard.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      const href = interactiveCard.dataset.href;
      if (href) {
        window.location.hash = href;
      }
    });
  });
}

