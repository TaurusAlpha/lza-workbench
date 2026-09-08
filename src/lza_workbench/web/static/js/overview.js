export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

export function getStatusVariant(status) {
  if (!status) return "neutral";
  const norm = String(status).toLowerCase();

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

  if (
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
    norm.includes("recorded") ||
    norm.includes("last known")
  ) {
    return "warning";
  }

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
    norm.includes("offline") ||
    norm.includes("rollback")
  ) {
    return "danger";
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
  return [
    ["Pipeline", pipeline.name, { mono: true, truncate: true }],
    ["Latest execution", pipeline.status, { statusIndicator: Boolean(pipeline.status) }],
    ["Current work", [pipeline.currentStage, pipeline.currentAction].filter(Boolean).join(" / ") || null, { truncate: true }],
    ["Failure", pipeline.failureSummary, { truncate: true }],
  ];
}

function configurationSyncStatus(configuration) {
  if (!configuration.localGitClean) {
    return "Local changes";
  }

  const sync = configuration.remoteSync || configuration.gitSync;
  if (!sync) {
    return "Sync unavailable";
  }

  switch (sync.status) {
    case "Synchronized":
      return "In sync";
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

export function renderOverview(container, status) {
  const repoTarget = status.configuration.target
    ? `${status.configuration.repositoryType} / ${status.configuration.target}`
    : status.configuration.repositoryType;

  const uncommittedValue = status.configuration.localGitClean
    ? "0 (Clean)"
    : `${status.configuration.localGitUncommitted} uncommitted`;

  const remoteSyncSummary =
    status.configuration.remoteSync?.summary || status.configuration.gitSync?.summary;

  container.innerHTML = [
    card("Workspace", [
      ["Customer", status.workspace.customerName],
      ["LZA version", status.workspace.lzaVersion, { mono: true }],
      ["Directory", status.workspace.directory, { mono: true, truncate: true }],
      ["Validation", "Not implemented yet"],
    ], "Validation pending"),
    card("AWS context", [
      ["Profile", status.aws.profile, { mono: true }],
      ["Region", status.aws.region, { mono: true }],
      ["Account", status.aws.identity?.account, { mono: true }],
      ["Identity", status.aws.identity?.arn, { mono: true, truncate: true }],
    ], status.aws.isLive ? "Live" : "Offline"),
    card("Installer", [
      ["Stack", status.installer.name, { mono: true, truncate: true }],
      ["Stack status", status.installer.status, { statusIndicator: Boolean(status.installer.status) }],
      ["Deployed version", status.installer.deployedVersion, { mono: true }],
    ], status.health.installer),
    card("Configuration", [
      ["Repository", repoTarget, { mono: true, truncate: true }],
      ["Local Git", status.configuration.localGitBranch, { mono: true }],
      ["Uncommitted", uncommittedValue, { statusIndicator: !status.configuration.localGitClean }],
      ["Remote sync", remoteSyncSummary, { truncate: true }],
    ], configurationSyncStatus(status.configuration), { href: "#/configuration" }),
    card("Installer pipeline", pipelineFields(status.installerPipeline), status.installerPipeline.status),
    card("Configuration pipeline", pipelineFields(status.configurationPipeline), status.configurationPipeline.status, { href: "#/configuration-pipeline" }),
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

